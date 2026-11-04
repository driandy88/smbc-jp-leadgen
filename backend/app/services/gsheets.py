"""Write a formatted Google Sheet into the Shared Drive folder (SHEETS_FOLDER_ID).

A service account has no Drive storage of its own, so the file is created with the Drive API inside a
Shared Drive folder it is a Content manager of, then filled and formatted with one Sheets batchUpdate
(chunked for long tables). Cells are typed explicitly, so a name starting with "=" or a "+81" phone is
never read as a formula.

When Google won't hold the file (see Unavailable), the same tabs are written as an .xlsx instead (to_xlsx).

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
    tab: str = "Summary"


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


def _tab(t) -> str:
    return t.tab if isinstance(t, Report) else t.title


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


class Unavailable(Exception):
    """Google won't hold the file (no folder set, folder not in a Shared Drive, no access): fall back to .xlsx."""


def create(name: str, tabs: list[Report | Table | Pivot]) -> str:
    """Create the workbook in the Shared Drive folder and return its URL."""
    folder = get_settings().sheets_folder_id
    if not folder:
        raise Unavailable("SHEETS_FOLDER_ID is not set")
    gs = _session()
    r = gs.post("https://www.googleapis.com/drive/v3/files", params={"supportsAllDrives": "true", "fields": "id"},
                json={"name": name, "mimeType": "application/vnd.google-apps.spreadsheet", "parents": [folder]}, timeout=60)
    if r.status_code in (403, 404):  # storage quota (My Drive folder), or the folder isn't shared with us
        try:
            raise Unavailable(r.json()["error"]["message"])
        except (ValueError, KeyError):
            raise Unavailable(r.text[:200]) from None
    f = _check(r, "Drive")
    sid = f["id"]
    base = f"https://sheets.googleapis.com/v4/spreadsheets/{sid}:batchUpdate"
    first = _check(gs.get(f"https://sheets.googleapis.com/v4/spreadsheets/{sid}", params={"fields": "sheets.properties.sheetId"}, timeout=60), "Sheets")
    default = first["sheets"][0]["properties"]["sheetId"]

    ids = {_tab(t): 100 + i for i, t in enumerate(tabs)}
    size = lambda t: (len(t.rows) + 5, len(t.header) + 2) if isinstance(t, Table) else (200, 12)  # noqa: E731
    setup = [{"addSheet": {"properties": {"sheetId": ids[_tab(t)], "title": _tab(t), "index": i,
                                          "gridProperties": {"rowCount": size(t)[0], "columnCount": size(t)[1]}}}}
             for i, t in enumerate(tabs)]
    setup.append({"deleteSheet": {"sheetId": default}})
    _check(gs.post(base, json={"requests": setup}, timeout=120), "Sheets")

    tables = {t.title: (ids[t.title], t) for t in tabs if isinstance(t, Table)}
    reqs: list[dict] = []
    for t in tabs:
        if isinstance(t, Report):
            reqs += _report(ids[_tab(t)], t)
        elif isinstance(t, Table):
            reqs += _table(ids[_tab(t)], t)
        else:
            reqs += _pivot(ids[_tab(t)], t, tables)
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


def to_xlsx(tabs: list[Report | Table | Pivot]) -> bytes:
    """The same workbook as an Excel file: the summary page, the merchant table (frozen header, filter,
    links) and the pivot as a fixed cross-tab. Opens as-is in Google Sheets."""
    import io

    import xlsxwriter

    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False})
    F = lambda **k: wb.add_format({"font_name": "Arial", "font_size": 10, "valign": "vcenter"} | k)  # noqa: E731
    title, sub = F(bold=True, font_size=18, font_color=INK), F(italic=True, font_color=MUTED)
    head = F(bold=True, font_color="#FFFFFF", bg_color=INK, border=0)
    big, big_red = F(bold=True, font_size=20, font_color=INK), F(bold=True, font_size=20, font_color=RED)
    lab, ctx = F(bold=True, text_wrap=True), F(font_color=MUTED, text_wrap=True)
    blk, txt, num, pct = F(bold=True, font_size=12), F(), F(num_format="#,##0"), F(num_format="0%")
    link = F(font_color="#3E5A63", underline=1)

    def put(ws, r, c, v, fmt=txt, pct_col=False):
        if isinstance(v, Link):
            ws.write_url(r, c, v.url, link, v.label or v.url)
        elif isinstance(v, bool):
            ws.write_string(r, c, "Yes" if v else "No", fmt)
        elif isinstance(v, (int, float)) and v == v:
            ws.write_number(r, c, v, pct if pct_col else num)
        elif v not in (None, ""):
            ws.write_string(r, c, str(v), fmt)

    tables = {t.title: t for t in tabs if isinstance(t, Table)}
    for t in tabs:
        ws = wb.add_worksheet(_tab(t)[:31])
        if isinstance(t, Report):
            ws.hide_gridlines(2)
            ws.write(0, 0, t.title, title)
            ws.write(1, 0, t.subtitle, sub)
            r = 3
            if t.kpis:
                for i, (v, label, c) in enumerate(t.kpis):
                    ws.write(r, i, v, big_red if i == 0 else big)
                    ws.write(r + 1, i, label, lab)
                    ws.write(r + 2, i, c, ctx)
                ws.set_row(r + 2, 30)
                r += 4
            for b in t.blocks:
                ws.write(r, 0, b.title, blk)
                r += 1
                if b.note:
                    ws.write(r, 0, b.note, sub)
                    r += 1
                for j, h in enumerate(b.header):
                    ws.write(r, j, h, head)
                for i, vals in enumerate(b.rows):
                    for j, v in enumerate(vals):
                        put(ws, r + 1 + i, j, v, pct_col=j in b.pct_cols)
                if b.bar_col is not None and b.rows:
                    ws.conditional_format(r + 1, b.bar_col, r + len(b.rows), b.bar_col,
                                          {"type": "data_bar", "bar_color": RED, "bar_solid": True})
                r += len(b.rows) + 2
            ws.set_column(0, 0, 30)
            ws.set_column(1, 8, 18)
        elif isinstance(t, Table):
            for j, h in enumerate(t.header):
                ws.write(0, j, h, head)
            for i, vals in enumerate(t.rows):
                for j, v in enumerate(vals):
                    put(ws, i + 1, j, v, pct_col=j in t.pct_cols)
            ws.freeze_panes(1, 1)
            ws.autofilter(0, 0, len(t.rows), len(t.header) - 1)
            for j, w in enumerate(t.widths or [160] * len(t.header)):
                ws.set_column(j, j, w / 7)
        else:  # pivot as a fixed cross-tab of the source table
            src = tables[t.source]
            ri, ci = src.header.index(t.rows), src.header.index(t.cols)
            counts: dict = {}
            for row in src.rows:
                k = (row[ri] or "—", row[ci] or "—")
                counts[k] = counts.get(k, 0) + 1
            rows = sorted({k[0] for k in counts}, key=lambda x: -sum(v for (a, _), v in counts.items() if a == x))
            cols = sorted({k[1] for k in counts}, key=str)
            ws.write(0, 0, t.title, title)
            ws.write(1, 0, t.note.replace("Live pivot", "Cross-tab").replace(" Edit it in the pivot editor.", ""), sub)
            ws.write(3, 0, f"{t.rows} × {t.cols}", head)
            for j, c in enumerate(cols):
                ws.write(3, j + 1, str(c), head)
            ws.write(3, len(cols) + 1, "Total", head)
            for i, a in enumerate(rows):
                ws.write(4 + i, 0, str(a), txt)
                for j, c in enumerate(cols):
                    if counts.get((a, c)):
                        ws.write_number(4 + i, j + 1, counts[(a, c)], num)
                ws.write_number(4 + i, len(cols) + 1, sum(counts.get((a, c), 0) for c in cols), F(bold=True, num_format="#,##0"))
            ws.set_column(0, 0, 26)
            ws.set_column(1, len(cols) + 1, 14)
    wb.close()
    return buf.getvalue()
