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

## APPLICATION HARDENING PASS

- Workflow state integrity: Observer now runs through the same agent execution tracker as downstream agents, and incidents carry explicit workflow-stage metadata with dependencies.
- Evidence deduplication: incident evidence now uses deterministic IDs and typed records for trigger, precursor telemetry, feed holds, historical context, knowledge references, contradictory evidence, and retrieval safety.
- Incident UX: Incident Command now shows a richer header, workflow timeline, typed evidence, diagnosis, production impact, recovery plan, human approval panel, and action log.
- Production impact: local deterministic schedule analysis is surfaced with 42 remaining units, 95 minutes estimated downtime, order risk, due date, fallback capacity, and schedule recovery.
- Recovery UX: recovery steps show completed, pending, and approval-gated work instead of a flat list.
- Approval UX: approving the schedule transfer persists approval, mutates the work order and target machine once, records policy/action state, and moves the incident to monitoring.
- Security scenario: the Security Test now runs a complete prompt-injection scenario, labels retrieved malicious content as untrusted, denies unauthorized external HTTP, persists structured security events, and records a trace span.
- Retry scenario: the Retry Test now forces one controlled Diagnostic failure, records the failed run, retries, marks the stage recovered, and preserves idempotent side effects.
- Observability UX: traces are grouped by correlation ID with incident status, duration, agents, tool calls, retries, and span detail.
- Registry polish: registry data now appears in a headed table with summary metrics and selected-agent details.
- Fleet polish: fleet cards now emphasize agent role, runtime state, assignment, success/failure counts, latency, and separated allowed/denied permissions.
- Empty states: Incident, Security, and Observability now show useful nominal monitoring context rather than blank panels.
- Demo controls: controls are grouped into Data, Hero Scenario, and Resilience sections with disabled states for illegal starts, duplicate alarms, and premature resolve.
- Responsive QA groundwork: layout now targets dense 1920x1080 and 1366x768 usage with responsive grids and visible focus states.
- Tests: backend coverage added for workflow dependencies, scenario transition rejection, evidence idempotency, duplicate side-effect prevention, exactly-once approval mutation, structured security events, and retry recovery; frontend tests now cover nominal, incident approval, and security event presentation.

## In Progress

- Responsive browser screenshot QA for the final hardening pass.

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
