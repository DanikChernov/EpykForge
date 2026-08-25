import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ClipboardCheck,
  Database,
  Factory,
  KeyRound,
  Lock,
  Play,
  RadioTower,
  RotateCcw,
  Server,
  Settings,
  ShieldCheck,
  Workflow,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import type {
  AgentManifest,
  AdminSeedPreview,
  AdminSetupStatus,
  Approval,
  DemoSeedStatus,
  Facility,
  Incident,
  Machine,
  SecurityEvent,
  SystemInfo,
  TraceSpan,
} from "./types";

type View = "overview" | "factory" | "incident" | "fleet" | "registry" | "security" | "observability" | "cloud" | "admin";
type Filter = "ALL" | "RUNNING" | "IDLE" | "ALARM" | "MAINTENANCE" | "AT_RISK";

interface Snapshot {
  facility?: Facility;
  machines: Machine[];
  incidents: Incident[];
  activeIncident?: Incident;
  agents: AgentManifest[];
  registry: AgentManifest[];
  security: SecurityEvent[];
  traces: TraceSpan[];
  approvals: Approval[];
  system?: SystemInfo;
  demoSeed?: DemoSeedStatus;
}

const initialSnapshot: Snapshot = {
  machines: [],
  incidents: [],
  agents: [],
  registry: [],
  security: [],
  traces: [],
  approvals: [],
};

function cls(...items: Array<string | false | null | undefined>) {
  return items.filter(Boolean).join(" ");
}

function severityClass(value?: string) {
  if (!value) return "neutral";
  return value.toLowerCase();
}

function stateClass(value: string) {
  return value.toLowerCase().replace("_", "-");
}

function formatTime(value?: string | null) {
  if (!value) return "never";
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

function Sparkline({ samples }: { samples: Machine["telemetry_history"] }) {
  const points = samples.slice(-18);
  if (!points.length) return <div className="sparkline empty" />;
  const max = 100;
  const width = 180;
  const height = 56;
  const path = points
    .map((sample, index) => {
      const x = points.length === 1 ? 0 : (index / (points.length - 1)) * width;
      const y = height - (sample.x_axis_load_pct / max) * height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg className="sparkline" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="X axis load trend">
      <polyline points={path} fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      <line x1="0" x2={width} y1="8" y2="8" className="limit-line" />
    </svg>
  );
}

function MetricCard({ label, value, tone }: { label: string; value: string | number; tone?: string }) {
  return (
    <div className={cls("metric", tone)}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function DemoControls({
  busy,
  onAction,
  demoSeed,
}: {
  busy: boolean;
  onAction: (name: string) => void;
  demoSeed?: DemoSeedStatus;
}) {
  const enabled = demoSeed?.demo_data_enabled ?? false;
  return (
    <section className="control-band" aria-label="Synthetic demo controls">
      <div>
        <p className="eyebrow">SYNTHETIC DEMO CONTROLS</p>
        <h2>Servo Overload Cascade</h2>
        <span className={cls("seed-status", enabled ? "enabled" : "disabled")}>
          Seed data {enabled ? "enabled" : "disabled"} · {demoSeed?.collections.machines ?? 0} machines
        </span>
      </div>
      <div className="control-actions">
        <button type="button" onClick={() => onAction("import_seed")} disabled={busy} title="Import complete demo seed data">
          <Database size={18} /> Import Seed
        </button>
        <button type="button" onClick={() => onAction(enabled ? "disable_seed" : "enable_seed")} disabled={busy} title="Enable or disable seed data">
          <ShieldCheck size={18} /> {enabled ? "Disable Seed" : "Enable Seed"}
        </button>
        <button type="button" onClick={() => onAction("reset")} disabled={busy} title="Reset demo">
          <RotateCcw size={18} /> Reset
        </button>
        <button type="button" onClick={() => onAction("security_attack")} disabled={busy || !enabled} title="Enable injection document retrieval">
          <ShieldCheck size={18} /> Security Test
        </button>
        <button type="button" onClick={() => onAction("failure")} disabled={busy || !enabled} title="Force one retryable agent failure">
          <RadioTower size={18} /> Retry Test
        </button>
        <button type="button" className="primary" onClick={() => onAction("start")} disabled={busy || !enabled} title="Start hero scenario">
          <Play size={18} /> Start Scenario
        </button>
        <button type="button" onClick={() => onAction("servo_alarm")} disabled={busy || !enabled} title="Inject servo alarm">
          <AlertTriangle size={18} /> Servo Alarm
        </button>
        <button type="button" onClick={() => onAction("maintenance_resolved")} disabled={busy || !enabled} title="Resolve maintenance step">
          <CheckCircle2 size={18} /> Resolve
        </button>
      </div>
    </section>
  );
}

function MachineCard({ machine, onSelect }: { machine: Machine; onSelect: (machine: Machine) => void }) {
  return (
    <button type="button" className={cls("machine-card", stateClass(machine.state), machine.at_risk && "risk")} onClick={() => onSelect(machine)}>
      <div className="machine-top">
        <div>
          <strong>{machine.machine_id}</strong>
          <span>{machine.cell}</span>
        </div>
        <span className={cls("pill", stateClass(machine.state))}>{machine.state}</span>
      </div>
      <div className="machine-job">
        <span>{machine.current_work_order_id ?? "No active work order"}</span>
        <strong>{machine.current_operation ?? machine.model}</strong>
      </div>
      <Sparkline samples={machine.telemetry_history} />
      <div className="machine-stats">
        <span>Cycle {Math.round(machine.telemetry.observed_cycle_time_sec)}s / {Math.round(machine.telemetry.target_cycle_time_sec)}s</span>
        <span>X Load {Math.round(machine.telemetry.x_axis_load_pct)}%</span>
      </div>
    </button>
  );
}

function Overview({ snapshot, onAction, busy, setView }: { snapshot: Snapshot; onAction: (name: string) => void; busy: boolean; setView: (view: View) => void }) {
  const facility = snapshot.facility;
  const mc04 = snapshot.machines.find((machine) => machine.machine_id === "MC-04");
  const incident = snapshot.activeIncident;
  return (
    <main className="view">
      <DemoControls busy={busy} onAction={onAction} demoSeed={snapshot.demoSeed} />
      <section className="metrics-grid">
        <MetricCard label="Facility Health" value={facility?.health_score ?? "-"} tone="cyan" />
        <MetricCard label="Running" value={facility?.machines_running ?? 0} />
        <MetricCard label="Idle" value={facility?.machines_idle ?? 0} />
        <MetricCard label="Alarmed" value={facility?.machines_alarmed ?? 0} tone="red" />
        <MetricCard label="Active Incidents" value={facility?.active_incidents ?? 0} tone="amber" />
        <MetricCard label="At-Risk Orders" value={facility?.at_risk_orders ?? 0} tone="amber" />
      </section>
      <section className="split">
        <div className="panel">
          <div className="panel-header">
            <h2>Operations Overview</h2>
            <span className="model-badge">{facility?.model_provider ?? "unknown"}</span>
          </div>
          <div className="machine-grid compact">
            {snapshot.machines.slice(0, 6).map((machine) => (
              <MachineCard key={machine.machine_id} machine={machine} onSelect={() => setView("factory")} />
            ))}
          </div>
        </div>
        <div className="panel command-preview">
          <div className="panel-header">
            <h2>Incident Command</h2>
            {incident ? <span className={cls("pill", severityClass(incident.severity))}>{incident.severity}</span> : <span className="pill neutral">standby</span>}
          </div>
          {incident ? (
            <button type="button" className="incident-button" onClick={() => setView("incident")}>
              <strong>{incident.incident_id}</strong>
              <span>{incident.title}</span>
              <small>{incident.machine_id} · {incident.work_order_id}</small>
              <span className={cls("status-line", stateClass(incident.status))}>{incident.status}</span>
            </button>
          ) : (
            <div className="empty-state">No active incident</div>
          )}
          {mc04 && (
            <div className="mc04-strip">
              <span>MC-04</span>
              <strong>{mc04.state}</strong>
              <span>MO-4821</span>
              <span>{Math.round(mc04.telemetry.x_axis_load_pct)}% X load</span>
            </div>
          )}
        </div>
      </section>
    </main>
  );
}

function FactoryView({ machines }: { machines: Machine[] }) {
  const [filter, setFilter] = useState<Filter>("ALL");
  const [selected, setSelected] = useState<Machine | undefined>();
  const filtered = machines.filter((machine) => {
    if (filter === "ALL") return true;
    if (filter === "AT_RISK") return machine.at_risk;
    return machine.state === filter;
  });
  const active = selected ?? machines.find((machine) => machine.machine_id === "MC-04") ?? machines[0];
  return (
    <main className="view">
      <section className="toolbar">
        {(["ALL", "RUNNING", "IDLE", "ALARM", "MAINTENANCE", "AT_RISK"] as Filter[]).map((item) => (
          <button key={item} type="button" className={filter === item ? "selected" : ""} onClick={() => setFilter(item)}>
            {item.replace("_", " ")}
          </button>
        ))}
      </section>
      <section className="machine-grid">
        {filtered.map((machine) => (
          <MachineCard key={machine.machine_id} machine={machine} onSelect={setSelected} />
        ))}
      </section>
      {active && (
        <section className="panel detail-panel">
          <div>
            <p className="eyebrow">{active.machine_type}</p>
            <h2>{active.machine_id} · {active.model}</h2>
          </div>
          <div className="detail-grid">
            <MetricCard label="State" value={active.state} tone={active.state === "ALARM" ? "red" : undefined} />
            <MetricCard label="Health" value={active.health_score} />
            <MetricCard label="Work Order" value={active.current_work_order_id ?? "None"} />
            <MetricCard label="X Axis Load" value={`${Math.round(active.telemetry.x_axis_load_pct)}%`} tone="cyan" />
          </div>
          <Sparkline samples={active.telemetry_history} />
        </section>
      )}
    </main>
  );
}

const workflowOrder = [
  ["observer-agent", "Observer"],
  ["diagnostic-agent", "Diagnostic"],
  ["knowledge-agent", "Knowledge"],
  ["production-agent", "Production"],
  ["recovery-agent", "Recovery"],
  ["supervisor-agent", "Supervisor"],
] as const;

function IncidentCommand({ incident, approvals, onApprove, onReject }: { incident?: Incident; approvals: Approval[]; onApprove: (approvalId?: string) => void; onReject: (approvalId?: string) => void }) {
  if (!incident) {
    return <main className="view"><div className="empty-state tall">No incident is active</div></main>;
  }
  const pending = approvals.find((approval) => approval.incident_id === incident.incident_id && approval.status === "PROPOSED");
  return (
    <main className="view incident-view">
      <section className="incident-header">
        <div>
          <p className="eyebrow">{incident.machine_id} · {incident.work_order_id}</p>
          <h1>{incident.incident_id}</h1>
          <h2>{incident.title}</h2>
        </div>
        <div className="incident-status">
          <span className={cls("pill", severityClass(incident.severity))}>{incident.severity}</span>
          <strong>{incident.status}</strong>
        </div>
      </section>
      <section className="workflow">
        {workflowOrder.map(([agentId, label]) => {
          const run = incident.agent_runs?.find((item) => item.agent_id === agentId);
          return (
            <div key={agentId} className={cls("workflow-step", run?.status.toLowerCase() ?? "pending")}>
              {run?.status === "FAILED" ? <XCircle size={20} /> : run ? <CheckCircle2 size={20} /> : <Activity size={20} />}
              <strong>{label}</strong>
              <span>{run?.status ?? "PENDING"}</span>
              {run?.error && <small>{run.error}</small>}
            </div>
          );
        })}
      </section>
      <section className="incident-grid">
        <div className="panel">
          <h2>Evidence</h2>
          <div className="list">
            {incident.evidence.map((item, index) => (
              <div key={`${item.title}-${index}`} className="list-row">
                <strong>{item.title}</strong>
                <span>{item.summary}</span>
                <small>{item.kind} · {Math.round(item.confidence * 100)}%</small>
              </div>
            ))}
          </div>
        </div>
        <div className="panel">
          <h2>Diagnosis</h2>
          {incident.diagnosis ? (
            <div className="list">
              <p>{incident.diagnosis.summary}</p>
              {incident.diagnosis.probable_causes.map((cause) => (
                <div key={cause.cause} className="list-row">
                  <strong>{Math.round(cause.confidence * 100)}% · {cause.cause}</strong>
                  <span>{cause.contradictions.join(" · ")}</span>
                </div>
              ))}
            </div>
          ) : <div className="empty-state">Pending</div>}
        </div>
        <div className="panel">
          <h2>Knowledge</h2>
          <div className="list">
            {incident.knowledge_result?.references.map((ref) => (
              <div key={ref.document_id} className={cls("list-row", ref.injection_risk && "security-risk")}>
                <strong>{ref.document_id} · {ref.title}</strong>
                <span>{ref.excerpt}</span>
                <small>{ref.document_type} · approved={String(ref.approved)} · {Math.round(ref.relevance_confidence * 100)}%</small>
              </div>
            )) ?? <div className="empty-state">Pending</div>}
          </div>
        </div>
        <div className="panel">
          <h2>Production Impact</h2>
          {incident.production_impact ? (
            <div className="impact">
              <MetricCard label="Remaining" value={incident.production_impact.remaining_quantity} />
              <MetricCard label="Downtime" value={`${incident.production_impact.estimated_downtime_minutes} min`} />
              <MetricCard label="Delivery Risk" value={incident.production_impact.delivery_risk} tone="amber" />
              <MetricCard label="Saved" value={`${incident.production_impact.saved_minutes_if_reassigned} min`} tone="cyan" />
              <p>{incident.production_impact.recommendation}</p>
            </div>
          ) : <div className="empty-state">Pending</div>}
        </div>
        <div className="panel">
          <h2>Recovery Plan</h2>
          {incident.recovery_plan ? (
            <ol className="steps">
              {incident.recovery_plan.steps.map((step) => <li key={step}>{step}</li>)}
            </ol>
          ) : <div className="empty-state">Pending</div>}
        </div>
        <div className="panel approval-panel">
          <h2>Approval Gate</h2>
          {pending ? (
            <>
              <div className="approval-copy">
                <strong>Schedule Change Proposed</strong>
                <span>MO-4821 remaining pieces require supervisor approval before reassignment.</span>
              </div>
              <div className="approval-actions">
                <button type="button" className="primary" onClick={() => onApprove(pending.approval_id)}><CheckCircle2 size={18} /> Approve</button>
                <button type="button" onClick={() => onReject(pending.approval_id)}><XCircle size={18} /> Reject</button>
              </div>
            </>
          ) : (
            <div className="empty-state">No pending approval</div>
          )}
        </div>
      </section>
      <section className="panel">
        <h2>Action Log</h2>
        <div className="table">
          {(incident.action_log ?? []).map((action) => (
            <div key={action.execution_id} className="table-row">
              <span>{formatTime(action.timestamp)}</span>
              <strong>{action.action_type}</strong>
              <span>{action.principal}</span>
              <span>{action.summary}</span>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}

function AgentFleetView({ agents }: { agents: AgentManifest[] }) {
  return (
    <main className="view">
      <section className="agent-grid">
        {agents.map((agent) => (
          <div className="panel agent-card" key={agent.agent_id}>
            <div className="panel-header">
              <div>
                <h2>{agent.agent_id}</h2>
                <span>{agent.version} · {agent.model}</span>
              </div>
              <span className={cls("pill", agent.health === "DEGRADED" && "critical")}>{agent.latest_status ?? agent.status}</span>
            </div>
            <p>{agent.role}</p>
            <div className="detail-grid">
              <MetricCard label="Success" value={agent.successful_executions ?? 0} />
              <MetricCard label="Failures" value={agent.failures ?? 0} tone={agent.failures ? "red" : undefined} />
              <MetricCard label="Latency" value={agent.latency_ms ? `${agent.latency_ms} ms` : "-"} />
            </div>
            <div className="tool-list">
              {agent.allowed_tools.slice(0, 5).map((tool) => <span key={tool}>✓ {tool}</span>)}
              {agent.denied_tools.slice(0, 3).map((tool) => <span key={tool} className="denied">✗ {tool}</span>)}
            </div>
          </div>
        ))}
      </section>
    </main>
  );
}

function RegistryView({ registry }: { registry: AgentManifest[] }) {
  return (
    <main className="view">
      <section className="panel">
        <h2>Agent Registry</h2>
        <div className="table registry-table">
          {registry.map((agent) => (
            <div key={agent.agent_id} className="table-row">
              <strong>{agent.agent_id}</strong>
              <span>{agent.owner}</span>
              <span>{agent.runtime}</span>
              <span>{agent.identity}</span>
              <span>{agent.policy_scope.join(", ")}</span>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}

function SecurityView({ events }: { events: SecurityEvent[] }) {
  return (
    <main className="view">
      <section className="panel">
        <div className="panel-header">
          <h2>Security Center</h2>
          <span className="model-badge">{events.length} events</span>
        </div>
        <div className="list">
          {events.map((event) => (
            <div key={event.security_event_id} className="list-row security-risk">
              <strong>{event.title}</strong>
              <span>{event.description}</span>
              <small>{event.category} · {event.principal} · {event.denied_tool ?? "classified"}</small>
            </div>
          ))}
          {!events.length && <div className="empty-state">No security events recorded</div>}
        </div>
      </section>
    </main>
  );
}

function ObservabilityView({ traces, incident }: { traces: TraceSpan[]; incident?: Incident }) {
  const visible = incident ? traces.filter((span) => span.correlation_id === incident.correlation_id) : traces;
  return (
    <main className="view">
      <section className="panel trace-panel">
        <div className="panel-header">
          <h2>Decision Trace</h2>
          <span className="model-badge">{incident?.correlation_id ?? "all traces"}</span>
        </div>
        <div className="trace-list">
          {visible.map((span) => (
            <div key={span.span_id} className={cls("trace-span", span.status.toLowerCase())}>
              <span>{formatTime(span.started_at)}</span>
              <strong>{span.name}</strong>
              <small>{span.agent_id ?? "system"} · {span.duration_ms ?? 0} ms · {span.status}</small>
            </div>
          ))}
          {!visible.length && <div className="empty-state">No spans recorded</div>}
        </div>
      </section>
    </main>
  );
}

function CloudView({ system }: { system?: SystemInfo }) {
  return (
    <main className="view">
      <section className="panel cloud-panel">
        <div className="panel-header">
          <h2>Google Cloud Proof</h2>
          <span className={cls("pill", system?.cloud_claim_active ? "running" : "neutral")}>{system?.environment ?? "unknown"}</span>
        </div>
        {system && (
          <div className="cloud-grid">
            <MetricCard label="Model" value={system.model} tone="cyan" />
            <MetricCard label="Provider" value={system.model_provider} />
            <MetricCard label="Agent Framework" value={system.agent_framework} />
            <MetricCard label="Event Bus" value={system.event_bus} />
            <MetricCard label="State Store" value={system.state_store} />
            <MetricCard label="Service" value={system.service} />
          </div>
        )}
        <div className="managed-grid">
          {Object.entries(system?.managed_agent_platform ?? {}).map(([key, value]) => (
            <div key={key} className={cls("managed-item", value && "active")}>
              <span>{key.replaceAll("_", " ")}</span>
              <strong>{value ? "ACTIVE" : "FALLBACK"}</strong>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}

function SetupCheck({ label, ok, detail }: { label: string; ok: boolean; detail: string }) {
  return (
    <div className={cls("setup-check", ok ? "ok" : "needs-work")}>
      {ok ? <CheckCircle2 size={18} /> : <AlertTriangle size={18} />}
      <div>
        <strong>{label}</strong>
        <span>{detail}</span>
      </div>
    </div>
  );
}

function AdminPanel({ onPlatformChange }: { onPlatformChange: () => Promise<void> }) {
  const [pin, setPin] = useState("");
  const [authenticatedPin, setAuthenticatedPin] = useState<string | null>(null);
  const [status, setStatus] = useState<AdminSetupStatus | null>(null);
  const [preview, setPreview] = useState<AdminSeedPreview | null>(null);
  const [smoke, setSmoke] = useState<Record<string, unknown> | null>(null);
  const [adminError, setAdminError] = useState<string | null>(null);
  const [adminBusy, setAdminBusy] = useState(false);

  const loadAdmin = async (adminPin = authenticatedPin) => {
    if (!adminPin) return;
    setAdminBusy(true);
    try {
      const [setupStatus, seedPreview] = await Promise.all([
        api.adminSetupStatus(adminPin),
        api.adminSeedPreview(adminPin),
      ]);
      setStatus(setupStatus);
      setPreview(seedPreview);
      setAuthenticatedPin(adminPin);
      setAdminError(null);
    } catch (caught) {
      setAdminError(caught instanceof Error ? caught.message : "Admin setup request failed");
    } finally {
      setAdminBusy(false);
    }
  };

  const runAdminAction = async (action: "import" | "enable" | "disable" | "smoke") => {
    if (!authenticatedPin) return;
    setAdminBusy(true);
    try {
      if (action === "import") await api.adminImportSeed(authenticatedPin);
      if (action === "enable") await api.adminEnableSeed(authenticatedPin);
      if (action === "disable") await api.adminDisableSeed(authenticatedPin);
      if (action === "smoke") setSmoke(await api.adminGeminiSmoke(authenticatedPin));
      await loadAdmin(authenticatedPin);
      await onPlatformChange();
      setAdminError(null);
    } catch (caught) {
      setAdminError(caught instanceof Error ? caught.message : "Admin action failed");
    } finally {
      setAdminBusy(false);
    }
  };

  if (!authenticatedPin || !status) {
    return (
      <main className="view">
        <section className="panel admin-login">
          <div className="panel-header">
            <div>
              <p className="eyebrow">ADMIN SETUP</p>
              <h2>Platform Setup Panel</h2>
            </div>
            <Lock size={24} />
          </div>
          <form
            className="admin-pin-form"
            onSubmit={(event) => {
              event.preventDefault();
              void loadAdmin(pin);
            }}
          >
            <label htmlFor="admin-pin">Admin PIN</label>
            <div>
              <input
                id="admin-pin"
                value={pin}
                onChange={(event) => setPin(event.target.value)}
                inputMode="numeric"
                type="password"
                autoComplete="off"
                placeholder="1234"
              />
              <button type="submit" className="primary" disabled={adminBusy || pin.length === 0}>
                <KeyRound size={18} /> Unlock
              </button>
            </div>
          </form>
          {adminError && <div className="error-banner">{adminError}</div>}
        </section>
      </main>
    );
  }

  const seedEnabled = status.seed.demo_data_enabled;
  return (
    <main className="view admin-view">
      <section className="control-band">
        <div>
          <p className="eyebrow">ADMIN SETUP</p>
          <h2>Platform Setup</h2>
          <span className={cls("seed-status", seedEnabled ? "enabled" : "disabled")}>
            Seed {seedEnabled ? "enabled" : "disabled"} · {status.seed.collections.machines} machines · {status.seed.collections.knowledge_documents} knowledge docs
          </span>
        </div>
        <div className="control-actions">
          <button type="button" onClick={() => void loadAdmin()} disabled={adminBusy}>
            <RotateCcw size={18} /> Refresh
          </button>
          <button type="button" className="primary" onClick={() => void runAdminAction("import")} disabled={adminBusy}>
            <Database size={18} /> Import Complete Seed
          </button>
          <button type="button" onClick={() => void runAdminAction(seedEnabled ? "disable" : "enable")} disabled={adminBusy}>
            <ShieldCheck size={18} /> {seedEnabled ? "Disable Seed" : "Enable Seed"}
          </button>
          <button type="button" onClick={() => void runAdminAction("smoke")} disabled={adminBusy}>
            <RadioTower size={18} /> Gemini Smoke Test
          </button>
        </div>
      </section>

      {adminError && <div className="error-banner">{adminError}</div>}

      <section className="split">
        <div className="panel">
          <h2>Gemini Flash Setup</h2>
          <div className="setup-grid">
            <SetupCheck
              label="ADK import"
              ok={status.gemini.google_adk_importable && status.gemini.adk_available}
              detail={status.gemini.adk_status}
            />
            <SetupCheck
              label="Google Gen AI SDK"
              ok={status.gemini.google_genai_importable}
              detail={status.gemini.google_genai_importable ? "google-genai is importable" : "Install backend dependencies"}
            />
            <SetupCheck
              label="Real Gemini provider"
              ok={status.gemini.real_gemini_enabled}
              detail={`Current provider: ${status.gemini.model_provider}`}
            />
            <SetupCheck
              label="Google Cloud project"
              ok={status.gemini.google_cloud_project_configured}
              detail={status.gemini.google_cloud_project ?? "Set GOOGLE_CLOUD_PROJECT"}
            />
            <SetupCheck
              label="gcloud CLI"
              ok={status.gemini.gcloud_on_path}
              detail={status.gemini.gcloud_on_path ? "gcloud is on PATH" : "Install Google Cloud CLI for local auth/deploy"}
            />
            <SetupCheck
              label="Model"
              ok={status.gemini.model === "gemini-3.5-flash"}
              detail={status.gemini.model}
            />
          </div>
          {smoke && (
            <pre className="admin-json">{JSON.stringify(smoke, null, 2)}</pre>
          )}
        </div>

        <div className="panel">
          <h2>Runtime</h2>
          <div className="detail-grid">
            <MetricCard label="Environment" value={status.runtime.environment} />
            <MetricCard label="Store" value={status.runtime.store_backend} />
            <MetricCard label="Event Bus" value={status.runtime.event_bus} />
            <MetricCard label="Cloud" value={status.runtime.running_on_google_cloud ? "yes" : "no"} />
          </div>
          <div className="setup-copy">
            <strong>To use real Gemini Flash locally</strong>
            <code>gcloud auth application-default login</code>
            <code>FORGE_MODEL_PROVIDER=REAL_GEMINI</code>
            <code>GOOGLE_CLOUD_PROJECT=your-project</code>
            <code>GOOGLE_GENAI_USE_ENTERPRISE=True</code>
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>Seeded Machines</h2>
          <span className="model-badge">{preview?.machines.length ?? 0}</span>
        </div>
        <div className="admin-table">
          {(preview?.machines ?? []).map((machine) => (
            <div key={machine.machine_id} className="admin-row">
              <strong>{machine.machine_id}</strong>
              <span>{machine.model}</span>
              <span>{machine.state}</span>
              <span>{machine.current_work_order_id ?? "none"}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>Seeded Work Orders</h2>
          <span className="model-badge">{preview?.work_orders.length ?? 0}</span>
        </div>
        <div className="admin-table">
          {(preview?.work_orders ?? []).map((order) => (
            <div key={order.work_order_id} className="admin-row work-order-row">
              <strong>{order.work_order_id}</strong>
              <span>{order.part_number}</span>
              <span>{order.operation}</span>
              <span>{order.completed_quantity} / {order.required_quantity}</span>
              <span>{order.assigned_machine_id}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>Seeded Knowledge</h2>
          <span className="model-badge">{preview?.knowledge_documents.length ?? 0}</span>
        </div>
        <div className="admin-knowledge-list">
          {(preview?.knowledge_documents ?? []).map((doc) => (
            <div key={doc.document_id} className={cls("list-row", doc.approved ? "" : "security-risk")}>
              <strong>{doc.document_id} · {doc.title}</strong>
              <span>{doc.document_type} · rev {doc.revision} · approved={String(doc.approved)}</span>
              <small>{doc.tags.join(", ")}</small>
            </div>
          ))}
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>Seeded Agents</h2>
          <span className="model-badge">{preview?.agent_registry.length ?? 0}</span>
        </div>
        <div className="admin-table">
          {(preview?.agent_registry ?? []).map((agent) => (
            <div key={agent.agent_id} className="admin-row agent-seed-row">
              <strong>{agent.agent_id}</strong>
              <span>{agent.version}</span>
              <span>{agent.model}</span>
              <span>{agent.identity}</span>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}

export function App() {
  const [view, setView] = useState<View>("overview");
  const [snapshot, setSnapshot] = useState<Snapshot>(initialSnapshot);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const activeIncidentId = useMemo(() => {
    const active = snapshot.incidents.find((incident) => !["LEARNED", "CANCELLED"].includes(incident.status));
    return active?.incident_id ?? snapshot.incidents.at(-1)?.incident_id;
  }, [snapshot.incidents]);

  const refresh = useCallback(async () => {
    const [facility, machines, incidents, agents, registry, security, traces, approvals, system, demoSeed] = await Promise.all([
      api.facility(),
      api.machines(),
      api.incidents(),
      api.agents(),
      api.registry(),
      api.security(),
      api.traces(),
      api.approvals(),
      api.system(),
      api.demoSeedStatus(),
    ]);
    const latestIncidentId = incidents.find((incident) => !["LEARNED", "CANCELLED"].includes(incident.status))?.incident_id ?? incidents.at(-1)?.incident_id;
    const activeIncident = latestIncidentId ? await api.incident(latestIncidentId) : undefined;
    setSnapshot({ facility, machines, incidents, agents, registry, security, traces, approvals, system, demoSeed, activeIncident });
    setError(null);
  }, []);

  useEffect(() => {
    void refresh().catch((caught: unknown) => setError(caught instanceof Error ? caught.message : "Unable to load Forge state"));
    const timer = window.setInterval(() => {
      void refresh().catch((caught: unknown) => setError(caught instanceof Error ? caught.message : "Unable to load Forge state"));
    }, 2500);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const handleAction = async (name: string) => {
    setBusy(true);
    try {
      if (name === "reset") {
        await api.resetDemo();
        setView("overview");
      } else if (name === "import_seed") {
        await api.importDemoSeed();
        setView("overview");
      } else if (name === "enable_seed") {
        await api.enableDemoSeed();
        setView("overview");
      } else if (name === "disable_seed") {
        await api.disableDemoSeed();
        setView("overview");
      } else if (name === "start") {
        await api.startDemo();
        setView("incident");
      } else {
        await api.inject(name);
        if (name === "maintenance_resolved") setView("incident");
      }
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Demo action failed");
    } finally {
      setBusy(false);
    }
  };

  const approve = async (approvalId?: string) => {
    if (!activeIncidentId) return;
    setBusy(true);
    try {
      await api.approve(activeIncidentId, approvalId);
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Approval failed");
    } finally {
      setBusy(false);
    }
  };

  const reject = async (approvalId?: string) => {
    if (!activeIncidentId) return;
    setBusy(true);
    try {
      await api.reject(activeIncidentId, approvalId);
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Rejection failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <Factory size={28} />
          <div>
            <strong>EPYK Forge</strong>
            <span>Northstar Precision Works</span>
          </div>
        </div>
        <nav>
          <button type="button" className={view === "overview" ? "active" : ""} onClick={() => setView("overview")}><Activity size={18} /> Overview</button>
          <button type="button" className={view === "factory" ? "active" : ""} onClick={() => setView("factory")}><Factory size={18} /> Factory</button>
          <button type="button" className={view === "incident" ? "active" : ""} onClick={() => setView("incident")}><ClipboardCheck size={18} /> Incident</button>
          <button type="button" className={view === "fleet" ? "active" : ""} onClick={() => setView("fleet")}><Workflow size={18} /> Fleet</button>
          <button type="button" className={view === "registry" ? "active" : ""} onClick={() => setView("registry")}><Database size={18} /> Registry</button>
          <button type="button" className={view === "security" ? "active" : ""} onClick={() => setView("security")}><ShieldCheck size={18} /> Security</button>
          <button type="button" className={view === "observability" ? "active" : ""} onClick={() => setView("observability")}><RadioTower size={18} /> Observability</button>
          <button type="button" className={view === "cloud" ? "active" : ""} onClick={() => setView("cloud")}><Server size={18} /> Cloud</button>
          <button type="button" className={view === "admin" ? "active" : ""} onClick={() => setView("admin")}><Settings size={18} /> Admin</button>
        </nav>
        <div className="sidebar-foot">
          <span>{snapshot.system?.model_provider ?? "loading"}</span>
          <strong>{snapshot.system?.model ?? "gemini-3.5-flash"}</strong>
        </div>
      </aside>
      <div className="content">
        <header className="topbar">
          <div>
            <p className="eyebrow">The autonomous operations fleet for the factory floor.</p>
            <h1>{view === "overview" ? "Operations Center" : view.charAt(0).toUpperCase() + view.slice(1)}</h1>
          </div>
          {error && <div className="error-banner">{error}</div>}
        </header>
        {view === "overview" && <Overview snapshot={snapshot} onAction={handleAction} busy={busy} setView={setView} />}
        {view === "factory" && <FactoryView machines={snapshot.machines} />}
        {view === "incident" && <IncidentCommand incident={snapshot.activeIncident} approvals={snapshot.approvals} onApprove={approve} onReject={reject} />}
        {view === "fleet" && <AgentFleetView agents={snapshot.agents} />}
        {view === "registry" && <RegistryView registry={snapshot.registry} />}
        {view === "security" && <SecurityView events={snapshot.security} />}
        {view === "observability" && <ObservabilityView traces={snapshot.traces} incident={snapshot.activeIncident} />}
        {view === "cloud" && <CloudView system={snapshot.system} />}
        {view === "admin" && <AdminPanel onPlatformChange={refresh} />}
      </div>
    </div>
  );
}
