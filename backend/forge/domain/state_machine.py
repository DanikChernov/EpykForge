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
    ALARMED = "ALARMED"
    INCIDENT_ACTIVE = "INCIDENT_ACTIVE"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    MONITORING = "MONITORING"
    RESOLVED = "RESOLVED"
    LEARNED = "LEARNED"
    ESCALATED = "ESCALATED"


SCENARIO_ALLOWED_TRANSITIONS: dict[ScenarioStatus, set[ScenarioStatus]] = {
    ScenarioStatus.DISABLED: {ScenarioStatus.READY},
    ScenarioStatus.READY: {ScenarioStatus.RUNNING_PRECURSOR, ScenarioStatus.ALARMED},
    ScenarioStatus.RUNNING_PRECURSOR: {ScenarioStatus.ALARMED},
    ScenarioStatus.ALARMED: {ScenarioStatus.INCIDENT_ACTIVE},
    ScenarioStatus.INCIDENT_ACTIVE: {ScenarioStatus.AWAITING_APPROVAL},
    ScenarioStatus.AWAITING_APPROVAL: {ScenarioStatus.APPROVED, ScenarioStatus.ESCALATED},
    ScenarioStatus.APPROVED: {ScenarioStatus.MONITORING},
    ScenarioStatus.MONITORING: {ScenarioStatus.RESOLVED},
    ScenarioStatus.RESOLVED: {ScenarioStatus.LEARNED},
    ScenarioStatus.LEARNED: {ScenarioStatus.READY},
    ScenarioStatus.ESCALATED: {ScenarioStatus.READY},
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
