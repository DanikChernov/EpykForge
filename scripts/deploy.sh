#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT}"
REGION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
REPO="epyk-forge"
HOST="${REGION}-docker.pkg.dev"

gcloud artifacts repositories create "$REPO" --repository-format=docker --location="$REGION" || true
gcloud builds submit --tag "$HOST/$PROJECT_ID/$REPO/forge-api:latest" --file backend/Dockerfile .

gcloud run deploy forge-api \
  --image "$HOST/$PROJECT_ID/$REPO/forge-api:latest" \
  --region "$REGION" \
  --allow-unauthenticated \
  --set-env-vars "FORGE_ENV=production,FORGE_STORE_BACKEND=firestore,FORGE_EVENT_BUS=pubsub,FORGE_MODEL_PROVIDER=REAL_GEMINI,FORGE_GEMINI_MODEL=gemini-3.5-flash,GOOGLE_GENAI_USE_ENTERPRISE=True,GOOGLE_CLOUD_LOCATION=global"

API_URL="$(gcloud run services describe forge-api --region "$REGION" --format='value(status.url)')"
gcloud builds submit \
  --config frontend/cloudbuild.yaml \
  --substitutions "_IMAGE=$HOST/$PROJECT_ID/$REPO/forge-web:latest,_VITE_API_BASE_URL=$API_URL" .

gcloud run deploy forge-web \
  --image "$HOST/$PROJECT_ID/$REPO/forge-web:latest" \
  --region "$REGION" \
  --allow-unauthenticated

echo "API: $API_URL"
