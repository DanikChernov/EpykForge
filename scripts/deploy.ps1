$ErrorActionPreference = "Stop"

if (-not $env:GOOGLE_CLOUD_PROJECT) {
  throw "Set GOOGLE_CLOUD_PROJECT"
}

$Region = if ($env:GOOGLE_CLOUD_LOCATION) { $env:GOOGLE_CLOUD_LOCATION } else { "us-central1" }
$Repo = "epyk-forge"
$HostName = "$Region-docker.pkg.dev"

gcloud artifacts repositories create $Repo --repository-format=docker --location=$Region
gcloud builds submit --tag "$HostName/$env:GOOGLE_CLOUD_PROJECT/$Repo/forge-api:latest" --file backend/Dockerfile .

gcloud run deploy forge-api `
  --image "$HostName/$env:GOOGLE_CLOUD_PROJECT/$Repo/forge-api:latest" `
  --region $Region `
  --allow-unauthenticated `
  --set-env-vars "FORGE_ENV=production,FORGE_STORE_BACKEND=firestore,FORGE_EVENT_BUS=pubsub,FORGE_MODEL_PROVIDER=REAL_GEMINI,FORGE_GEMINI_MODEL=gemini-3.5-flash,GOOGLE_GENAI_USE_ENTERPRISE=True,GOOGLE_CLOUD_LOCATION=global"

$ApiUrl = gcloud run services describe forge-api --region $Region --format='value(status.url)'
gcloud builds submit `
  --config frontend/cloudbuild.yaml `
  --substitutions "_IMAGE=$HostName/$env:GOOGLE_CLOUD_PROJECT/$Repo/forge-web:latest,_VITE_API_BASE_URL=$ApiUrl" .

gcloud run deploy forge-web `
  --image "$HostName/$env:GOOGLE_CLOUD_PROJECT/$Repo/forge-web:latest" `
  --region $Region `
  --allow-unauthenticated
