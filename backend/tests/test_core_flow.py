from __future__ import annotations

from pathlib import Path

import pytest

from forge.agents.fleet import AgentFleet
from forge.agents.model_service import DeterministicModelService
from forge.config.settings import Settings
from forge.domain.models import Incident, IncidentStatus, PolicyEffect
from forge.domain.state_machine import (
    IllegalIncidentTransition,
    IllegalScenarioTransition,
    transition_incident,
)
from forge.events.ingestion import EventIngestionService
from forge.policies.permissions import PolicyService
from forge.repositories.local_store import LocalStore
from forge.simulator.runner import DemoScenarioRunner
from forge.simulator.seed import build_seed_state
from forge.simulator.seed_service import DemoDataDisabled, SeedService
from forge.telemetry.tracing import TraceRecorder
from forge.tools.actions import ToolExecutor
from forge.tools.scheduling import calculate_production_impact


class Harness:
    def __init__(self, tmp_path: Path):
        self.settings = Settings(
            FORGE_STATE_PATH=tmp_path / "state.json",
            FORGE_MODEL_PROVIDER="TEST_STUB",
            FORGE_ENV="local",
        )
        self.store = LocalStore(self.settings.state_path)
        self.store.reset(build_seed_state(self.settings.gemini_model))
        self.policy = PolicyService(self.store)
        self.tools = ToolExecutor(self.store, self.policy)
        self.traces = TraceRecorder(self.store)
        self.fleet = AgentFleet(
            settings=self.settings,
            store=self.store,
            model_service=DeterministicModelService(),
            policy=self.policy,
            tools=self.tools,
            traces=self.traces,
        )
        self.ingestion = EventIngestionService(store=self.store, fleet=self.fleet, traces=self.traces)
        self.runner = DemoScenarioRunner(store=self.store, ingestion=self.ingestion, tools=self.tools)


def test_incident_state_machine_rejects_illegal_transition(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    harness.runner.run_hero(speed=99, sleep=False)
    incident = Incident.model_validate(harness.store.get("incidents", "INC-1042"))
    assert incident.status == IncidentStatus.AWAITING_APPROVAL
    with pytest.raises(IllegalIncidentTransition):
        transition_incident(incident, IncidentStatus.RESOLVED)


def test_policy_denies_unsafe_and_unprivileged_actions(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    machine_control = harness.policy.evaluate(principal="recovery-agent", action="machine_control")
    assert machine_control.effect == PolicyEffect.DENY
    observer_schedule = harness.policy.evaluate(principal="observer-agent", action="apply_schedule_change")
    assert observer_schedule.effect == PolicyEffect.DENY


def test_schedule_calculator_uses_explicit_numbers(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    work_order = next(wo for wo in harness.store.list("work_orders") if wo["work_order_id"] == "MO-4821")
    machines = harness.store.list("machines")
    impact = calculate_production_impact(
        incident_id="INC-1042",
        work_order=__import__("forge.domain.models", fromlist=["WorkOrder"]).WorkOrder.model_validate(work_order),
        machines=[__import__("forge.domain.models", fromlist=["Machine"]).Machine.model_validate(machine) for machine in machines],
        failed_machine_id="MC-04",
    )
    assert impact.remaining_quantity == 42
    assert any(alt.machine_id == "MC-02" and alt.capable for alt in impact.alternatives)
    assert impact.saved_minutes_if_reassigned > 0


def test_hero_flow_reaches_approval_and_then_learned(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    result = harness.runner.run_hero(speed=99, sleep=False)
    assert result["incident_id"] == "INC-1042"
    incident = harness.store.get("incidents", "INC-1042")
    assert incident["status"] == "AWAITING_APPROVAL"
    assert len(harness.store.list("maintenance_tasks")) == 1
    assert len(harness.store.list("schedule_proposals")) == 1
    harness.tools.apply_schedule_change(
        principal="synthetic-supervisor",
        approval_id="APV-1042",
        trace_id="trc_servo_overload_cascade",
    )
    assert harness.store.get("incidents", "INC-1042")["status"] == "MONITORING"
    assert harness.store.get("work_orders", "MO-4821")["assigned_machine_id"] == "MC-02"
    harness.runner.resolve_maintenance_step()
    assert harness.store.get("incidents", "INC-1042")["status"] == "LEARNED"
    assert len(harness.store.list("memories")) == 1


def test_workflow_dependencies_are_not_left_pending(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    harness.runner.run_hero(speed=99, sleep=False)
    incident = harness.store.get("incidents", "INC-1042")
    workflow = {stage["stage_id"]: stage for stage in incident["workflow"]}
    assert workflow["observer"]["status"] == "SUCCEEDED"
    for stage in workflow.values():
        if stage["status"] not in {"SUCCEEDED", "RECOVERED"}:
            continue
        for dependency in stage["dependencies"]:
            assert workflow[dependency]["status"] != "PENDING"


def test_duplicate_hero_start_is_rejected(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    harness.runner.run_hero(speed=99, sleep=False)
    with pytest.raises((IllegalScenarioTransition, ValueError)):
        harness.runner.run_hero(speed=99, sleep=False)


def test_evidence_is_typed_deduplicated_and_stably_ordered(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    harness.runner.run_hero(speed=99, sleep=False)
    incident = harness.store.get("incidents", "INC-1042")
    evidence = incident["evidence"]
    evidence_ids = [item["evidence_id"] for item in evidence]
    assert len(evidence_ids) == len(set(evidence_ids))
    assert [item["order"] for item in evidence] == sorted(item["order"] for item in evidence)
    assert {"trigger", "precursor_telemetry", "contradictory_evidence", "historical_context"}.issubset(
        {item["evidence_type"] for item in evidence}
    )


def test_rerun_pipeline_does_not_duplicate_evidence_or_actions(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    harness.runner.run_hero(speed=99, sleep=False)
    before_evidence = len(harness.store.get("incidents", "INC-1042")["evidence"])
    before_actions = len(harness.store.list("action_executions"))
    harness.fleet.run_incident_pipeline("INC-1042")
    assert len(harness.store.get("incidents", "INC-1042")["evidence"]) == before_evidence
    assert len(harness.store.list("action_executions")) == before_actions
    assert len(harness.store.list("maintenance_tasks")) == 1
    assert len(harness.store.list("schedule_proposals")) == 1
    assert len(harness.store.list("notifications")) == 1


def test_approval_mutates_schedule_exactly_once(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    harness.runner.run_hero(speed=99, sleep=False)
    first = harness.tools.apply_schedule_change(
        principal="synthetic-supervisor",
        approval_id="APV-1042",
        trace_id="trc_servo_overload_cascade",
    )
    second = harness.tools.apply_schedule_change(
        principal="synthetic-supervisor",
        approval_id="APV-1042",
        trace_id="trc_servo_overload_cascade",
    )
    assert first.proposal_id == second.proposal_id
    assert harness.store.get("work_orders", "MO-4821")["assigned_machine_id"] == "MC-02"
    apply_logs = [
        row for row in harness.store.list("action_executions") if row["action_type"] == "apply_schedule_change"
    ]
    assert len(apply_logs) == 1


def test_prompt_injection_document_is_denied_and_audited(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    harness.runner.enable_security_attack()
    harness.runner.run_hero(speed=99, sleep=False)
    security = harness.store.list("security_events")
    assert any(event["denied_tool"] == "external_http_request" for event in security)
    assert any(event["event_type"] == "PROMPT_INJECTION" and event["decision"] == "BLOCKED" for event in security)
    decisions = harness.store.list("policy_decisions")
    assert any(decision["action"] == "external_http_request" and decision["effect"] == "DENY" for decision in decisions)
    assert harness.store.get("incidents", "INC-1042")["status"] == "AWAITING_APPROVAL"
    incident = harness.store.get("incidents", "INC-1042")
    malicious = [
        ref
        for ref in incident["knowledge_result"]["references"]
        if ref["document_id"] == "MAL-REDTEAM-001"
    ][0]
    assert malicious["excerpt"].startswith("UNTRUSTED RETRIEVED CONTENT")
    assert harness.store.get("work_orders", "MO-4821")["assigned_machine_id"] == "MC-04"


def test_retry_failure_records_recovery_without_duplicate_actions(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    harness.runner.inject_failure("diagnostic-agent")
    harness.runner.run_hero(speed=99, sleep=False)
    runs = [run for run in harness.store.list("agent_runs") if run["agent_id"] == "diagnostic-agent"]
    assert any(run["status"] == "FAILED" for run in runs)
    assert any(run["status"] == "RECOVERED" for run in runs)
    workflow = {stage["agent_id"]: stage for stage in harness.store.get("incidents", "INC-1042")["workflow"]}
    assert workflow["diagnostic-agent"]["status"] == "RECOVERED"
    assert workflow["diagnostic-agent"]["retry_count"] == 1
    assert len(harness.store.list("maintenance_tasks")) == 1
    assert len(harness.store.list("schedule_proposals")) == 1
    evidence_ids = [item["evidence_id"] for item in harness.store.get("incidents", "INC-1042")["evidence"]]
    assert len(evidence_ids) == len(set(evidence_ids))


def test_demo_seed_can_be_disabled_and_reenabled(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    seed = SeedService(store=harness.store, model=harness.settings.gemini_model)
    disabled = seed.disable()
    assert disabled["demo_data_enabled"] is False
    assert disabled["collections"]["machines"] == 0
    with pytest.raises(DemoDataDisabled):
        harness.runner.run_hero(speed=99, sleep=False)
    enabled = seed.import_complete_seed()
    assert enabled["demo_data_enabled"] is True
    assert enabled["collections"]["machines"] == 10
    result = harness.runner.run_hero(speed=99, sleep=False)
    assert result["incident_id"] == "INC-1042"
