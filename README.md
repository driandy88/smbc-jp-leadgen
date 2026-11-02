# Hexline: Osaka F&B lead generation

Merchant prospecting for SMBC acquiring sales. Google Maps places are collected on an H3 hex grid, filtered for sales relevance, versioned, and profiled for lead generation.

| Screen | Status |
|---|---|
| **01 Scout** | Live. Runs the collection pipeline in `modules/` against Google Places (or a mock), stores everything in Postgres, and filters, versions and analyses the results. |
| **02 Score**, **03 Field** | Static click-through design pages from the Hexline prototype (`frontend/public/design`). |

## Layout

```
backend/app/          FastAPI monolith: API + serves the built frontend
  routers/            auth, scout (define/run/filter), versions (save/analyze/export), billing
  services/
    collector.py      hex-by-hex Text Search with recursive 7-way split (same algorithm as
                      modules/pipeline/data_collection_pipeline.py), queued in run_cells, every call logged
    places_client.py  RealPlaces (wraps modules/google_maps) and MockPlaces (deterministic fake universe)
    regions.py        MLIT N03 ward boundaries → H3 cells
    records.py        Places JSON → flat rows, filter funnel
    analysis.py       lead-gen profile (segments, area ranking, hours heatmap, completeness)
    summary.py        Claude Sonnet on Vertex AI (rule-based in mock mode or on error)
  jobs.py             Cloud Run Job entrypoint: python -m app.jobs collect --run-id N
frontend/             React + Vite + TypeScript (Login, Scout); Score/Field embedded from public/design
modules/, config/     existing pipeline code, reused by the backend
data/boundaries/      simplified N03 GeoJSON (Osaka + Kyoto prefectures, ward level)
infra/bootstrap.sh    one-time GCP setup (idempotent)
.github/workflows/    ci.yml (lint, test, build) · deploy.yml (main → Artifact Registry → Cloud Run)
```

## How a run works

1. **Define**: pick keywords (Japan F&B catalogue + free text), city → wards, base H3 resolution and max split resolution. The app estimates calls and cost before you start. Real API runs ask for confirmation with the expected ¥ cost.
2. **Run**: each (cell, keyword) is searched in the cell's bounding box, paging to Google's 60-result cap. A full cell is split into its 7 children down to the max resolution. A cell still full at the max resolution is flagged *saturated*. Places are de-duplicated by place id as they arrive.
3. **Filter**: business status, rating, reviews, opening-hours visit window, price, payment, category, services, contact quality and area, with a per-step funnel.
4. **Summary / Versions**: save the filtered set as a named version (CSV export to GCS). **Analyze** profiles it and asks Claude for a lead-gen summary built from aggregate statistics only.

**Real API vs Mock** is a per-run toggle. Mock never calls Google. It generates a deterministic fake universe that has realistic density hotspots, duplicates and saturated cells, and it produces a rule-based summary. Mock calls are still recorded in the ledger, marked mock and not counted as spend.

**Billing**: every Places and Vertex call is a row in `api_calls`. The header shows the real spend for the current month against the monthly budget (SGD by default, `CURRENCY` / `USD_RATE` / `MONTHLY_BUDGET`). The lock icon opens the full ledger (passcode) with totals by SKU, run and day, and a filterable list of every call.

Field mask is `"*"`, so each Text Search call bills at the **Enterprise + Atmosphere** SKU. The rate is set by `PLACES_USD_PER_1000` (default $40, list price, free tier not deducted).

## Run locally

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r backend/requirements-dev.txt
(cd frontend && npm ci && npm run build)
cd backend && PYTHONPATH=..:. ../.venv/bin/uvicorn app.main:app --reload --port 8000
# http://localhost:8000   (frontend dev server with hot reload: cd frontend && npm run dev → :5173)
```

With no `DATABASE_URL`, the app uses `hexline.db` (SQLite) and writes CSVs to `output/`. `GOOGLE_MAPS_API_KEY` in `.env` enables Real API runs. Alternatively, `docker compose up --build` runs the image against Postgres on :8080.

Tests: `cd backend && ../.venv/bin/pytest -q` (runs a full mock collection end to end).

## Deploy

`infra/bootstrap.sh` has already been run for `smbc-leadgen-1833`. It created:

- Artifact Registry `hexline`
- bucket `smbc-leadgen-1833-data`
- Cloud SQL `hexline-pg` (Postgres 16)
- secrets `db-password`, `app-secret-key`, `maps-api-key`
- service accounts `hexline-runtime` and `hexline-deployer`
- Workload Identity Federation pool `github`, restricted to this repository

Every push to `main` runs CI, builds the image and deploys:

- **Cloud Run Job** `hexline-collect`, which runs the collector. The service starts one execution per run, because Cloud Run throttles CPU outside requests and long runs would stall.
- **Cloud Run service** `hexline`, which serves the API and UI. It connects to Cloud SQL over the unix socket.

GitHub repository secrets (Settings → Secrets and variables → Actions):

| Secret | Value |
|---|---|
| `GCP_PROJECT_ID` | `smbc-leadgen-1833` |
| `GCP_REGION` | `asia-northeast1` |
| `GCP_WIF_PROVIDER` | `projects/1008426181320/locations/global/workloadIdentityPools/github/providers/github-oidc` |
| `GCP_DEPLOY_SA` | `hexline-deployer@smbc-leadgen-1833.iam.gserviceaccount.com` |
| `GCP_RUNTIME_SA` | `hexline-runtime@smbc-leadgen-1833.iam.gserviceaccount.com` |
| `CLOUDSQL_INSTANCE` | `smbc-leadgen-1833:asia-northeast1:hexline-pg` |

### Access

The service is deployed **private** (IAM-only). Two ways to reach it:

```bash
# Through a local authenticated proxy (no public exposure):
gcloud run services proxy hexline --region asia-northeast1 --project smbc-leadgen-1833   # → http://localhost:8080

# Or make it public. The app login still applies, but the URL becomes reachable from the internet:
gcloud run services add-iam-policy-binding hexline --region asia-northeast1 --project smbc-leadgen-1833 \
  --member allUsers --role roles/run.invoker
```

### One manual step: enable Claude on Vertex AI

In the Cloud console, open Vertex AI → Model Garden → **Claude Sonnet 5.5** → Enable, and accept Anthropic's terms for the project. Until then, Analyze falls back to the rule-based summary and labels it with the Vertex error.

## Known limits

- Login is a single hardcoded account (`LOGIN_EMAIL` / `LOGIN_PASSWORD`), and the billing passcode is `BILLING_PASSCODE`. Override both through env/Secret Manager before sharing more widely.
- Google Places terms: place IDs may be stored indefinitely, but other Places content should be refreshed or deleted within ~30 days. Check with legal before retaining versions longer.
- Payment fields are self-reported on Google and missing for many listings. "No payment info" is a separate bucket from cash-only.
