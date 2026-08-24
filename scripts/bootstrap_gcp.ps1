$ErrorActionPreference = "Stop"

if (-not $env:GOOGLE_CLOUD_PROJECT) {
  throw "Set GOOGLE_CLOUD_PROJECT"
}

$Region = if ($env:GOOGLE_CLOUD_LOCATION) { $env:GOOGLE_CLOUD_LOCATION } else { "us-central1" }
gcloud config set project $env:GOOGLE_CLOUD_PROJECT
gcloud services enable `
  aiplatform.googleapis.com `
  run.googleapis.com `
  pubsub.googleapis.com `
  firestore.googleapis.com `
  secretmanager.googleapis.com `
  cloudtrace.googleapis.com `
  logging.googleapis.com `
  monitoring.googleapis.com `
  artifactregistry.googleapis.com

Write-Host "Google Cloud project bootstrapped for EPYK Forge in $Region."
