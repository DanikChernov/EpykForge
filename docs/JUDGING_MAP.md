# Judging Map

## Innovation & Operational Utility - 40%

- Autonomous event-to-incident workflow with no initial chat prompt.
- Six specialized agents for observer, diagnostic, knowledge, production, recovery, and policy.
- Servo overload cascade demonstrates manufacturing-specific operations value.
- Recovery actions mutate real application state.
- Production impact uses deterministic scheduling math.

## Architectural Discipline & Tech Stack - 30%

- Google ADK agent definitions.
- Gemini 3.5 Flash integration via Google Gen AI SDK.
- Event ingestion and append-oriented event ledger.
- Explicit incident state machine.
- Deterministic policy engine with least privilege.
- Local store and Firestore-compatible repository.
- OpenTelemetry-style app trace records and Cloud Trace deployment path.

## Demo & Production Readiness - 30%

- Deterministic reset/replay scenario.
- Polished operations console with command center, registry, security, and observability.
- GitHub Actions CI.
- Terraform and deployment scripts.
- Security injection scenario.
- Documentation and Devpost draft.
