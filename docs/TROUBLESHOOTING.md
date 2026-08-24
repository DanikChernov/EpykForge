# Troubleshooting

## `npm.ps1 cannot be loaded`

Use `npm.cmd` on Windows PowerShell:

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

## `gcloud` not found

Install Google Cloud CLI and run:

```bash
gcloud init
gcloud auth application-default login
```

## Production refuses to start

Set:

```bash
FORGE_MODEL_PROVIDER=REAL_GEMINI
GOOGLE_GENAI_USE_ENTERPRISE=True
GOOGLE_CLOUD_PROJECT=your-project
GOOGLE_CLOUD_LOCATION=global
```

## No incident appears

Run:

```bash
python scripts/seed_demo.py
python scripts/run_hero_flow.py
```
