from __future__ import annotations

from collections import Counter
from typing import Any

from pydantic import ValidationError

from forge.domain.models import Incident, Machine, WorkOrder
from forge.domain.state_machine import ScenarioStatus, is_active_incident
from forge.simulator.seed import EXPECTED_ASSETS, SCENARIO_ID, SEED_BATCH_ID, SEED_SCHEMA_VERSION


class SeedValidationError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("Seed validation failed: " + "; ".join(errors))
        self.errors = errors


def _ids(values: dict[str, Any], id_key: str) -> list[str]:
    return [str(value.get(id_key, key)) for key, value in values.items()]


def _duplicate_errors(values: list[str], label: str) -> list[str]:
    counts = Counter(values)
    return [f"duplicate {label} {item}" for item, count in counts.items() if count > 1]


def _require_seed_meta(collection: str, doc_id: str, row: dict[str, Any]) -> list[str]:
    errors = []
    if row.get("seed_schema_version") != SEED_SCHEMA_VERSION:
        errors.append(f"{collection}/{doc_id} missing seed_schema_version {SEED_SCHEMA_VERSION}")
    if row.get("seed_batch_id") != SEED_BATCH_ID:
        errors.append(f"{collection}/{doc_id} missing seed_batch_id {SEED_BATCH_ID}")
    if row.get("scenario_id") != SCENARIO_ID:
        errors.append(f"{collection}/{doc_id} missing scenario_id {SCENARIO_ID}")
    if row.get("synthetic") is not True:
        errors.append(f"{collection}/{doc_id} must be synthetic")
    if not row.get("seeded_at"):
        errors.append(f"{collection}/{doc_id} missing seeded_at")
    return errors


def validate_seed_state(state: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    meta = state.get("_meta", {})
    for key, expected in {
        "seed_schema_version": SEED_SCHEMA_VERSION,
        "seed_batch_id": SEED_BATCH_ID,
        "scenario_id": SCENARIO_ID,
    }.items():
        if meta.get(key) != expected:
            errors.append(f"_meta.{key} expected {expected}, got {meta.get(key)}")
    if meta.get("synthetic") is not True:
        errors.append("_meta.synthetic must be true")
    if not meta.get("seeded_at"):
        errors.append("_meta.seeded_at is required")

    machines_raw = state.get("machines", {})
    work_orders_raw = state.get("work_orders", {})
    incidents_raw = state.get("incidents", {})
    events = state.get("events", [])
    traces = state.get("traces", [])

    expected_assets = dict(EXPECTED_ASSETS)
    if len(machines_raw) != 10:
        errors.append(f"expected exactly 10 machines, got {len(machines_raw)}")
    if set(machines_raw) != set(expected_assets):
        errors.append(f"machine IDs mismatch: expected {sorted(expected_assets)}, got {sorted(machines_raw)}")
    errors.extend(_duplicate_errors(_ids(machines_raw, "machine_id"), "machine_id"))

    machines: dict[str, Machine] = {}
    for machine_id, row in machines_raw.items():
        errors.extend(_require_seed_meta("machines", machine_id, row))
        try:
            machine = Machine.model_validate(row)
            machines[machine.machine_id] = machine
        except ValidationError as exc:
            errors.append(f"machines/{machine_id} invalid: {exc}")
            continue
        if machine.model != expected_assets.get(machine.machine_id):
            errors.append(f"{machine.machine_id} model expected {expected_assets.get(machine.machine_id)}, got {machine.model}")
        if machine.active_alarm_codes:
            errors.append(f"{machine.machine_id} has active alarms in nominal seed")
        if machine.at_risk:
            errors.append(f"{machine.machine_id} is at risk in nominal seed")
        if machine.health_score != 100:
            errors.append(f"{machine.machine_id} health_score expected 100, got {machine.health_score}")

    status_counts = Counter(machine.state.value for machine in machines.values())
    for status, expected in {"RUNNING": 6, "IDLE": 3, "SETUP": 1, "ALARM": 0}.items():
        if status_counts.get(status, 0) != expected:
            errors.append(f"nominal {status} count expected {expected}, got {status_counts.get(status, 0)}")

    work_orders: dict[str, WorkOrder] = {}
    errors.extend(_duplicate_errors(_ids(work_orders_raw, "work_order_id"), "work_order_id"))
    for work_order_id, row in work_orders_raw.items():
        errors.extend(_require_seed_meta("work_orders", work_order_id, row))
        try:
            work_order = WorkOrder.model_validate(row)
            work_orders[work_order.work_order_id] = work_order
        except ValidationError as exc:
            errors.append(f"work_orders/{work_order_id} invalid: {exc}")
            continue
        if work_order.assigned_machine_id not in machines_raw:
            errors.append(f"{work_order.work_order_id} assigned to unknown machine {work_order.assigned_machine_id}")
        if work_order.risk.value != "LOW":
            errors.append(f"{work_order.work_order_id} risk expected LOW, got {work_order.risk.value}")
        for downstream in work_order.downstream_orders:
            if downstream not in work_orders_raw:
                errors.append(f"{work_order.work_order_id} downstream order {downstream} is missing")

    for machine in machines.values():
        if machine.current_work_order_id:
            work_order = work_orders.get(machine.current_work_order_id)
            if not work_order:
                errors.append(f"{machine.machine_id} references unknown work order {machine.current_work_order_id}")
            elif work_order.assigned_machine_id != machine.machine_id:
                errors.append(
                    f"{machine.machine_id} current work order {work_order.work_order_id} is assigned to {work_order.assigned_machine_id}"
                )
            if work_order and machine.current_operation != work_order.operation:
                errors.append(f"{machine.machine_id} operation does not match {work_order.work_order_id}")

    mc04 = machines.get("MC-04")
    mo4821 = work_orders.get("MO-4821")
    if not mc04 or not mo4821:
        errors.append("MC-04 and MO-4821 must both exist")
    else:
        if mc04.state.value != "RUNNING":
            errors.append("MC-04 must be RUNNING in nominal seed")
        if mo4821.part_number != "NP-4172" or mo4821.operation != "OP30":
            errors.append("MO-4821 must be NP-4172 OP30")
        if mo4821.part_description != "Synthetic actuator housing":
            errors.append("MO-4821 part description must be Synthetic actuator housing")
        if mo4821.target_cycle_time_sec != 184 or mo4821.observed_cycle_time_sec != 184:
            errors.append("MO-4821 cycle time must be nominal 184 seconds")
        if round(mc04.telemetry.x_axis_load_pct) != 63:
            errors.append("MC-04 nominal X-axis load must be 63%")

    active_incidents = []
    for incident_id, row in incidents_raw.items():
        errors.extend(_require_seed_meta("incidents", incident_id, row))
        try:
            incident = Incident.model_validate(row)
        except ValidationError as exc:
            errors.append(f"incidents/{incident_id} invalid: {exc}")
            continue
        if incident.machine_id not in machines_raw:
            errors.append(f"{incident_id} references unknown machine {incident.machine_id}")
        if incident.work_order_id and incident.work_order_id not in work_orders_raw:
            errors.append(f"{incident_id} references unknown work order {incident.work_order_id}")
        if is_active_incident(incident.status.value):
            active_incidents.append(incident_id)
    if active_incidents:
        errors.append(f"nominal seed must have zero active incidents, got {active_incidents}")

    event_ids = set()
    for event in events:
        event_id = event.get("event_id")
        if event_id in event_ids:
            errors.append(f"duplicate event_id {event_id}")
        event_ids.add(event_id)
        if event.get("machine_id") and event["machine_id"] not in machines_raw:
            errors.append(f"event {event_id} references unknown machine {event['machine_id']}")
        if event.get("work_order_id") and event["work_order_id"] not in work_orders_raw:
            errors.append(f"event {event_id} references unknown work order {event['work_order_id']}")

    trace_incidents = {row.get("incident_id") for row in incidents_raw.values()}
    for span in traces:
        if not span.get("trace_id") or not span.get("correlation_id"):
            errors.append(f"trace span {span.get('span_id')} missing trace identifiers")
        span_incident = span.get("attributes", {}).get("incident_id")
        if span_incident and span_incident not in trace_incidents:
            errors.append(f"trace span {span.get('span_id')} references unknown incident {span_incident}")

    agents = state.get("agent_registry", {})
    identities = state.get("agent_identities", {})
    if len(agents) != 6:
        errors.append(f"expected six registered agents, got {len(agents)}")
    if len(identities) != 6:
        errors.append(f"expected six agent identities, got {len(identities)}")
    for agent_id, manifest in agents.items():
        errors.extend(_require_seed_meta("agent_registry", agent_id, manifest))
        identity = identities.get(agent_id)
        if not identity:
            errors.append(f"missing identity for {agent_id}")
            continue
        errors.extend(_require_seed_meta("agent_identities", agent_id, identity))
        denied = set(manifest.get("denied_tools", [])) | set(identity.get("denied_tools", []))
        for operation in {"machine.control", "plc.write", "servo.reset"}:
            if operation not in denied:
                errors.append(f"{agent_id} missing denied physical operation {operation}")
        if operation := set(manifest.get("allowed_tools", [])).intersection({"machine.control", "plc.write", "servo.reset"}):
            errors.append(f"{agent_id} incorrectly allows physical operations {sorted(operation)}")

    policies = state.get("permission_policies", {})
    denied_policy = policies.get("POLICY-DENY-PHYSICAL-CONTROL", {})
    for operation in {"machine.control", "plc.write", "servo.reset"}:
        if operation not in set(denied_policy.get("operations", [])):
            errors.append(f"permission policy missing denied operation {operation}")
    if "POLICY-KNOWLEDGE-EVIDENCE-NOT-POLICY" not in policies:
        errors.append("knowledge evidence-not-policy defense is missing")

    scenario = state.get("scenario_state", {}).get("default", {})
    errors.extend(_require_seed_meta("scenario_state", "default", scenario))
    if scenario.get("status") != ScenarioStatus.READY.value:
        errors.append(f"scenario must be READY, got {scenario.get('status')}")
    if scenario.get("demo_data_enabled") is not True:
        errors.append("demo_data_enabled must be true")
    if scenario.get("security_attack_enabled"):
        errors.append("security_attack_enabled must be false in nominal seed")

    for collection, required_ids in {
        "security_fixtures": {"SEC-FIXTURE-PROMPT-INJECTION"},
        "retry_fixtures": {"RETRY-FIXTURE-DIAGNOSTIC-TRANSIENT"},
        "alarm_definitions": {"AXIS_SERVO_OVERLOAD_X"},
    }.items():
        bucket = state.get(collection, {})
        missing = required_ids - set(bucket)
        if missing:
            errors.append(f"{collection} missing {sorted(missing)}")
        for doc_id, row in bucket.items():
            errors.extend(_require_seed_meta(collection, doc_id, row))

    docs = state.get("knowledge_documents", {})
    for doc_id, doc in docs.items():
        errors.extend(_require_seed_meta("knowledge_documents", doc_id, doc))
        if not doc.get("provenance"):
            errors.append(f"knowledge document {doc_id} missing provenance")
        if not doc.get("trust_classification"):
            errors.append(f"knowledge document {doc_id} missing trust_classification")
    if docs.get("MAL-REDTEAM-001", {}).get("trust_classification") != "UNTRUSTED":
        errors.append("MAL-REDTEAM-001 must be classified UNTRUSTED")

    if errors:
        raise SeedValidationError(errors)
    return {
        "status": "valid",
        "seed_schema_version": SEED_SCHEMA_VERSION,
        "seed_batch_id": SEED_BATCH_ID,
        "machines": len(machines_raw),
        "work_orders": len(work_orders_raw),
        "knowledge_documents": len(docs),
        "agents": len(agents),
    }
