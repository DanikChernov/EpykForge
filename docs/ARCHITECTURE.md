# Architecture

EPYK Forge is an event-driven synthetic manufacturing operations system for the fictional Northstar Precision Works facility.

The working local implementation uses:

- FastAPI backend with a local JSON store.
- Google ADK agent definitions plus an application-level ADK-compatible orchestrator.
- Google Gen AI SDK integration for Gemini Enterprise Agent Platform when `FORGE_MODEL_PROVIDER=REAL_GEMINI`.
- Deterministic model fixtures only when `FORGE_MODEL_PROVIDER=TEST_STUB`.
- React/Vite operations console.
- Deterministic simulator for Scenario A, Servo Overload Cascade.

The cloud path provisions Cloud Run, Pub/Sub, Firestore, Secret Manager, Cloud Logging, Cloud Trace, and Vertex AI/Gemini permissions.

## Runtime Flow

1. The simulator publishes normalized factory events.
2. Event ingestion appends the event ledger and updates machine state.
3. The Observer Agent detects the servo overload without a chat prompt.
4. The orchestrator runs Diagnostic, Knowledge, Production, Recovery, and Supervisor agents.
5. Deterministic tools enforce scheduling math and policy checks.
6. Auto-approved digital actions create a maintenance task, set machine state, create notifications, and create a schedule proposal.
7. Applying the schedule proposal requires human approval.
8. Maintenance resolution records operational memory and closes the incident into `LEARNED`.

## Managed Agent Platform

Local mode uses fallback abstractions:

- Agent Registry: local/Firestore registry abstraction.
- Agent Identity: explicit `forge://agents/...` principals.
- Memory Bank: `MemoryService`-compatible local/Firestore memory records.
- Agent Gateway and Model Armor: documented integration points plus deterministic policy enforcement.

Managed activation requires Google Cloud access and is scripted in `infra/cloud/deploy_agents.py`.

## References Verified

- ADK Python installs with `pip install google-adk`.
- Gemini Enterprise Agent Platform uses the Google Gen AI SDK package `google-genai`.
- Gemini 3.5 Flash model ID is `gemini-3.5-flash`.
- Agent Runtime supports ADK through `vertexai.agent_engines.AdkApp`.
