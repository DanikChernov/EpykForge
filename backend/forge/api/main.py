from __future__ import annotations

import importlib.util
import shutil
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from forge.agents.fleet import AgentFleet
from forge.agents.model_service import build_model_service
from forge.config.settings import Settings, get_settings
from forge.domain.models import (
    Approval,
    Incident,
    Machine,
    MachineEvent,
    WorkOrder,
)
from forge.domain.state_machine import IllegalScenarioTransition, ScenarioStatus
from forge.events.bus import EventBus, InProcessEventBus
from forge.events.ingestion import EventIngestionService
from forge.policies.permissions import PolicyService
from forge.repositories.local_store import LocalStore
from forge.simulator.runner import HERO_CORRELATION_ID, DemoScenarioRunner
from forge.simulator.seed_service import DemoDataDisabled, SeedService
from forge.telemetry.logging import configure_logging
from forge.telemetry.tracing import TraceRecorder
from forge.tools.actions import ToolExecutor


class StartDemoRequest(BaseModel):
    sync: bool = False
    speed: float | None = None


class ApprovalRequest(BaseModel):
    approval_id: str | None = None
    decision_note: str = "Approved for synthetic hackathon demo"


class RejectRequest(BaseModel):
    approval_id: str | None = None
    decision_note: str = "Rejected by synthetic supervisor"


class AdminGeminiSmokeOutput(BaseModel):
    status: str
    model: str
    summary: str
    confidence: float


class ServiceBundle(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    settings: Settings
    store: Any
    policy: PolicyService
    tools: ToolExecutor
    traces: TraceRecorder
    event_bus: EventBus
    fleet: AgentFleet
    ingestion: EventIngestionService
    runner: DemoScenarioRunner
    seed: SeedService


def build_services(settings: Settings) -> ServiceBundle:
    if settings.store_backend == "firestore":
        from forge.repositories.firestore_store import FirestoreStore

        store = FirestoreStore(project=settings.google_cloud_project)
    else:
        store = LocalStore(settings.state_path)
    policy = PolicyService(store)
    tools = ToolExecutor(store, policy)
    traces = TraceRecorder(store)
    seed = SeedService(store=store, model=settings.gemini_model)
    if not store.get("scenario_state", "default"):
        if settings.demo_data_enabled:
            seed.import_complete_seed()
        else:
            seed.disable()
    if settings.event_bus == "pubsub":
        from forge.events.pubsub_bus import PubSubEventBus

        if not settings.google_cloud_project:
            raise RuntimeError("FORGE_EVENT_BUS=pubsub requires GOOGLE_CLOUD_PROJECT")
        event_bus: EventBus = PubSubEventBus(project_id=settings.google_cloud_project)
    else:
        event_bus = InProcessEventBus()
    model_service = build_model_service(settings)
    fleet = AgentFleet(
        settings=settings,
        store=store,
        model_service=model_service,
        policy=policy,
        tools=tools,
        traces=traces,
    )
    ingestion = EventIngestionService(store=store, fleet=fleet, traces=traces)
    if isinstance(event_bus, InProcessEventBus):
        event_bus.subscribe("factory-events", ingestion.ingest)
    runner = DemoScenarioRunner(store=store, ingestion=ingestion, tools=tools)
    return ServiceBundle(
        settings=settings,
        store=store,
        policy=policy,
        tools=tools,
        traces=traces,
        event_bus=event_bus,
        fleet=fleet,
        ingestion=ingestion,
        runner=runner,
        seed=seed,
    )


settings = get_settings()
configure_logging(settings.environment)
services = build_services(settings)

app = FastAPI(title="EPYK Forge API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def _require_supervisor_token(x_demo_token: str | None) -> None:
    if x_demo_token != services.settings.demo_supervisor_token:
        raise HTTPException(status_code=401, detail="Missing or invalid synthetic supervisor token")


def _require_admin_pin(x_admin_pin: str | None) -> None:
    if x_admin_pin != services.settings.admin_pin:
        raise HTTPException(status_code=401, detail="Missing or invalid admin PIN")


def _state() -> dict[str, Any]:
    return services.store.read_state()


def _module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, Any]:
    state = _state()
    return {
        "status": "ready" if state.get("machines") else "not_ready",
        "store_backend": services.settings.store_backend,
        "model_provider": services.fleet.model_service.provider_name,
        "adk_available": services.fleet.adk_status.available,
    }


@app.get("/api/system/info")
def system_info() -> dict[str, Any]:
    cloud = services.settings.running_on_google_cloud
    managed_flags = {
        "agent_runtime": False,
        "memory_bank": False,
        "agent_registry": False,
        "agent_identity": False,
        "agent_gateway": False,
        "model_armor": False,
        "agent_observability": bool(cloud),
    }
    return {
        "product": "EPYK Forge",
        "synthetic_facility": "Northstar Precision Works",
        "environment": "google-cloud" if cloud else "local",
        "service": services.settings.service_name,
        "region": services.settings.cloud_run_region if cloud else None,
        "google_cloud_location": services.settings.google_cloud_location,
        "revision": services.settings.cloud_run_revision,
        "web_origin": services.settings.forge_web_origin,
        "model": services.settings.gemini_model,
        "model_provider": services.fleet.model_service.provider_name,
        "agent_framework": "Google ADK",
        "adk_status": services.fleet.adk_status.message,
        "event_bus": "Google Pub/Sub" if services.settings.event_bus == "pubsub" else "in-process event bus",
        "state_store": "Google Firestore" if services.settings.store_backend == "firestore" else "local JSON store",
        "managed_agent_platform": managed_flags,
        "cloud_claim_active": cloud,
    }


@app.get("/api/admin/setup/status")
def admin_setup_status(x_admin_pin: str | None = Header(default=None)) -> dict[str, Any]:
    _require_admin_pin(x_admin_pin)
    seed_status = services.seed.status()
    model_provider = services.fleet.model_service.provider_name
    google_project = services.settings.google_cloud_project
    return {
        "admin": {"authenticated": True, "pin_configured": bool(services.settings.admin_pin)},
        "runtime": {
            "environment": services.settings.environment,
            "service": services.settings.service_name,
            "store_backend": services.settings.store_backend,
            "event_bus": services.settings.event_bus,
            "running_on_google_cloud": services.settings.running_on_google_cloud,
        },
        "gemini": {
            "model_provider": model_provider,
            "model": services.settings.gemini_model,
            "real_gemini_enabled": model_provider == "REAL_GEMINI",
            "google_cloud_project": google_project,
            "google_cloud_project_configured": bool(google_project),
            "google_cloud_location": services.settings.google_cloud_location,
            "google_genai_use_enterprise": services.settings.google_genai_use_enterprise,
            "adk_available": services.fleet.adk_status.available,
            "adk_status": services.fleet.adk_status.message,
            "google_adk_importable": _module_available("google.adk"),
            "google_genai_importable": _module_available("google.genai"),
            "gcloud_on_path": shutil.which("gcloud") is not None,
            "smoke_test_required": model_provider == "REAL_GEMINI",
        },
        "seed": seed_status,
        "actions": {
            "import_seed": "/api/admin/seed/import",
            "enable_seed": "/api/admin/seed/enable",
            "disable_seed": "/api/admin/seed/disable",
            "gemini_smoke": "/api/admin/gemini/smoke",
        },
    }


@app.get("/api/admin/seed/preview")
def admin_seed_preview(x_admin_pin: str | None = Header(default=None)) -> dict[str, Any]:
    _require_admin_pin(x_admin_pin)
    return {
        "status": services.seed.status(),
        "machines": services.store.list("machines"),
        "work_orders": services.store.list("work_orders"),
        "knowledge_documents": services.store.list("knowledge_documents"),
        "agent_registry": services.store.list("agent_registry"),
        "scenario_state": services.store.list("scenario_state"),
    }


@app.post("/api/admin/seed/import")
def admin_seed_import(x_admin_pin: str | None = Header(default=None)) -> dict[str, Any]:
    _require_admin_pin(x_admin_pin)
    return services.seed.import_complete_seed() | {"status": "imported"}


@app.post("/api/admin/seed/enable")
def admin_seed_enable(x_admin_pin: str | None = Header(default=None)) -> dict[str, Any]:
    _require_admin_pin(x_admin_pin)
    return services.seed.enable() | {"status": "enabled"}


@app.post("/api/admin/seed/disable")
def admin_seed_disable(x_admin_pin: str | None = Header(default=None)) -> dict[str, Any]:
    _require_admin_pin(x_admin_pin)
    return services.seed.disable() | {"status": "disabled"}


@app.post("/api/admin/gemini/smoke")
def admin_gemini_smoke(x_admin_pin: str | None = Header(default=None)) -> dict[str, Any]:
    _require_admin_pin(x_admin_pin)
    if services.fleet.model_service.provider_name != "REAL_GEMINI":
        return {
            "status": "skipped",
            "reason": "FORGE_MODEL_PROVIDER is not REAL_GEMINI",
            "current_provider": services.fleet.model_service.provider_name,
            "required_env": {
                "FORGE_MODEL_PROVIDER": "REAL_GEMINI",
                "FORGE_GEMINI_MODEL": "gemini-3.5-flash",
                "GOOGLE_GENAI_USE_ENTERPRISE": "True",
                "GOOGLE_CLOUD_PROJECT": "your-project",
                "GOOGLE_CLOUD_LOCATION": "global",
            },
        }
    output = services.fleet.model_service.generate_structured(
        agent_id="admin-setup",
        system_prompt=(
            "You are an EPYK Forge setup verifier. Return a concise JSON health result. "
            "Do not mention hidden reasoning."
        ),
        input_payload={
            "task": "Verify Gemini model connectivity for EPYK Forge setup.",
            "model": services.settings.gemini_model,
            "synthetic_facility": "Northstar Precision Works",
        },
        output_model=AdminGeminiSmokeOutput,
    )
    return output.model_dump(mode="json")


@app.get("/api/facility")
def facility() -> dict[str, Any]:
    machines = [Machine.model_validate(raw) for raw in services.store.list("machines")]
    work_orders = [WorkOrder.model_validate(raw) for raw in services.store.list("work_orders")]
    incidents = [Incident.model_validate(raw) for raw in services.store.list("incidents")]
    active_incidents = [item for item in incidents if item.status.value not in {"LEARNED", "CANCELLED"}]
    return {
        "facility_name": "Northstar Precision Works",
        "synthetic": True,
        "health_score": int(sum(machine.health_score for machine in machines) / max(len(machines), 1)),
        "machines_total": len(machines),
        "machines_running": sum(1 for machine in machines if machine.state.value == "RUNNING"),
        "machines_idle": sum(1 for machine in machines if machine.state.value == "IDLE"),
        "machines_alarmed": sum(1 for machine in machines if machine.state.value == "ALARM"),
        "machines_maintenance": sum(1 for machine in machines if machine.state.value == "MAINTENANCE"),
        "active_incidents": len(active_incidents),
        "at_risk_orders": sum(1 for wo in work_orders if wo.risk.value in {"HIGH", "CRITICAL"}),
        "agent_fleet_status": "ACTIVE",
        "model_provider": services.fleet.model_service.provider_name,
    }


@app.get("/api/machines")
def machines() -> list[dict[str, Any]]:
    return services.store.list("machines")


@app.get("/api/machines/{machine_id}")
def machine(machine_id: str) -> dict[str, Any]:
    raw = services.store.get("machines", machine_id)
    if not raw:
        raise HTTPException(status_code=404, detail="Machine not found")
    events = [event for event in services.store.list("events") if event.get("machine_id") == machine_id][-30:]
    incidents = [item for item in services.store.list("incidents") if item.get("machine_id") == machine_id]
    return raw | {"events": events, "incidents": incidents}


@app.get("/api/work-orders")
def work_orders() -> list[dict[str, Any]]:
    return services.store.list("work_orders")


@app.get("/api/events")
def events(machine_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    rows = services.store.list("events")
    if machine_id:
        rows = [row for row in rows if row.get("machine_id") == machine_id]
    return rows[-limit:]


@app.get("/api/incidents")
def incidents() -> list[dict[str, Any]]:
    return services.store.list("incidents")


@app.get("/api/incidents/{incident_id}")
def incident(incident_id: str) -> dict[str, Any]:
    raw = services.store.get("incidents", incident_id)
    if not raw:
        raise HTTPException(status_code=404, detail="Incident not found")
    approvals = [row for row in services.store.list("approvals") if row.get("incident_id") == incident_id]
    actions = [row for row in services.store.list("action_executions") if row.get("incident_id") == incident_id]
    runs = sorted(
        [row for row in services.store.list("agent_runs") if row.get("incident_id") == incident_id],
        key=lambda row: (row.get("started_at", ""), row.get("completed_at", ""), row.get("run_id", "")),
    )
    traces = [row for row in services.store.list("traces") if row.get("correlation_id") == raw.get("correlation_id")]
    proposals = [
        row for row in services.store.list("schedule_proposals") if row.get("incident_id") == incident_id
    ]
    return raw | {
        "approvals": approvals,
        "action_log": sorted(actions, key=lambda row: row.get("timestamp", "")),
        "agent_runs": runs,
        "trace_spans": traces,
        "schedule_proposals": proposals,
    }


@app.get("/api/agents")
def agents() -> list[dict[str, Any]]:
    runs = services.store.list("agent_runs")
    result = []
    for manifest in services.store.list("agent_registry"):
        agent_runs = sorted(
            [run for run in runs if run.get("agent_id") == manifest.get("agent_id")],
            key=lambda row: (row.get("started_at", ""), row.get("completed_at", ""), row.get("run_id", "")),
        )
        latest = agent_runs[-1] if agent_runs else None
        result.append(
            manifest
            | {
                "current_task": latest.get("incident_id") if latest else None,
                "last_execution": latest.get("completed_at") if latest else None,
                "latest_status": latest.get("status") if latest else "IDLE",
                "successful_executions": sum(1 for run in agent_runs if run.get("status") in {"SUCCEEDED", "RECOVERED"}),
                "failures": sum(1 for run in agent_runs if run.get("status") == "FAILED"),
                "latency_ms": latest.get("duration_ms") if latest else None,
                "health": "DEGRADED" if latest and latest.get("status") == "FAILED" else "HEALTHY",
            }
        )
    return result


@app.get("/api/registry")
def registry() -> list[dict[str, Any]]:
    return services.store.list("agent_registry")


@app.get("/api/traces")
def traces(incident_id: str | None = None, agent_id: str | None = None) -> list[dict[str, Any]]:
    rows = services.store.list("traces")
    if incident_id:
        incident_raw = services.store.get("incidents", incident_id)
        if not incident_raw:
            return []
        rows = [row for row in rows if row.get("correlation_id") == incident_raw.get("correlation_id")]
    if agent_id:
        rows = [row for row in rows if row.get("agent_id") == agent_id]
    return rows


@app.get("/api/security/events")
def security_events() -> list[dict[str, Any]]:
    return services.store.list("security_events")


@app.get("/api/notifications")
def notifications() -> list[dict[str, Any]]:
    return services.store.list("notifications")


@app.get("/api/approvals")
def approvals() -> list[dict[str, Any]]:
    return services.store.list("approvals")


@app.post("/api/events")
def post_event(event: MachineEvent) -> dict[str, Any]:
    return services.ingestion.ingest(event)


@app.post("/api/demo/reset")
def reset_demo() -> dict[str, Any]:
    return services.seed.import_complete_seed() | {"status": "reset", "incident_id": None}


@app.get("/api/demo/seed/status")
def demo_seed_status() -> dict[str, Any]:
    return services.seed.status()


@app.post("/api/demo/seed/import")
def import_demo_seed() -> dict[str, Any]:
    return services.seed.import_complete_seed() | {"status": "imported"}


@app.post("/api/demo/seed/enable")
def enable_demo_seed() -> dict[str, Any]:
    return services.seed.enable() | {"status": "enabled"}


@app.post("/api/demo/seed/disable")
def disable_demo_seed() -> dict[str, Any]:
    return services.seed.disable() | {"status": "disabled"}


@app.post("/api/demo/start")
def start_demo(payload: StartDemoRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    speed = payload.speed or services.settings.demo_speed
    try:
        if payload.sync:
            return services.runner.run_hero(speed=speed, sleep=False)
        services.seed.require_enabled()
        scenario = services.store.get("scenario_state", "default") or {}
        if scenario.get("status") != ScenarioStatus.READY.value:
            raise IllegalScenarioTransition(
                f"Start Scenario requires {ScenarioStatus.READY.value}; current state is {scenario.get('status')}"
            )
        active = [
            incident
            for incident in services.store.list("incidents")
            if incident.get("status") not in {"LEARNED", "FAILED", "ESCALATED", "CANCELLED"}
        ]
        if active:
            raise ValueError("Reset the demo before starting another hero scenario")
        background_tasks.add_task(services.runner.run_hero, speed=speed, sleep=True)
        return {"status": "started", "correlation_id": HERO_CORRELATION_ID}
    except DemoDataDisabled as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (IllegalScenarioTransition, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/demo/inject/{event_name}")
def inject_demo_event(event_name: str) -> dict[str, Any]:
    try:
        if event_name == "servo_alarm":
            return services.runner.inject_servo_alarm()
        if event_name == "security_attack":
            return services.runner.run_security_test()
        if event_name == "failure":
            return services.runner.run_retry_test()
        if event_name == "maintenance_resolved":
            return services.runner.resolve_maintenance_step()
        raise HTTPException(status_code=404, detail=f"Unknown demo event {event_name}")
    except DemoDataDisabled as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (IllegalScenarioTransition, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _approval_for_incident(incident_id: str, approval_id: str | None) -> Approval:
    if approval_id:
        raw = services.store.get("approvals", approval_id)
        if not raw:
            raise HTTPException(status_code=404, detail="Approval not found")
        return Approval.model_validate(raw)
    approvals = [
        Approval.model_validate(row)
        for row in services.store.list("approvals")
        if row.get("incident_id") == incident_id and row.get("status") == "PROPOSED"
    ]
    if not approvals:
        raise HTTPException(status_code=404, detail="No pending approval for incident")
    return approvals[0]


@app.post("/api/incidents/{incident_id}/approve")
def approve_incident(
    incident_id: str,
    payload: ApprovalRequest,
    x_demo_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_supervisor_token(x_demo_token)
    approval = _approval_for_incident(incident_id, payload.approval_id)
    proposal = services.tools.apply_schedule_change(
        principal="synthetic-supervisor",
        approval_id=approval.approval_id,
        trace_id=HERO_CORRELATION_ID,
        decision_note=payload.decision_note,
    )
    return {"status": "approved", "proposal": proposal.model_dump(mode="json")}


@app.post("/api/incidents/{incident_id}/reject")
def reject_incident(
    incident_id: str,
    payload: RejectRequest,
    x_demo_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_supervisor_token(x_demo_token)
    approval = _approval_for_incident(incident_id, payload.approval_id)
    rejected = services.tools.reject_schedule_change(
        principal="synthetic-supervisor",
        approval_id=approval.approval_id,
        trace_id=HERO_CORRELATION_ID,
        decision_note=payload.decision_note,
    )
    return {"status": "rejected", "approval": rejected.model_dump(mode="json")}


@app.get("/api/state")
def state_snapshot() -> dict[str, Any]:
    return _state()
