# Demo Script

## 0:00-0:20 Opening

Show Operations Center.

Say: "EPYK Forge is the autonomous operations fleet for the factory floor. Dashboards tell you what happened. Forge starts handling what happens next."

Point out the label: Northstar Precision Works, Synthetic Hackathon Facility.

## 0:20-1:45 Hero Scenario

1. Click `Reset`.
2. Open `Factory` and confirm `MC-04` is `RUNNING` on `MO-4821`, part `NP-4172`, operation `OP30`.
3. Return to `Overview`.
4. Click `Start` under `Hero Scenario`.
5. Watch the precursor telemetry: X-axis load rises, cycle time drifts, and feed holds occur.
6. When the servo alarm fires, open `Incident`.
7. Confirm `INC-1042` appears as `CRITICAL` and moves to `AWAITING_APPROVAL`.
8. Walk the workflow timeline: Observer, Diagnostic, Knowledge, Production, Recovery, Supervisor.
9. Show typed evidence: critical alarm, precursor telemetry, feed-hold precursor, historical context, knowledge references, and contradictory evidence.
10. Show diagnosis: mechanical resistance ranked highest with uncertainty and contradictions.
11. Show production impact: 42 / 120 remaining, 95 min downtime, high order risk, MC-02 fallback, 72 min schedule recovery.
12. Show the recovery plan: maintenance state, P1 ticket, checklist, capacity proposal, schedule transfer approval gate.
13. Approve the schedule proposal.
14. Confirm the work order is assigned to `MC-02` and the incident enters monitoring.
15. Click `Resolve`.
16. Confirm maintenance verification, incident closure, and lesson storage.

## 1:45-2:25 Resilience Scenario

1. Click `Reset`.
2. Click `Retry Test`.
3. Open `Incident`.
4. Show Diagnostic Agent failed once with `Synthetic Gemini request timeout`, retried, and recovered.
5. Confirm there is still only one maintenance ticket, one schedule proposal, and no duplicated evidence rows.

## 2:25-3:00 Security Scenario

1. Click `Reset`.
2. Click `Security Test`.
3. Open `Security`.
4. Show `PROMPT_INJECTION` blocked from `MAL-REDTEAM-001`.
5. Show `UNAUTHORIZED_TOOL` denied for `external_http_request`.
6. Point out: retrieved knowledge is labeled untrusted, and knowledge is evidence, not policy.
7. Confirm no schedule mutation happened without approval.

## 3:00-3:30 Observability

Open `Observability`.

Show trace `trc_servo_overload_cascade`, incident status, duration, agents, tool calls, retries, and spans for event ingestion, agent execution, and denied security action.

## 3:30-3:50 Fleet And Registry

Open `Fleet` and `Registry`.

Show the six agent identities, runtime mode, latest execution status, policy scope, allowed tools, and denied physical-control permissions:

- `machine.control`
- `plc.write`
- `servo.reset`

## 3:50-4:00 Cloud/Fallback Truthfulness

Open `Cloud`.

For local judging, it should truthfully show local JSON store, in-process event bus, and `TEST_STUB` unless real provider credentials are configured outside this pass.
