from __future__ import annotations

from enum import Enum

from forge.domain.models import Incident, IncidentStatus, utc_now_iso

TERMINAL_STATUSES = {
    IncidentStatus.LEARNED,
    IncidentStatus.FAILED,
    IncidentStatus.ESCALATED,
    IncidentStatus.CANCELLED,
}

ALLOWED_TRANSITIONS: dict[IncidentStatus, set[IncidentStatus]] = {
    IncidentStatus.DETECTED: {IncidentStatus.TRIAGED, IncidentStatus.FAILED, IncidentStatus.CANCELLED},
    IncidentStatus.TRIAGED: {IncidentStatus.INVESTIGATING, IncidentStatus.FAILED, IncidentStatus.ESCALATED},
    IncidentStatus.INVESTIGATING: {IncidentStatus.DIAGNOSIS_READY, IncidentStatus.FAILED, IncidentStatus.ESCALATED},
    IncidentStatus.DIAGNOSIS_READY: {IncidentStatus.IMPACT_ANALYZED, IncidentStatus.FAILED, IncidentStatus.ESCALATED},
    IncidentStatus.IMPACT_ANALYZED: {IncidentStatus.PLAN_READY, IncidentStatus.FAILED, IncidentStatus.ESCALATED},
    IncidentStatus.PLAN_READY: {
        IncidentStatus.AWAITING_APPROVAL,
        IncidentStatus.ACTIONING,
        IncidentStatus.FAILED,
        IncidentStatus.ESCALATED,
    },
    IncidentStatus.AWAITING_APPROVAL: {
        IncidentStatus.ACTIONING,
        IncidentStatus.ESCALATED,
        IncidentStatus.CANCELLED,
    },
    IncidentStatus.ACTIONING: {IncidentStatus.MONITORING, IncidentStatus.FAILED, IncidentStatus.ESCALATED},
    IncidentStatus.MONITORING: {IncidentStatus.RESOLVED, IncidentStatus.FAILED, IncidentStatus.ESCALATED},
    IncidentStatus.RESOLVED: {IncidentStatus.LEARNED},
    IncidentStatus.LEARNED: set(),
    IncidentStatus.FAILED: {IncidentStatus.INVESTIGATING, IncidentStatus.ESCALATED},
    IncidentStatus.ESCALATED: set(),
    IncidentStatus.CANCELLED: set(),
}


class IllegalIncidentTransition(ValueError):
    pass


class ScenarioStatus(str, Enum):
    DISABLED = "DISABLED"
    READY = "READY"
    RUNNING_PRECURSOR = "RUNNING_PRECURSOR"
    INCIDENT_OPEN = "INCIDENT_OPEN"
    DIAGNOSING = "DIAGNOSING"
    DIAGNOSIS_READY = "DIAGNOSIS_READY"
    RECOVERY_PLANNED = "RECOVERY_PLANNED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    RESOLVED = "RESOLVED"
    DEGRADED = "DEGRADED"


SCENARIO_ALLOWED_TRANSITIONS: dict[ScenarioStatus, set[ScenarioStatus]] = {
    ScenarioStatus.DISABLED: {ScenarioStatus.READY},
    ScenarioStatus.READY: {ScenarioStatus.RUNNING_PRECURSOR, ScenarioStatus.INCIDENT_OPEN},
    ScenarioStatus.RUNNING_PRECURSOR: {ScenarioStatus.INCIDENT_OPEN, ScenarioStatus.DEGRADED},
    ScenarioStatus.INCIDENT_OPEN: {ScenarioStatus.DIAGNOSING, ScenarioStatus.DEGRADED},
    ScenarioStatus.DIAGNOSING: {
        ScenarioStatus.DIAGNOSIS_READY,
        ScenarioStatus.RECOVERY_PLANNED,
        ScenarioStatus.AWAITING_APPROVAL,
        ScenarioStatus.DEGRADED,
    },
    ScenarioStatus.DIAGNOSIS_READY: {ScenarioStatus.RECOVERY_PLANNED, ScenarioStatus.DEGRADED},
    ScenarioStatus.RECOVERY_PLANNED: {
        ScenarioStatus.AWAITING_APPROVAL,
        ScenarioStatus.RESOLVED,
        ScenarioStatus.DEGRADED,
    },
    ScenarioStatus.AWAITING_APPROVAL: {ScenarioStatus.RECOVERY_PLANNED, ScenarioStatus.RESOLVED, ScenarioStatus.DEGRADED},
    ScenarioStatus.RESOLVED: {ScenarioStatus.READY},
    ScenarioStatus.DEGRADED: {ScenarioStatus.READY},
}


class IllegalScenarioTransition(ValueError):
    pass


def transition_incident(incident: Incident, target: IncidentStatus) -> Incident:
    if target == incident.status:
        return incident
    allowed = ALLOWED_TRANSITIONS.get(incident.status, set())
    if target not in allowed:
        raise IllegalIncidentTransition(f"Illegal incident transition {incident.status} -> {target}")
    incident.status = target
    incident.updated_at = utc_now_iso()
    return incident


def transition_scenario(current: str, target: ScenarioStatus) -> ScenarioStatus:
    source = ScenarioStatus(current)
    if source == target:
        return source
    allowed = SCENARIO_ALLOWED_TRANSITIONS.get(source, set())
    if target not in allowed:
        raise IllegalScenarioTransition(f"Illegal scenario transition {source.value} -> {target.value}")
    return target


ACTIVE_INCIDENT_STATUSES = {
    IncidentStatus.DETECTED.value,
    IncidentStatus.TRIAGED.value,
    IncidentStatus.INVESTIGATING.value,
    IncidentStatus.DIAGNOSIS_READY.value,
    IncidentStatus.IMPACT_ANALYZED.value,
    IncidentStatus.PLAN_READY.value,
    IncidentStatus.AWAITING_APPROVAL.value,
    IncidentStatus.ACTIONING.value,
    IncidentStatus.MONITORING.value,
}


SCENARIO_MESSAGES: dict[ScenarioStatus, str] = {
    ScenarioStatus.DISABLED: "Synthetic seed data is disabled.",
    ScenarioStatus.READY: "Northstar Precision Works is nominal and ready for a deterministic demo.",
    ScenarioStatus.RUNNING_PRECURSOR: "Servo precursor is running: X-axis load and cycle time are drifting on MC-04.",
    ScenarioStatus.INCIDENT_OPEN: "Servo alarm was injected and INC-1042 is being opened.",
    ScenarioStatus.DIAGNOSING: "Agents are processing evidence, diagnosis, knowledge retrieval, impact and recovery planning.",
    ScenarioStatus.DIAGNOSIS_READY: "Diagnosis and knowledge evidence are ready; recovery planning is continuing.",
    ScenarioStatus.RECOVERY_PLANNED: "Digital recovery actions are complete; maintenance recovery is available after approval.",
    ScenarioStatus.AWAITING_APPROVAL: "Supervisor approval is required before applying the production schedule transfer.",
    ScenarioStatus.RESOLVED: "Maintenance recovery was verified and the incident was resolved.",
    ScenarioStatus.DEGRADED: "A scenario step failed; Import Seed or Reset returns the facility to READY.",
}


def is_active_incident(status: str) -> bool:
    return status in ACTIVE_INCIDENT_STATUSES


def scenario_controls(
    *,
    status: str,
    demo_data_enabled: bool,
    active_incident_status: str | None = None,
) -> dict[str, dict[str, str | bool]]:
    try:
        scenario_status = ScenarioStatus(status)
    except ValueError:
        scenario_status = ScenarioStatus.DEGRADED
    active = bool(active_incident_status and is_active_incident(active_incident_status))

    def control(enabled: bool, reason: str) -> dict[str, str | bool]:
        return {"enabled": enabled, "reason": reason}

    ready = demo_data_enabled and scenario_status == ScenarioStatus.READY and not active
    resolving = (
        demo_data_enabled
        and scenario_status in {ScenarioStatus.RECOVERY_PLANNED, ScenarioStatus.AWAITING_APPROVAL}
        and active_incident_status == IncidentStatus.MONITORING.value
    )
    precursor = demo_data_enabled and scenario_status == ScenarioStatus.RUNNING_PRECURSOR and not active
    enabled_reason = "Available."
    disabled_reason = "Available after the facility is hydrated, seeded, READY, and has no active incident."

    return {
        "import_seed": control(True, "Recovery operation. Installs the validated premium seed batch."),
        "reset": control(
            demo_data_enabled and scenario_status != ScenarioStatus.DISABLED,
            "Resets the active demo to the validated READY seed state.",
        ),
        "enable_seed": control(not demo_data_enabled, "Re-enables synthetic seed data."),
        "disable_seed": control(
            demo_data_enabled and scenario_status in {ScenarioStatus.READY, ScenarioStatus.RESOLVED, ScenarioStatus.DEGRADED},
            "Disables visible synthetic factory data outside an active scenario.",
        ),
        "start": control(ready, enabled_reason if ready else disabled_reason),
        "servo_alarm": control(
            ready or precursor,
            "Injects the stable MC-04 servo alarm immediately."
            if ready or precursor
            else "Available while READY or during the precursor.",
        ),
        "security_attack": control(
            ready,
            enabled_reason if ready else "Available only from READY; it preserves baseline factory records.",
        ),
        "failure": control(
            ready,
            enabled_reason if ready else "Available only from READY; it runs a synthetic retry fixture.",
        ),
        "maintenance_resolved": control(
            resolving,
            "Records technician verification and closes the incident."
            if resolving
            else "Available after schedule approval moves the incident to MONITORING.",
        ),
    }
