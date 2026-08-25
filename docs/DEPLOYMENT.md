# Deployment

## Local

```bash
python -m pip install -e "backend[dev]"
cd frontend && npm.cmd install
```

Run backend:

```bash
python -m uvicorn forge.api.main:app --app-dir backend --host 0.0.0.0 --port 8080
```

Run frontend:

```bash
cd frontend
npm.cmd run dev
```

## Google Cloud

Prerequisites:

- Google Cloud project with billing.
- `gcloud` installed.
- Application Default Credentials configured.
- Roles sufficient to enable APIs, deploy Cloud Run, use Vertex AI/Gemini, Pub/Sub, Firestore, Secret Manager, Cloud Trace, and Cloud Logging.

Bootstrap:

```bash
export GOOGLE_CLOUD_PROJECT=your-project
export GOOGLE_CLOUD_LOCATION=us-central1
scripts/bootstrap_gcp.sh
```

Deploy Cloud Run services:

```bash
scripts/deploy.sh
```

Deploy ADK agents to Agent Runtime after creating a staging bucket:

```bash
export FORGE_AGENT_STAGING_BUCKET=gs://your-agent-staging-bucket
scripts/deploy_agents.sh
```

## Honesty Boundary

Do not mark managed Agent Runtime, Memory Bank, Agent Registry, Agent Identity, Agent Gateway, or Model Armor as active until the deployment has been verified in Google Cloud.

## Demo Seed Data

The complete synthetic platform seed is controlled by API:

```bash
curl -fsS "$FORGE_API_URL/api/demo/seed/status"
curl -fsS -X POST "$FORGE_API_URL/api/demo/seed/import"
curl -fsS -X POST "$FORGE_API_URL/api/demo/seed/disable"
curl -fsS -X POST "$FORGE_API_URL/api/demo/seed/enable"
```

Set `FORGE_DEMO_DATA_ENABLED=false` to start with the synthetic seed disabled. Scenario endpoints return `409` until the seed is imported or enabled.
