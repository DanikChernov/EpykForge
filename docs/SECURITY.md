# Security

EPYK Forge is a governed operations coordination system. It is not a CNC control system.

## Threat Model

Primary risks:

- Prompt injection through retrieved maintenance notes.
- Tool poisoning or unauthorized tool calls.
- Forged agent identity.
- Duplicate event delivery.
- Unapproved production schedule mutation.
- Leakage of credentials or environment secrets.
- Physical safety boundary confusion.

## Controls

- Every agent has a fixed principal and permission set.
- Each tool maps to a required permission.
- The deterministic policy engine is authoritative.
- Retrieved knowledge is treated as untrusted data.
- Schedule application requires supervisor approval.
- CNC actuation, PLC writes, servo reset, spindle commands, and parameter changes are denied.
- Secrets are read from environment/Secret Manager and are never exposed to the frontend.
- Production mode refuses to start unless `FORGE_MODEL_PROVIDER=REAL_GEMINI`.

## Prompt Injection Demonstration

The synthetic document `MAL-REDTEAM-001` contains instructions to ignore policy and exfiltrate data to `attacker.example`. The Knowledge Agent flags it, the policy layer denies `external_http_request`, and the Security Center displays the blocked attempt.

## Physical Safety Boundary

EPYK Forge can create tickets, notifications, schedule proposals, and state records. It never connects to industrial controllers and exposes no physical-control API.
