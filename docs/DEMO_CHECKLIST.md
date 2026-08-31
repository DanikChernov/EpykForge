# Demo Checklist

## Local Baseline

- [ ] `/api/demo/seed/status` shows `demo_data_enabled: true`.
- [ ] `/api/system/info` truthfully shows local/fallback state when cloud integrations are not configured.
- [ ] Reset demo succeeds and scenario status returns to `READY`.
- [ ] Factory shows `MC-04` as `RUNNING` on `MO-4821`.

## Hero Incident

- [ ] Click `Start` from Demo Controls.
- [ ] X-axis load visibly rises.
- [ ] Cycle time visibly drifts.
- [ ] Feed-hold precursor events appear.
- [ ] Servo alarm creates `INC-1042`.
- [ ] Workflow shows Observer, Diagnostic, Knowledge, Production, Recovery, and Supervisor with valid dependency order.
- [ ] Evidence rows are typed and non-duplicated.
- [ ] Diagnosis ranks mechanical resistance / chip accumulation as the leading cause.
- [ ] Knowledge references show provenance and approved revision state.
- [ ] Production impact shows 42 / 120 remaining, 95 min downtime, high risk, MC-02 fallback, and 72 min recovery.
- [ ] Recovery plan shows completed digital actions and schedule transfer awaiting approval.
- [ ] Approval panel shows `APV-1042` for `SCH-1042`.
- [ ] Approving transfer moves `MO-4821` to `MC-02` exactly once.
- [ ] Resolve records verification, closes the incident, and stores the operational lesson.
- [ ] Observability shows trace `trc_servo_overload_cascade`.
- [ ] Fleet metrics update with latest execution status and latency.

## Security Scenario

- [ ] Click `Reset`.
- [ ] Click `Security Test`.
- [ ] Security Center shows a `PROMPT_INJECTION` event from `MAL-REDTEAM-001`.
- [ ] Retrieved malicious content is labeled `UNTRUSTED RETRIEVED CONTENT`.
- [ ] Security Center shows `UNAUTHORIZED_TOOL` denied for `external_http_request`.
- [ ] Policy decision is visible.
- [ ] Trace contains the blocked operation.
- [ ] No unauthorized schedule or machine mutation occurs.

## Failure / Retry Scenario

- [ ] Click `Reset`.
- [ ] Click `Retry Test`.
- [ ] Diagnostic Agent shows a failed attempt and recovered workflow status.
- [ ] Retry count is visible.
- [ ] No duplicate evidence, maintenance ticket, notification, or schedule proposal is created.
- [ ] Observability records the failure/retry path.

## Final Local Validation

- [ ] Backend Ruff passes.
- [ ] Backend pytest passes.
- [ ] Frontend ESLint passes.
- [ ] Frontend Vitest passes.
- [ ] Frontend production build passes.
- [ ] Principal screens are visually checked at 1920x1080, 1440x900, and 1366x768.

## Out Of Scope For This Pass

- [ ] Google Cloud project setup.
- [ ] Real Gemini credentials.
- [ ] Cloud Run, Firestore, Pub/Sub, Agent Runtime, Memory Bank, Agent Registry, Agent Identity, Agent Gateway, Model Armor, or Google Cloud Observability setup.
