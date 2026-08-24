from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any

from forge.domain.models import PolicyDecision, PolicyEffect
from forge.repositories.local_store import LocalStore

AGENT_PERMISSIONS: dict[str, set[str]] = {
    "observer-agent": {
        "factory.events.read",
        "telemetry.read",
        "incidents.create",
        "incidents.evidence.add",
    },
    "diagnostic-agent": {
        "factory.events.read",
        "telemetry.read",
        "maintenance.history.read",
        "incidents.read",
        "incidents.diagnosis.write",
    },
    "knowledge-agent": {
        "knowledge.search",
        "incidents.evidence.add",
        "security.events.create",
    },
    "production-agent": {
        "work_orders.read",
        "machines.read",
        "production.schedule.read",
        "production.schedule.propose",
        "incidents.impact.write",
    },
    "recovery-agent": {
        "maintenance.ticket.create",
        "machine.state.set_maintenance",
        "notifications.create",
        "production.schedule.propose",
        "machine.capacity.reserve",
        "verification.task.create",
        "incidents.plan.write",
    },
    "supervisor-agent": {
        "policy.evaluate",
        "maintenance.ticket.create",
        "machine.state.set_maintenance",
        "notifications.create",
        "production.schedule.propose",
        "machine.capacity.reserve",
        "verification.task.create",
        "approvals.request",
        "production.schedule.apply",
        "memory.write",
    },
    "synthetic-supervisor": {
        "approvals.approve",
        "production.schedule.apply",
        "notifications.create",
        "memory.write",
    },
}

ACTION_PERMISSIONS: dict[str, str] = {
    "create_incident": "incidents.create",
    "add_incident_evidence": "incidents.evidence.add",
    "create_maintenance_ticket": "maintenance.ticket.create",
    "set_machine_maintenance": "machine.state.set_maintenance",
    "create_schedule_proposal": "production.schedule.propose",
    "apply_schedule_change": "production.schedule.apply",
    "reserve_machine_capacity": "machine.capacity.reserve",
    "create_notification": "notifications.create",
    "schedule_followup_check": "verification.task.create",
    "write_operational_memory": "memory.write",
    "external_http_request": "external.http.request",
    "machine_control": "machine.control",
}

APPROVAL_REQUIRED_ACTIONS = {"apply_schedule_change"}
DENIED_ACTIONS = {"machine_control", "external_http_request", "delete_data", "plc_write", "servo_reset"}


class PolicyService:
    def __init__(self, store: LocalStore):
        self.store = store

    def evaluate(
        self,
        *,
        principal: str,
        action: str,
        resource: str | None = None,
        incident_id: str | None = None,
        trace_id: str | None = None,
    ) -> PolicyDecision:
        if action in DENIED_ACTIONS:
            effect = PolicyEffect.DENY
            reason = "Action is outside the governed digital workflow boundary"
        else:
            required = ACTION_PERMISSIONS.get(action, action)
            permissions = AGENT_PERMISSIONS.get(principal, set())
            if required not in permissions:
                effect = PolicyEffect.DENY
                reason = f"Principal lacks required permission {required}"
            elif action in APPROVAL_REQUIRED_ACTIONS:
                effect = PolicyEffect.APPROVAL_REQUIRED
                reason = "Human supervisor approval is required for schedule application"
            else:
                effect = PolicyEffect.ALLOW
                reason = f"Principal has required permission {required}"

        decision = PolicyDecision(
            principal=principal,
            action=action,
            resource=resource,
            effect=effect,
            reason=reason,
            trace_id=trace_id,
            incident_id=incident_id,
        )
        self.store.upsert("policy_decisions", decision.decision_id, decision.model_dump(mode="json"))
        return decision


def requires_permission(action: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(self, *args: Any, **kwargs: Any) -> Any:
            principal = kwargs.get("principal") or kwargs.get("actor") or "unknown"
            incident_id = kwargs.get("incident_id")
            trace_id = kwargs.get("trace_id")
            decision = self.policy.evaluate(
                principal=principal,
                action=action,
                incident_id=incident_id,
                trace_id=trace_id,
            )
            if decision.effect == PolicyEffect.DENY:
                raise PermissionError(decision.reason)
            return func(self, *args, **kwargs)

        return wrapper

    return decorator
