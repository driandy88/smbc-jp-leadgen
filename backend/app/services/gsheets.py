"""Write a formatted Google Sheet into the Shared Drive folder (SHEETS_FOLDER_ID).

A service account has no Drive storage of its own, so the file is created with the Drive API inside a
Shared Drive folder it is a Content manager of, then filled and formatted with one Sheets batchUpdate
(chunked for long tables). Cells are typed explicitly, so a name starting with "=" or a "+81" phone is
never read as a formula.

A workbook is a list of tabs:
- Report(title, subtitle, blocks): a summary page; each Block is a small titled table (KPIs, pivots)
- Table(title, header, rows, widths, link_cols, filter): a full data tab with frozen header and filter
- Pivot(title, source, rows, cols, value): a native Sheets pivot over a Table tab, so people can re-cut it
"""

from dataclasses import dataclass, field

from fastapi import HTTPException

from app.settings import get_settings

INK, MUTED, RED, PAPER, BAND = "#1E1E1C", "#5E5A52", "#C8442B", "#F8F6F0", "#F3F0E8"
CHUNK = 1500  # rows per updateCells request


@dataclass
class Link:
    url: str
    label: str = ""


@dataclass
class Block:
    title: str
    header: list[str]
    rows: list[list]
    note: str = ""
    pct_cols: tuple[int, ...] = ()
    bar_col: int | None = None  # a column of numbers to draw as an in-cell bar next to it


@dataclass
class Report:
    title: str
    subtitle: str
    blocks: list[Block]
    kpis: list[tuple[str, str, str]] = field(default_factory=list)  # (value, label, context)


@dataclass
class Table:
    title: str
    header: list[str]
    rows: list[list]
    widths: list[int] = field(default_factory=list)
    pct_cols: tuple[int, ...] = ()


@dataclass
class Pivot:
    title: str
    source: str  # title of a Table tab
    rows: str  # header names
    cols: str
    value: str
    note: str = ""


def _rgb(h: str) -> dict:
    return {k: int(h[i:i + 2], 16) / 255 for k, i in (("red", 1), ("green", 3), ("blue", 5))}


def _cell(v, *, bold=False, color=None, size=None, bg=None, pct=False, italic=False, wrap=False) -> dict:
    c: dict = {}
    if isinstance(v, Link):
        u, lab = v.url.replace('"', '""'), (v.label or v.url).replace('"', '""')
        c["userEnteredValue"] = {"formulaValue": f'=HYPERLINK("{u}","{lab}")'}
    elif isinstance(v, bool):
        c["userEnteredValue"] = {"stringValue": "Yes" if v else "No"}
    elif isinstance(v, (int, float)) and v == v:  # not NaN
        c["userEnteredValue"] = {"numberValue": float(v)}
    elif v not in (None, ""):
        c["userEnteredValue"] = {"stringValue": str(v)}
    f: dict = {}
    tf = {k: x for k, x in (("bold", bold), ("italic", italic), ("fontSize", size)) if x}
    if color:
        tf["foregroundColor"] = _rgb(color)
    if tf:
        f["textFormat"] = tf
    if bg:
        f["backgroundColor"] = _rgb(bg)
    if pct:
        f["numberFormat"] = {"type": "PERCENT", "pattern": "0%"}
    elif isinstance(v, (int, float)) and not isinstance(v, bool):
        f["numberFormat"] = {"type": "NUMBER", "pattern": "#,##0" if float(v).is_integer() else "#,##0.0"}
    if wrap:
        f["wrapStrategy"] = "WRAP"
    f["verticalAlignment"] = "MIDDLE"
    c["userEnteredFormat"] = f
    return c


def _row(cells: list[dict]) -> dict:
    return {"values": cells}


def _put(sheet: int, r0: int, rows: list[dict], c0: int = 0) -> dict:
    return {"updateCells": {"start": {"sheetId": sheet, "rowIndex": r0, "columnIndex": c0}, "rows": rows,
                            "fields": "userEnteredValue,userEnteredFormat"}}


def _widths(sheet: int, widths: list[int]) -> list[dict]:
    return [{"updateDimensionProperties": {"range": {"sheetId": sheet, "dimension": "COLUMNS", "startIndex": i, "endIndex": i + 1},
                                           "properties": {"pixelSize": w}, "fields": "pixelSize"}} for i, w in enumerate(widths)]


def _report(sid: int, t: Report) -> list[dict]:
    reqs = [_put(sid, 0, [_row([_cell(t.title, bold=True, size=18, color=INK)]), _row([_cell(t.subtitle, color=MUTED, italic=True)])])]
    r = 3
    if t.kpis:
        reqs.append(_put(sid, r, [
            _row([_cell(v, bold=True, size=20, color=RED if i == 0 else INK) for i, (v, _, _) in enumerate(t.kpis)]),
            _row([_cell(lab, bold=True, color=INK, wrap=True) for _, lab, _ in t.kpis]),
            _row([_cell(ctx, color=MUTED, wrap=True) for _, _, ctx in t.kpis]),
        ]))
        r += 4
    for b in t.blocks:
        rows = [_row([_cell(b.title, bold=True, size=12, color=INK)])]
        if b.note:
            rows.append(_row([_cell(b.note, color=MUTED, italic=True)]))
        rows.append(_row([_cell(h, bold=True, color="#FFFFFF", bg=INK) for h in b.header]))
        for i, vals in enumerate(b.rows):
            bg = BAND if i % 2 else None
            rows.append(_row([_cell(v, pct=j in b.pct_cols, bg=bg) for j, v in enumerate(vals)]))
        reqs.append(_put(sid, r, rows))
        if b.bar_col is not None and b.rows:
            top = r + len(rows) - len(b.rows)
            col = chr(65 + b.bar_col)
            hi = max((x[b.bar_col] for x in b.rows if isinstance(x[b.bar_col], (int, float))), default=1) or 1
            bars = [_row([{"userEnteredValue": {"formulaValue": f'=SPARKLINE({col}{top + i + 1},{{"charttype","bar";"max",{hi};"color1","{RED}"}})'}}])
                    for i in range(len(b.rows))]
            reqs.append(_put(sid, top, bars, c0=len(b.header)))
        r += len(rows) + 1
    width = max([len(b.header) for b in t.blocks] + [len(t.kpis)] + [1])
    reqs += _widths(sid, [220] + [130] * (width - 1) + [160])
    reqs.append({"updateSheetProperties": {"properties": {"sheetId": sid, "gridProperties": {"hideGridlines": True}},
                                           "fields": "gridProperties.hideGridlines"}})
    return reqs


def _table(sid: int, t: Table) -> list[dict]:
    n = len(t.rows)
    reqs = [_put(sid, 0, [_row([_cell(h, bold=True, color="#FFFFFF", bg=INK) for h in t.header])])]
    for s in range(0, n, CHUNK):
        reqs.append(_put(sid, 1 + s, [_row([_cell(v, pct=j in t.pct_cols) for j, v in enumerate(vals)]) for vals in t.rows[s:s + CHUNK]]))
    rng = {"sheetId": sid, "startRowIndex": 0, "endRowIndex": n + 1, "startColumnIndex": 0, "endColumnIndex": len(t.header)}
    reqs += [
        {"updateSheetProperties": {"properties": {"sheetId": sid, "gridProperties": {"frozenRowCount": 1, "frozenColumnCount": 1}},
                                   "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount"}},
        {"setBasicFilter": {"filter": {"range": rng}}},
        {"addBanding": {"bandedRange": {"range": {**rng, "startRowIndex": 1}, "rowProperties": {
            "firstBandColor": _rgb("#FFFFFF"), "secondBandColor": _rgb(BAND)}}}},
    ]
    reqs += _widths(sid, t.widths or [160] * len(t.header))
    return reqs


def _pivot(sid: int, t: Pivot, tabs: dict[str, tuple[int, Table]]) -> list[dict]:
    src_id, src = tabs[t.source]
    idx = {h: i for i, h in enumerate(src.header)}
    pv = {
        "source": {"sheetId": src_id, "startRowIndex": 0, "endRowIndex": len(src.rows) + 1, "startColumnIndex": 0, "endColumnIndex": len(src.header)},
        "rows": [{"sourceColumnOffset": idx[t.rows], "showTotals": True, "sortOrder": "DESCENDING",
                  "valueBucket": {"valuesIndex": 0}}],
        "columns": [{"sourceColumnOffset": idx[t.cols], "showTotals": True, "sortOrder": "ASCENDING"}],
        "values": [{"summarizeFunction": "COUNTA", "sourceColumnOffset": idx[t.value], "name": "Merchants"}],
    }
    reqs = [_put(sid, 0, [_row([_cell(t.title, bold=True, size=14)]), _row([_cell(t.note, color=MUTED, italic=True)])])]
    reqs.append({"updateCells": {"start": {"sheetId": sid, "rowIndex": 3, "columnIndex": 0}, "rows": [{"values": [{"pivotTable": pv}]}],
                                 "fields": "pivotTable"}})
    reqs += _widths(sid, [200])
    return reqs


def _session():
    import google.auth
    from google.auth.transport.requests import AuthorizedSession

    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/spreadsheets"])
    return AuthorizedSession(creds)


def _check(r, what: str):
    if r.status_code >= 400:
        msg = r.text[:300]
        try:
            msg = r.json()["error"]["message"]
        except Exception:  # noqa: BLE001
            pass
        raise HTTPException(502, f"Google {what} failed: {msg}")
    return r.json()


def create(name: str, tabs: list[Report | Table | Pivot]) -> str:
    """Create the workbook in the Shared Drive folder and return its URL."""
    folder = get_settings().sheets_folder_id
    if not folder:
        raise HTTPException(503, "Google Sheets isn't set up yet: add the service account to a Shared Drive folder and set SHEETS_FOLDER_ID.")
    gs = _session()
    f = _check(gs.post("https://www.googleapis.com/drive/v3/files", params={"supportsAllDrives": "true", "fields": "id"},
                       json={"name": name, "mimeType": "application/vnd.google-apps.spreadsheet", "parents": [folder]}, timeout=60), "Drive")
    sid = f["id"]
    base = f"https://sheets.googleapis.com/v4/spreadsheets/{sid}:batchUpdate"
    first = _check(gs.get(f"https://sheets.googleapis.com/v4/spreadsheets/{sid}", params={"fields": "sheets.properties.sheetId"}, timeout=60), "Sheets")
    default = first["sheets"][0]["properties"]["sheetId"]

    ids = {t.title: 100 + i for i, t in enumerate(tabs)}
    size = lambda t: (len(t.rows) + 5, len(t.header) + 2) if isinstance(t, Table) else (200, 12)  # noqa: E731
    setup = [{"addSheet": {"properties": {"sheetId": ids[t.title], "title": t.title, "index": i,
                                          "gridProperties": {"rowCount": size(t)[0], "columnCount": size(t)[1]}}}}
             for i, t in enumerate(tabs)]
    setup.append({"deleteSheet": {"sheetId": default}})
    _check(gs.post(base, json={"requests": setup}, timeout=120), "Sheets")

    tables = {t.title: (ids[t.title], t) for t in tabs if isinstance(t, Table)}
    reqs: list[dict] = []
    for t in tabs:
        if isinstance(t, Report):
            reqs += _report(ids[t.title], t)
        elif isinstance(t, Table):
            reqs += _table(ids[t.title], t)
        else:
            reqs += _pivot(ids[t.title], t, tables)
    # Big tables go in several calls to stay under the request size limit
    batch: list[dict] = []
    for q in reqs:
        batch.append(q)
        if q.get("updateCells") and sum(len(x.get("updateCells", {}).get("rows", [])) for x in batch) >= CHUNK * 2:
            _check(gs.post(base, json={"requests": batch}, timeout=300), "Sheets")
            batch = []
    if batch:
        _check(gs.post(base, json={"requests": batch}, timeout=300), "Sheets")
    return f"https://docs.google.com/spreadsheets/d/{sid}/edit"
