#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT}"
REGION="${GOOGLE_CLOUD_LOCATION:-us-central1}"

ACCOUNT="$(gcloud auth list --filter=status:ACTIVE --format=value\(account\) 2>/dev/null || true)"
if [[ -z "${ACCOUNT}" ]]; then
  echo "No active gcloud account. Run gcloud auth login first." >&2
  exit 1
fi

echo
echo "EPYK Forge Google Cloud Bootstrap"
echo
printf "Project       %s\n" "${PROJECT_ID}"
printf "Region        %s\n" "${REGION}"
printf "Account       %s\n" "${ACCOUNT}"
echo

gcloud services enable \
  aiplatform.googleapis.com \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  pubsub.googleapis.com \
  firestore.googleapis.com \
  secretmanager.googleapis.com \
  cloudtrace.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com \
  artifactregistry.googleapis.com \
  --project="${PROJECT_ID}"

if ! gcloud firestore databases list --project="${PROJECT_ID}" --format='value(name)' | grep -q '(default)'; then
  gcloud firestore databases create \
    --project="${PROJECT_ID}" \
    --database='(default)' \
    --location="${REGION}" \
    --type=firestore-native
fi

for topic in \
  epyk-forge-factory-events \
  epyk-forge-incident-events \
  epyk-forge-agent-tasks \
  epyk-forge-action-results \
  epyk-forge-notifications
do
  if ! gcloud pubsub topics describe "${topic}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
    gcloud pubsub topics create "${topic}" --project="${PROJECT_ID}"
  fi
done

echo
echo "Google Cloud project bootstrapped for EPYK Forge."
