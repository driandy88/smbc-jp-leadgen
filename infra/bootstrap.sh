#!/usr/bin/env bash
# One-time GCP setup for Hexline. Idempotent: safe to re-run, existing resources are skipped.
#
#   GCLOUD=~/google-cloud-sdk/bin/gcloud ./infra/bootstrap.sh
#
# Prints the GitHub Actions secrets at the end.
set -euo pipefail

GCLOUD="${GCLOUD:-gcloud}"
PROJECT_ID="${PROJECT_ID:-smbc-leadgen-1833}"
REGION="${REGION:-asia-northeast1}"
GITHUB_REPO="${GITHUB_REPO:-driandy88/smbc-jp-leadgen}"

AR_REPO="hexline"
BUCKET="${PROJECT_ID}-data"
SQL_INSTANCE="hexline-pg"
SQL_DB="hexline"
SQL_USER="hexline"
RUNTIME_SA="hexline-runtime"
DEPLOY_SA="hexline-deployer"
WIF_POOL="github"
WIF_PROVIDER="github-oidc"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
g() { "$GCLOUD" --project "$PROJECT_ID" --quiet "$@"; }
exists() { "$@" >/dev/null 2>&1; }
step() { printf '\n== %s\n' "$*"; }

PROJECT_NUMBER="$(g projects describe "$PROJECT_ID" --format='value(projectNumber)')"
RUNTIME_EMAIL="${RUNTIME_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
DEPLOY_EMAIL="${DEPLOY_SA}@${PROJECT_ID}.iam.gserviceaccount.com"

step "Enable APIs"
g services enable run.googleapis.com sqladmin.googleapis.com storage.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com aiplatform.googleapis.com \
  iam.googleapis.com iamcredentials.googleapis.com sts.googleapis.com \
  cloudresourcemanager.googleapis.com places.googleapis.com sql-component.googleapis.com cloudbuild.googleapis.com

step "Artifact Registry"
exists g artifacts repositories describe "$AR_REPO" --location "$REGION" ||
  g artifacts repositories create "$AR_REPO" --repository-format docker --location "$REGION"

step "GCS bucket"
exists g storage buckets describe "gs://${BUCKET}" ||
  g storage buckets create "gs://${BUCKET}" --location "$REGION" --uniform-bucket-level-access

step "Cloud SQL (Postgres 16, smallest tier; creation takes ~10 min)"
exists g sql instances describe "$SQL_INSTANCE" ||
  g sql instances create "$SQL_INSTANCE" --database-version POSTGRES_16 --edition ENTERPRISE \
    --tier db-f1-micro --region "$REGION" --storage-size 10 --storage-auto-increase
exists g sql databases describe "$SQL_DB" --instance "$SQL_INSTANCE" ||
  g sql databases create "$SQL_DB" --instance "$SQL_INSTANCE"

step "Secrets"
new_secret() { # name, value on stdin; only adds a version when the secret is new
  if ! exists g secrets describe "$1"; then
    g secrets create "$1" --replication-policy automatic
    g secrets versions add "$1" --data-file=-
  else
    cat >/dev/null
  fi
}
openssl rand -hex 24 | tr -d '\n' | new_secret db-password
openssl rand -hex 32 | tr -d '\n' | new_secret app-secret-key
if [ -f "$ROOT/.env" ] && grep -q '^GOOGLE_MAPS_API_KEY=' "$ROOT/.env"; then
  grep '^GOOGLE_MAPS_API_KEY=' "$ROOT/.env" | head -1 | cut -d= -f2- | tr -d '"\n' | new_secret maps-api-key
fi
DB_PASSWORD="$(g secrets versions access latest --secret db-password)"
if exists g sql users list --instance "$SQL_INSTANCE" --filter "name=${SQL_USER}" --format 'value(name)' &&
   [ -n "$(g sql users list --instance "$SQL_INSTANCE" --filter "name=${SQL_USER}" --format 'value(name)')" ]; then
  g sql users set-password "$SQL_USER" --instance "$SQL_INSTANCE" --password "$DB_PASSWORD"
else
  g sql users create "$SQL_USER" --instance "$SQL_INSTANCE" --password "$DB_PASSWORD"
fi

step "Service accounts"
exists g iam service-accounts describe "$RUNTIME_EMAIL" ||
  g iam service-accounts create "$RUNTIME_SA" --display-name "Hexline runtime (Cloud Run service + job)"
exists g iam service-accounts describe "$DEPLOY_EMAIL" ||
  g iam service-accounts create "$DEPLOY_SA" --display-name "Hexline deployer (GitHub Actions)"

bind() { g projects add-iam-policy-binding "$PROJECT_ID" --member "serviceAccount:$1" --role "$2" --condition None >/dev/null; }
for role in roles/cloudsql.client roles/secretmanager.secretAccessor roles/aiplatform.user \
            roles/run.developer roles/logging.logWriter; do
  bind "$RUNTIME_EMAIL" "$role"
done
g storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member "serviceAccount:${RUNTIME_EMAIL}" --role roles/storage.objectAdmin >/dev/null
# The service starts job executions that run as the same runtime account
g iam service-accounts add-iam-policy-binding "$RUNTIME_EMAIL" \
  --member "serviceAccount:${RUNTIME_EMAIL}" --role roles/iam.serviceAccountUser >/dev/null

for role in roles/run.admin roles/artifactregistry.writer; do
  bind "$DEPLOY_EMAIL" "$role"
done
g iam service-accounts add-iam-policy-binding "$RUNTIME_EMAIL" \
  --member "serviceAccount:${DEPLOY_EMAIL}" --role roles/iam.serviceAccountUser >/dev/null

step "Workload Identity Federation for GitHub Actions"
exists g iam workload-identity-pools describe "$WIF_POOL" --location global ||
  g iam workload-identity-pools create "$WIF_POOL" --location global --display-name "GitHub Actions"
exists g iam workload-identity-pools providers describe "$WIF_PROVIDER" --location global --workload-identity-pool "$WIF_POOL" ||
  g iam workload-identity-pools providers create-oidc "$WIF_PROVIDER" --location global \
    --workload-identity-pool "$WIF_POOL" --display-name "GitHub OIDC" \
    --issuer-uri "https://token.actions.githubusercontent.com" \
    --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
    --attribute-condition "assertion.repository == '${GITHUB_REPO}'"
g iam service-accounts add-iam-policy-binding "$DEPLOY_EMAIL" --role roles/iam.workloadIdentityUser \
  --member "principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${WIF_POOL}/attribute.repository/${GITHUB_REPO}" >/dev/null

step "Done. GitHub repo secrets (Settings → Secrets and variables → Actions):"
cat <<EOF
GCP_PROJECT_ID      = ${PROJECT_ID}
GCP_REGION          = ${REGION}
GCP_WIF_PROVIDER    = projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${WIF_POOL}/providers/${WIF_PROVIDER}
GCP_DEPLOY_SA       = ${DEPLOY_EMAIL}
GCP_RUNTIME_SA      = ${RUNTIME_EMAIL}
CLOUDSQL_INSTANCE   = ${PROJECT_ID}:${REGION}:${SQL_INSTANCE}
EOF
