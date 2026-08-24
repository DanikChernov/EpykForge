# Demo Script

## 0:00-0:25 Problem

Show Operations Center. Say: "Dashboards tell you what happened. Forge starts handling what happens next."

## 0:25-0:40 Architecture

Open Cloud or architecture diagram. Point to Gemini 3.5 Flash, ADK, Pub/Sub, Firestore, Cloud Run, policy, and trace records.

## 0:40-2:35 Hero Incident

1. Click `Reset`.
2. Confirm MC-04 is `RUNNING`.
3. Click `Start Scenario`.
4. Open Incident.
5. Watch MC-04 telemetry degrade, servo alarm trigger, and `INC-1042` appear.
6. Show agent workflow completing.
7. Show diagnosis, cited knowledge, production impact, recovery plan, and action log.
8. Approve the schedule proposal.
9. Click `Resolve`.

## 2:35-3:05 Governance

Open Fleet, Registry, and Security. Trigger `Security Test` before a reset/start run to show denied injection.

## 3:05-3:30 Observability

Open Observability and show the shared correlation ID `trc_servo_overload_cascade`.

## 3:30-3:50 Google Cloud Proof

Open Cloud. When deployed, it shows Cloud Run revision, real Gemini provider, Pub/Sub, and Firestore.

## 3:50-4:00 Close

"One supervisor can oversee the factory while a secure autonomous agent fleet watches the operational details continuously."
