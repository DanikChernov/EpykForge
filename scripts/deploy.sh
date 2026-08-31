#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-}"
REGION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
REPO="epyk-forge"
API_SERVICE="forge-api"
WEB_SERVICE="forge-web"
HOST="${REGION}-docker.pkg.dev"

if [[ -z "${PROJECT_ID}" ]]; then
  PROJECT_ID="$(gcloud config get-value project 2>/dev/null || true)"
  if [[ -z "${PROJECT_ID}" || "${PROJECT_ID}" == "(unset)" ]]; then
    echo "Set GOOGLE_CLOUD_PROJECT or configure an active gcloud project" >&2
    exit 1
  fi
  echo "GOOGLE_CLOUD_PROJECT is not set; using active gcloud project '${PROJECT_ID}'." >&2
fi

ACTIVE_PROJECT="$(gcloud config get-value project 2>/dev/null || true)"
if [[ -n "${ACTIVE_PROJECT}" && "${ACTIVE_PROJECT}" != "(unset)" && "${ACTIVE_PROJECT}" != "${PROJECT_ID}" ]]; then
  echo "Active gcloud project is '${ACTIVE_PROJECT}'; deployment commands will explicitly use '${PROJECT_ID}'." >&2
fi

ACCOUNT="$(gcloud auth list --filter=status:ACTIVE --format=value\(account\) 2>/dev/null || true)"
if [[ -z "${ACCOUNT}" ]]; then
  echo "No active gcloud account. Run gcloud auth login first." >&2
  exit 1
fi

cloud_run_url() {
  local service="$1"
  gcloud run services describe "${service}" \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --format='value(status.url)' 2>/dev/null || true
}

require_url() {
  local label="$1"
  local url="$2"
  if [[ -z "${url}" || ! "${url}" =~ ^https?:// ]]; then
    echo "${label} must be a non-empty absolute http(s) URL. Actual value: '${url}'" >&2
    exit 1
  fi
}

echo
echo "EPYK Forge Cloud Run Deployment"
echo
printf "Project       %s\n" "${PROJECT_ID}"
printf "Region        %s\n" "${REGION}"
printf "Account       %s\n" "${ACCOUNT}"
printf "API service   %s\n" "${API_SERVICE}"
printf "Web service   %s\n" "${WEB_SERVICE}"
echo

API_IMAGE="${HOST}/${PROJECT_ID}/${REPO}/${API_SERVICE}:latest"
WEB_IMAGE="${HOST}/${PROJECT_ID}/${REPO}/${WEB_SERVICE}:latest"
EXISTING_WEB_URL="$(cloud_run_url "${WEB_SERVICE}")"

if ! gcloud artifacts repositories describe "${REPO}" --project="${PROJECT_ID}" --location="${REGION}" >/dev/null 2>&1; then
  gcloud artifacts repositories create "${REPO}" \
    --project="${PROJECT_ID}" \
    --repository-format=docker \
    --location="${REGION}" \
    --quiet
fi

gcloud builds submit \
  --project="${PROJECT_ID}" \
  --config backend/cloudbuild.yaml \
  --substitutions "_IMAGE=${API_IMAGE}" .

API_ENV="FORGE_ENV=production,FORGE_STORE_BACKEND=firestore,FORGE_EVENT_BUS=pubsub,FORGE_MODEL_PROVIDER=REAL_GEMINI,FORGE_GEMINI_MODEL=gemini-3.5-flash,GOOGLE_GENAI_USE_ENTERPRISE=True,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=global,FORGE_CLOUD_RUN_REGION=${REGION}"
if [[ -n "${EXISTING_WEB_URL}" ]]; then
  API_ENV="${API_ENV},FORGE_WEB_ORIGIN=${EXISTING_WEB_URL}"
fi

gcloud run deploy "${API_SERVICE}" \
  --project="${PROJECT_ID}" \
  --image "${API_IMAGE}" \
  --region "${REGION}" \
  --allow-unauthenticated \
  --set-env-vars "${API_ENV}" \
  --quiet

gcloud run services add-iam-policy-binding "${API_SERVICE}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --member=allUsers \
  --role=roles/run.invoker \
  --quiet

API_URL="$(cloud_run_url "${API_SERVICE}")"
require_url "Forge API URL" "${API_URL}"

echo
printf "Forge Web API target: %s\n" "${API_URL}"
echo

gcloud builds submit \
  --project="${PROJECT_ID}" \
  --config frontend/cloudbuild.yaml \
  --substitutions "_IMAGE=${WEB_IMAGE},_VITE_FORGE_API_URL=${API_URL}" .

gcloud run deploy "${WEB_SERVICE}" \
  --project="${PROJECT_ID}" \
  --image "${WEB_IMAGE}" \
  --region "${REGION}" \
  --allow-unauthenticated \
  --quiet

gcloud run services add-iam-policy-binding "${WEB_SERVICE}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --member=allUsers \
  --role=roles/run.invoker \
  --quiet

WEB_URL="$(cloud_run_url "${WEB_SERVICE}")"
require_url "Forge Web URL" "${WEB_URL}"

gcloud run services update "${API_SERVICE}" \
  --project="${PROJECT_ID}" \
  --region "${REGION}" \
  --update-env-vars "FORGE_WEB_ORIGIN=${WEB_URL}" \
  --quiet

API_URL="$(cloud_run_url "${API_SERVICE}")"
require_url "Forge API URL" "${API_URL}"

echo
printf "API URL       %s\n" "${API_URL}"
printf "Web URL       %s\n" "${WEB_URL}"
echo

if [[ -f scripts/smoke_cloud.ps1 && -x "$(command -v pwsh || true)" ]]; then
  pwsh -NoProfile -ExecutionPolicy Bypass -File scripts/smoke_cloud.ps1 -ProjectId "${PROJECT_ID}" -Region "${REGION}"
elif [[ -f scripts/smoke_cloud.ps1 ]]; then
  echo "Skipping PowerShell cloud smoke test because pwsh is not installed."
fi
