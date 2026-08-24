from __future__ import annotations

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


def transition_incident(incident: Incident, target: IncidentStatus) -> Incident:
    if target == incident.status:
        return incident
    allowed = ALLOWED_TRANSITIONS.get(incident.status, set())
    if target not in allowed:
        raise IllegalIncidentTransition(f"Illegal incident transition {incident.status} -> {target}")
    incident.status = target
    incident.updated_at = utc_now_iso()
    return incident
