# Devpost Draft

## Title

EPYK Forge

## Tagline

The autonomous operations fleet for the factory floor.

## Inspiration

Manufacturing dashboards usually tell supervisors what already happened. EPYK Forge demonstrates an agent fleet that starts coordinating what happens next.

## What It Does

EPYK Forge watches a synthetic factory, detects a servo overload cascade on MC-04, opens an incident, investigates root cause, retrieves internal knowledge, calculates production risk, creates a recovery plan, performs bounded digital actions, requests approval for a schedule change, and records the outcome as operational memory.

## How It Works

FastAPI ingests synthetic factory events, persists state, and runs a six-agent Google ADK fleet using Gemini 3.5 Flash in real demo mode. A deterministic policy engine governs tools and approvals. The React console exposes operations, incidents, agent registry, security, traces, and cloud proof.

## Google Products Used

- Gemini 3.5 Flash through Gemini Enterprise Agent Platform / Google Gen AI SDK.
- Google Agent Development Kit.
- Cloud Run.
- Pub/Sub.
- Firestore.
- Secret Manager.
- Cloud Logging and Cloud Trace deployment path.
- Agent Runtime / Memory Bank / Gateway / Model Armor integration path. [VERIFY BEFORE SUBMISSION]

## Challenges

The main challenge was making the workflow agentic without making it reckless: digital actions are autonomous, but physical CNC control and schedule application are governed.

## Accomplishments

- No-chat autonomous incident pipeline.
- Manufacturing-specific hero scenario.
- Prompt-injection defense visible in the UI.
- Deterministic reset/replay for a four-minute demo.

## Synthetic Data Statement

Northstar Precision Works, machines, work orders, telemetry, procedures, and incidents are fictional synthetic data created exclusively for this hackathon demo.

## What's Next

- Activate managed Agent Runtime and Memory Bank after cloud verification.
- Add multimodal synthetic alarm-screen evidence.
- Expand scenario library beyond servo overload.
