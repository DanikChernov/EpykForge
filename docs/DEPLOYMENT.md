# Deployment

## Local

Install dependencies:

```powershell
python -m pip install -e "backend[dev]"
cd frontend
npm.cmd install
```

Run the backend on `http://localhost:8080`:

```powershell
$env:FORGE_MODEL_PROVIDER="TEST_STUB"
python -m uvicorn forge.api.main:app --app-dir backend --host 0.0.0.0 --port 8080
```

Run the frontend on `http://localhost:5173`:

```powershell
cd frontend
npm.cmd run dev
```

When `VITE_FORGE_API_URL` is blank, Vite development mode targets `http://localhost:8080`.

## Google Cloud Prerequisites

Use a project with billing enabled and permissions to enable APIs, run Cloud Build, deploy Cloud Run, create Artifact Registry repositories, create Firestore databases, create Pub/Sub topics, and call Vertex AI/Gemini.

Authenticate:

```powershell
gcloud.cmd auth login
gcloud.cmd auth application-default login
```

Select deployment inputs:

```powershell
$env:GOOGLE_CLOUD_PROJECT="your-project-id"
$env:GOOGLE_CLOUD_LOCATION="us-central1"
```

`GOOGLE_CLOUD_LOCATION` is the Cloud Run and Artifact Registry region used by the scripts. The API container is deployed with `GOOGLE_CLOUD_LOCATION=global` for Gemini, plus `FORGE_CLOUD_RUN_REGION` for truthful runtime reporting.

## Bootstrap

```powershell
.\scripts\bootstrap_gcp.ps1
```

If Windows script execution is restricted, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\bootstrap_gcp.ps1
```

Bootstrap enables required Google APIs, creates the default Firestore database when missing, and creates the Pub/Sub topics used by the cloud event bus. It does not change the active gcloud project; commands pass `--project` explicitly.

## Deploy Cloud Run

```powershell
.\scripts\deploy.ps1
```

If needed:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy.ps1
```

The deployment order is:

1. Build and deploy `forge-api`.
2. Resolve the actual `forge-api` Cloud Run URL.
3. Build `forge-web` with `VITE_FORGE_API_URL` set to that API URL.
4. Deploy `forge-web`.
5. Update `forge-api` with `FORGE_WEB_ORIGIN` set to the deployed web URL for CORS.
6. Run `scripts/smoke_cloud.ps1`.

The frontend API URL is a Vite build-time value. Setting `VITE_FORGE_API_URL` only as a Cloud Run runtime environment variable after the web image is built will not update the browser bundle.

## Smoke Test

Run the smoke test independently after any manual deployment change:

```powershell
.\scripts\smoke_cloud.ps1
```

If needed:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\smoke_cloud.ps1
```

It resolves `forge-api` and `forge-web`, verifies `/health`, `/ready`, and `/api/system/info` return JSON, verifies the web root returns HTML, checks that the frontend bundle contains the resolved API URL, and validates CORS for the deployed web origin.

## Agent Runtime

Deploy ADK agents to Agent Runtime separately after creating a staging bucket:

```powershell
$env:FORGE_AGENT_STAGING_BUCKET="gs://your-agent-staging-bucket"
bash scripts/deploy_agents.sh
```

## Honesty Boundary

Do not mark managed Agent Runtime, Memory Bank, Agent Registry, Agent Identity, Agent Gateway, or Model Armor as active until the deployment has been verified in Google Cloud.

## Demo Seed Data

Use the resolved API URL from deployment or smoke output:

```powershell
$env:FORGE_API_URL="https://forge-api-..."
Invoke-RestMethod "$env:FORGE_API_URL/api/demo/seed/status"
Invoke-RestMethod "$env:FORGE_API_URL/api/demo/seed/import" -Method Post
Invoke-RestMethod "$env:FORGE_API_URL/api/demo/seed/disable" -Method Post
Invoke-RestMethod "$env:FORGE_API_URL/api/demo/seed/enable" -Method Post
```

Set `FORGE_DEMO_DATA_ENABLED=false` to start with the synthetic seed disabled. Scenario endpoints return `409` until the seed is imported or enabled.
