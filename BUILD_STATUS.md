# EPYK Forge Build Status

Northstar Precision Works is a fictional synthetic manufacturing environment created exclusively for the hackathon demonstration.

## Complete

- Repository initialized as a clean EPYK Forge monorepo.
- Current Google documentation reviewed for ADK, Gemini Enterprise Agent Platform, Gemini 3.5 Flash, Agent Runtime, Memory Bank, structured output, Agent Identity, and tracing.
- Backend domain model, incident state machine, local JSON operational store, event ledger, deterministic simulator, six-agent fleet, policy engine, action tools, approval gate, security scenario, memory fallback, and FastAPI API are implemented.
- Google Cloud-facing Firestore store, Pub/Sub publisher, and MemoryService fallback abstractions are implemented.
- Complete synthetic platform seed import, status, enable, and disable controls are implemented in API and UI.
- PIN-protected Admin setup panel is implemented with PIN `1234`, Gemini readiness checks, Gemini smoke action, seed import/enable/disable, and visible seed data tables.
- Local smoke checks passed for hero flow, security injection denial, and forced agent retry recovery.
- Frontend React operations console, incident command center, agent fleet, registry, security center, observability, cloud proof, and demo controls are implemented.
- Terraform, Cloud Run/Agent Runtime deployment scripts, CI, synthetic data notes, README, security docs, demo script, judging map, Devpost draft, and disclosures are implemented.
- Validation completed: backend Ruff, backend pytest, frontend ESLint, frontend Vitest, frontend production build, production npm audit, CLI demo script, HTTP hero flow, and HTTP security flow.
- Local dependency verification completed: `google-adk` and `google-genai` import successfully; `/ready` reports `adk_available=true`.

## In Progress

- None.

## Blocked

- Managed Google Cloud deployment and managed Agent Platform activation require local `gcloud`/ADC credentials. `gcloud` is not currently installed on PATH.
- Actual Agent Runtime, Memory Bank, Agent Registry, Agent Identity, Agent Gateway, Model Armor, and Cloud Trace verification require a Google Cloud project with billing and permissions.

## Deferred

- Optional multimodal evidence analysis.
- Optional Gemma classifier.

## Validation Notes

- Python available locally: 3.10.11.
- Node available locally: 24.16.0.
- `npm.ps1` is blocked by PowerShell execution policy; use `npm.cmd`.
- `git` and `rg` are not currently on PATH; PowerShell fallbacks are used.
- A stale local Python package warning for an invalid old `-vicorn` distribution appeared during install, but `uvicorn` 0.52.4 is installed and the API runs.
