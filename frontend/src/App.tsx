import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Circle,
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
  ShieldAlert,
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
  IncidentEvidence,
  Machine,
  SecurityEvent,
  SystemInfo,
  TraceSpan,
  WorkflowStage,
  WorkOrder,
} from "./types";

type View = "overview" | "factory" | "incident" | "fleet" | "registry" | "security" | "observability" | "cloud" | "admin";
type Filter = "ALL" | "RUNNING" | "IDLE" | "ALARM" | "MAINTENANCE" | "AT_RISK";

interface Snapshot {
  facility?: Facility;
  machines: Machine[];
  workOrders: WorkOrder[];
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
  workOrders: [],
  incidents: [],
  agents: [],
  registry: [],
  security: [],
  traces: [],
  approvals: [],
};

const fallbackWorkflow: WorkflowStage[] = [
  { stage_id: "observer", agent_id: "observer-agent", label: "Observer", status: "PENDING", dependencies: [], retry_count: 0, order: 10 },
  { stage_id: "diagnostic", agent_id: "diagnostic-agent", label: "Diagnostic", status: "PENDING", dependencies: ["observer"], retry_count: 0, parallel_group: "analysis", order: 20 },
  { stage_id: "knowledge", agent_id: "knowledge-agent", label: "Knowledge", status: "PENDING", dependencies: ["observer"], retry_count: 0, parallel_group: "analysis", order: 30 },
  { stage_id: "production", agent_id: "production-agent", label: "Production", status: "PENDING", dependencies: ["diagnostic", "knowledge"], retry_count: 0, order: 40 },
  { stage_id: "recovery", agent_id: "recovery-agent", label: "Recovery", status: "PENDING", dependencies: ["production"], retry_count: 0, order: 50 },
  { stage_id: "supervisor", agent_id: "supervisor-agent", label: "Supervisor", status: "PENDING", dependencies: ["recovery"], retry_count: 0, order: 60 },
];

function cls(...items: Array<string | false | null | undefined>) {
  return items.filter(Boolean).join(" ");
}

function severityClass(value?: string) {
  if (!value) return "neutral";
  return value.toLowerCase();
}

function stateClass(value?: string) {
  if (!value) return "neutral";
  return value.toLowerCase().replaceAll("_", "-");
}

function statusTone(value?: string) {
  if (!value) return "neutral";
  if (["RUNNING", "HEALTHY", "SUCCEEDED", "RECOVERED", "APPROVED", "EXECUTED"].includes(value)) return "good";
  if (["AWAITING_APPROVAL", "PROPOSED", "WARNING", "HIGH", "AT_RISK"].includes(value)) return "warn";
  if (["FAILED", "DENIED", "CRITICAL", "ALARM", "REJECTED", "ESCALATED"].includes(value)) return "bad";
  if (["PENDING", "IDLE", "READY"].includes(value)) return "neutral";
  return "info";
}

function formatTime(value?: string | null) {
  if (!value) return "never";
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

function formatDue(value?: string) {
  if (!value) return "unknown";
  const due = new Date(value);
  const now = new Date();
  const sameDay = due.toDateString() === now.toDateString();
  return sameDay ? "Today" : new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(due);
}

function formatDuration(ms?: number | null) {
  if (ms === undefined || ms === null) return "-";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

function incidentElapsed(incident?: Incident) {
  if (!incident) return "-";
  const elapsed = Math.max(Date.now() - new Date(incident.created_at).getTime(), 0);
  const minutes = Math.floor(elapsed / 60000);
  const seconds = Math.floor((elapsed % 60000) / 1000);
  return minutes ? `${minutes}m ${seconds}s` : `${seconds}s`;
}

function readableAction(value: string) {
  return value.replaceAll("_", " ").replaceAll(".", " ");
}

function workOrderFor(workOrders: WorkOrder[], workOrderId?: string | null) {
  return workOrders.find((order) => order.work_order_id === workOrderId);
}

function Sparkline({ samples, metric = "x_axis_load_pct", label = "X-axis load trend" }: { samples: Machine["telemetry_history"]; metric?: keyof Machine["telemetry"]; label?: string }) {
  const points = samples.slice(-18);
  if (!points.length) return <div className="sparkline empty" />;
  const max = metric === "observed_cycle_time_sec" ? Math.max(...points.map((sample) => Number(sample[metric]) || 0), 200) : 100;
  const min = metric === "observed_cycle_time_sec" ? Math.min(...points.map((sample) => Number(sample[metric]) || 0), 180) : 0;
  const width = 180;
  const height = 56;
  const path = points
    .map((sample, index) => {
      const value = Number(sample[metric]) || 0;
      const x = points.length === 1 ? 0 : (index / (points.length - 1)) * width;
      const y = height - ((value - min) / Math.max(max - min, 1)) * height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg className="sparkline" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label}>
      <polyline points={path} fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      {metric === "x_axis_load_pct" && <line x1="0" x2={width} y1="8" y2="8" className="limit-line" />}
    </svg>
  );
}

function MetricCard({ label, value, tone, detail }: { label: string; value: string | number; tone?: string; detail?: string }) {
  return (
    <div className={cls("metric", tone)}>
      <span>{label}</span>
      <strong>{value}</strong>
      {detail && <small>{detail}</small>}
    </div>
  );
}

function EmptyPanel({ title, body, items }: { title: string; body: string; items?: string[] }) {
  return (
    <div className="empty-state rich">
      <strong>{title}</strong>
      <span>{body}</span>
      {items && (
        <div className="empty-list">
          {items.map((item) => <span key={item}>{item}</span>)}
        </div>
      )}
    </div>
  );
}

function DemoControls({
  busy,
  onAction,
  demoSeed,
  activeIncident,
}: {
  busy: boolean;
  onAction: (name: string) => void;
  demoSeed?: DemoSeedStatus;
  activeIncident?: Incident;
}) {
  const enabled = demoSeed?.demo_data_enabled ?? false;
  const scenarioStatus = demoSeed?.scenario_status ?? "UNKNOWN";
  const canStart = enabled && scenarioStatus === "READY" && !activeIncident;
  const canResolve = enabled && activeIncident?.status === "MONITORING";
  return (
    <section className="control-band" aria-label="Synthetic demo controls">
      <div className="control-title">
        <p className="eyebrow">SYNTHETIC DEMO CONTROLS</p>
        <h2>Servo Overload Cascade</h2>
        <span className={cls("seed-status", enabled ? "enabled" : "disabled")}>
          Seed data {enabled ? "enabled" : "disabled"} | {demoSeed?.collections.machines ?? 0} machines | {scenarioStatus}
        </span>
      </div>
      <div className="control-groups">
        <div className="control-group" aria-label="Data controls">
          <span>DATA</span>
          <button type="button" onClick={() => onAction("import_seed")} disabled={busy} title="Import complete demo seed data">
            <Database size={18} /> Import Seed
          </button>
          <button type="button" onClick={() => onAction("reset")} disabled={busy} title="Reset demo to nominal state">
            <RotateCcw size={18} /> Reset
          </button>
        </div>
        <div className="control-group" aria-label="Hero scenario controls">
          <span>HERO SCENARIO</span>
          <button type="button" className="primary" onClick={() => onAction("start")} disabled={busy || !canStart} title="Start the timed precursor and incident flow">
            <Play size={18} /> Start
          </button>
          <button type="button" onClick={() => onAction("servo_alarm")} disabled={busy || !canStart} title="Inject the servo alarm immediately">
            <AlertTriangle size={18} /> Inject Alarm
          </button>
          <button type="button" onClick={() => onAction("maintenance_resolved")} disabled={busy || !canResolve} title="Resolve maintenance after approval">
            <CheckCircle2 size={18} /> Resolve
          </button>
        </div>
        <div className="control-group" aria-label="Resilience controls">
          <span>RESILIENCE</span>
          <button type="button" onClick={() => onAction("security_attack")} disabled={busy || !canStart} title="Run the prompt-injection defense scenario">
            <ShieldAlert size={18} /> Security Test
          </button>
          <button type="button" onClick={() => onAction("failure")} disabled={busy || !canStart} title="Run the forced retry and recovery scenario">
            <RadioTower size={18} /> Retry Test
          </button>
          <button type="button" onClick={() => onAction(enabled ? "disable_seed" : "enable_seed")} disabled={busy} title="Enable or disable seed data">
            <ShieldCheck size={18} /> {enabled ? "Disable Seed" : "Enable Seed"}
          </button>
        </div>
      </div>
    </section>
  );
}

function MachineCard({ machine, onSelect }: { machine: Machine; onSelect: (machineId: string) => void }) {
  return (
    <button type="button" className={cls("machine-card", stateClass(machine.state), machine.at_risk && "risk")} onClick={() => onSelect(machine.machine_id)}>
      <div className="machine-top">
        <div>
          <strong>{machine.machine_id}</strong>
          <span>{machine.model}</span>
        </div>
        <span className={cls("pill", stateClass(machine.state))}>{machine.state}</span>
      </div>
      <div className="machine-job">
        <span>{machine.current_work_order_id ?? "No active work order"}</span>
        <strong>{machine.current_operation ?? machine.cell}</strong>
      </div>
      <Sparkline samples={machine.telemetry_history} />
      <div className="machine-stats">
        <span>Cycle {Math.round(machine.telemetry.observed_cycle_time_sec)}s / {Math.round(machine.telemetry.target_cycle_time_sec)}s</span>
        <span>X load {Math.round(machine.telemetry.x_axis_load_pct)}%</span>
      </div>
    </button>
  );
}

function Overview({ snapshot, onAction, busy, setView }: { snapshot: Snapshot; onAction: (name: string) => void; busy: boolean; setView: (view: View) => void }) {
  const facility = snapshot.facility;
  const mc04 = snapshot.machines.find((machine) => machine.machine_id === "MC-04");
  const incident = snapshot.activeIncident;
  const workOrder = workOrderFor(snapshot.workOrders, incident?.work_order_id ?? "MO-4821");
  const pendingApprovals = snapshot.approvals.filter((approval) => approval.status === "PROPOSED").length;
  const agentsActive = snapshot.agents.filter((agent) => ["RUNNING", "SUCCEEDED", "RECOVERED"].includes(agent.latest_status ?? "")).length;
  return (
    <main className="view">
      <DemoControls busy={busy} onAction={onAction} demoSeed={snapshot.demoSeed} activeIncident={snapshot.activeIncident} />
      <section className="metrics-grid wide">
        <MetricCard label="Facility Health" value={facility?.health_score ?? "-"} tone="cyan" />
        <MetricCard label="Running" value={facility?.machines_running ?? 0} />
        <MetricCard label="Idle" value={facility?.machines_idle ?? 0} />
        <MetricCard label="Alarmed" value={facility?.machines_alarmed ?? 0} tone="red" />
        <MetricCard label="Active Incidents" value={facility?.active_incidents ?? 0} tone="amber" />
        <MetricCard label="At-Risk Orders" value={facility?.at_risk_orders ?? 0} tone="amber" />
        <MetricCard label="Agents Active" value={agentsActive} tone="green" />
        <MetricCard label="Pending Approval" value={pendingApprovals} tone={pendingApprovals ? "amber" : undefined} />
      </section>
      <section className="split overview-split">
        <div className="panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Northstar Precision Works</p>
              <h2>Synthetic Manufacturing Environment</h2>
            </div>
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
            <div>
              <p className="eyebrow">Dashboards tell you what happened.</p>
              <h2>Forge starts handling what happens next.</h2>
            </div>
            {incident ? <span className={cls("pill", severityClass(incident.severity))}>{incident.severity}</span> : <span className="pill neutral">standby</span>}
          </div>
          {incident ? (
            <button type="button" className="incident-button" onClick={() => setView("incident")}>
              <strong>{incident.incident_id}</strong>
              <span>{incident.title}</span>
              <small>{incident.machine_id} | {incident.work_order_id} | {workOrder?.part_number ?? "part pending"}</small>
              <span className={cls("status-line", stateClass(incident.status))}>Stage: {incident.status}</span>
              {incident.production_impact && <span>{incident.production_impact.remaining_quantity} pieces at risk</span>}
            </button>
          ) : (
            <EmptyPanel
              title="NO ACTIVE INCIDENT"
              body="Forge is monitoring 10 synthetic assets."
              items={[
                `System state: ${facility?.machines_alarmed ? "Attention required" : "Nominal"}`,
                mc04 ? `MC-04 ${mc04.state} with ${Math.round(mc04.telemetry.x_axis_load_pct)}% X-axis load` : "MC-04 loading",
                "Start the Servo Overload Cascade from Demo Controls.",
              ]}
            />
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

function FactoryView({ machines, workOrders }: { machines: Machine[]; workOrders: WorkOrder[] }) {
  const [filter, setFilter] = useState<Filter>("ALL");
  const [selectedId, setSelectedId] = useState("MC-04");
  const filtered = machines.filter((machine) => {
    if (filter === "ALL") return true;
    if (filter === "AT_RISK") return machine.at_risk;
    return machine.state === filter;
  });
  const active = machines.find((machine) => machine.machine_id === selectedId) ?? machines.find((machine) => machine.machine_id === "MC-04") ?? machines[0];
  const order = workOrderFor(workOrders, active?.current_work_order_id);
  const xTrend = active?.telemetry_history.slice(-6).map((sample) => `${Math.round(sample.x_axis_load_pct)}%`).join(" -> ");
  const cycleTrend = active?.telemetry_history.slice(-6).map((sample) => `${Math.round(sample.observed_cycle_time_sec)}s`).join(" -> ");
  return (
    <main className="view">
      <section className="toolbar" aria-label="Machine filters">
        {(["ALL", "RUNNING", "IDLE", "ALARM", "MAINTENANCE", "AT_RISK"] as Filter[]).map((item) => (
          <button key={item} type="button" className={filter === item ? "selected" : ""} onClick={() => setFilter(item)}>
            {item.replace("_", " ")}
          </button>
        ))}
      </section>
      <section className="machine-grid">
        {filtered.map((machine) => (
          <MachineCard key={machine.machine_id} machine={machine} onSelect={setSelectedId} />
        ))}
      </section>
      {active && (
        <section className="panel detail-panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">{active.machine_type}</p>
              <h2>{active.machine_id} | {active.model}</h2>
            </div>
            <span className={cls("pill", stateClass(active.state))}>{active.state}</span>
          </div>
          <div className="detail-grid dense">
            <MetricCard label="Work Order" value={active.current_work_order_id ?? "None"} detail={order?.part_number} />
            <MetricCard label="Operation" value={active.current_operation ?? "-"} detail={order?.part_description} />
            <MetricCard label="Completed" value={order ? `${order.completed_quantity} / ${order.required_quantity}` : "-"} />
            <MetricCard label="Cycle" value={`${Math.round(active.telemetry.target_cycle_time_sec)}s target`} detail={`${Math.round(active.telemetry.observed_cycle_time_sec)}s actual`} />
            <MetricCard label="X-axis Load" value={`${Math.round(active.telemetry.x_axis_load_pct)}%`} tone={active.telemetry.x_axis_load_pct > 85 ? "red" : "cyan"} />
            <MetricCard label="Health" value={active.health_score} tone={active.health_score < 50 ? "red" : "green"} />
          </div>
          <div className="telemetry-detail">
            <div>
              <strong>X-axis load</strong>
              <span>{xTrend}</span>
              <Sparkline samples={active.telemetry_history} />
            </div>
            <div>
              <strong>Cycle time</strong>
              <span>{cycleTrend}</span>
              <Sparkline samples={active.telemetry_history} metric="observed_cycle_time_sec" label="Cycle time trend" />
            </div>
          </div>
        </section>
      )}
    </main>
  );
}

function StageIcon({ status }: { status: string }) {
  if (status === "FAILED") return <XCircle size={20} />;
  if (status === "RUNNING") return <Activity size={20} />;
  if (status === "SUCCEEDED" || status === "RECOVERED") return <CheckCircle2 size={20} />;
  return <Circle size={20} />;
}

function EvidenceGroup({ title, rows }: { title: string; rows: IncidentEvidence[] }) {
  if (!rows.length) return null;
  return (
    <div className="evidence-group">
      <h3>{title}</h3>
      {rows.map((item) => (
        <div key={item.evidence_id} className={cls("list-row", item.kind === "security" && "security-risk")}>
          <strong>{item.title}</strong>
          <span>{item.summary}</span>
          <small>
            {item.source_agent ?? item.kind} | {item.source_event_ids.length ? item.source_event_ids.join(", ") : item.source_event_id ?? "provenance retained"} | {Math.round(item.confidence * 100)}%
          </small>
        </div>
      ))}
    </div>
  );
}

function CauseRow({ cause }: { cause: { cause: string; confidence: number; evidence: string[]; contradictions: string[] } }) {
  const pct = Math.round(cause.confidence * 100);
  const support = pct >= 70 ? "Strongly supported" : pct >= 15 ? "Possible" : "Unlikely";
  return (
    <div className="cause-row">
      <div className="confidence-ring" style={{ "--pct": pct } as React.CSSProperties}>{pct}%</div>
      <div>
        <strong>{cause.cause}</strong>
        <span>{support}</span>
        <small>{cause.evidence.length ? `Evidence: ${cause.evidence.slice(0, 4).join(", ")}` : "No direct supporting event"}</small>
        <small>{cause.contradictions.join(" | ")}</small>
      </div>
    </div>
  );
}

function RecoveryStep({ label, state }: { label: string; state: "done" | "active" | "pending" | "blocked" }) {
  return (
    <div className={cls("recovery-step", state)}>
      {state === "done" ? <CheckCircle2 size={18} /> : state === "blocked" ? <XCircle size={18} /> : <Circle size={18} />}
      <span>{label}</span>
    </div>
  );
}

function IncidentCommand({
  incident,
  approvals,
  workOrders,
  machines,
  onApprove,
  onReject,
}: {
  incident?: Incident;
  approvals: Approval[];
  workOrders: WorkOrder[];
  machines: Machine[];
  onApprove: (approvalId?: string) => void;
  onReject: (approvalId?: string) => void;
}) {
  if (!incident) {
    const lastMachine = machines.find((machine) => machine.machine_id === "MC-03") ?? machines[0];
    return (
      <main className="view">
        <EmptyPanel
          title="NO ACTIVE INCIDENT"
          body="Forge is monitoring 10 synthetic assets."
          items={[
            lastMachine ? `Last operational event: ${lastMachine.machine_id} ${lastMachine.state.toLowerCase()}` : "Factory snapshot loading",
            "System state: Nominal",
            "Start the Servo Overload Cascade from Demo Controls to observe the autonomous response.",
          ]}
        />
      </main>
    );
  }

  const workflow = (incident.workflow?.length ? incident.workflow : fallbackWorkflow).slice().sort((a, b) => a.order - b.order);
  const pending = approvals.find((approval) => approval.incident_id === incident.incident_id && approval.status === "PROPOSED");
  const proposal = incident.schedule_proposals?.find((item) => item.proposal_id === pending?.proposal_id) ?? incident.schedule_proposals?.[0];
  const order = workOrderFor(workOrders, incident.work_order_id);
  const machine = machines.find((item) => item.machine_id === incident.machine_id);
  const evidence = incident.evidence ?? [];
  const executed = new Set((incident.action_log ?? []).filter((item) => item.status === "EXECUTED").map((item) => item.action_type));
  const proposed = new Set((incident.action_log ?? []).filter((item) => item.status === "PROPOSED").map((item) => item.action_type));
  const transferApproved = proposal?.status === "APPROVED";
  const resolved = ["RESOLVED", "LEARNED"].includes(incident.status);
  return (
    <main className="view incident-view">
      <section className="incident-header">
        <div>
          <p className="eyebrow">{machine?.machine_id ?? incident.machine_id} | {machine?.model ?? "FX-5X"}</p>
          <h1>{incident.incident_id}</h1>
          <h2>{incident.title}</h2>
          <span>{incident.machine_id} | {machine?.model ?? "FX-5X"} | {incident.work_order_id} | {order?.part_number ?? "NP-4172"} | {order?.operation ?? "OP30"}</span>
        </div>
        <div className="incident-status">
          <span className={cls("pill", severityClass(incident.severity))}>{incident.severity}</span>
          <strong>{incident.status}</strong>
          <small>Detected {formatTime(incident.created_at)} | Elapsed {incidentElapsed(incident)}</small>
          <small>Trace {incident.correlation_id}</small>
        </div>
      </section>

      <section className="workflow" aria-label="Agent workflow timeline">
        {workflow.map((stage) => (
          <div key={stage.stage_id} className={cls("workflow-step", stateClass(stage.status), statusTone(stage.status))}>
            <StageIcon status={stage.status} />
            <div>
              <strong>{stage.label}</strong>
              <span>{stage.status}</span>
            </div>
            <small>{stage.action_summary ?? (stage.status === "PENDING" ? "Waiting for dependencies" : "Running")}</small>
            <small>{formatDuration(stage.duration_ms)}{stage.retry_count ? ` | retry ${stage.retry_count} / 3` : ""}</small>
            {stage.error && <small className="error-text">{stage.error}</small>}
          </div>
        ))}
      </section>

      <section className="incident-grid">
        <div className="panel evidence-panel">
          <div className="panel-header">
            <h2>Evidence</h2>
            <span className="model-badge">{evidence.length} records</span>
          </div>
          <EvidenceGroup title="Trigger" rows={evidence.filter((item) => item.evidence_type === "trigger")} />
          <EvidenceGroup title="Precursor Telemetry" rows={evidence.filter((item) => item.evidence_type === "precursor_telemetry")} />
          <EvidenceGroup title="Historical Context" rows={evidence.filter((item) => item.evidence_type === "historical_context")} />
          <EvidenceGroup title="Knowledge References" rows={evidence.filter((item) => item.evidence_type === "knowledge_reference")} />
          <EvidenceGroup title="Contradictory Evidence" rows={evidence.filter((item) => item.evidence_type === "contradictory_evidence")} />
          <EvidenceGroup title="Retrieval Safety" rows={evidence.filter((item) => item.evidence_type === "security")} />
        </div>

        <div className="panel diagnosis-panel">
          <div className="panel-header">
            <h2>Likely Causes</h2>
            {incident.diagnosis && <span className="model-badge">{Math.round(incident.diagnosis.confidence * 100)}% confidence</span>}
          </div>
          {incident.diagnosis ? (
            <div className="cause-list">
              <p>{incident.diagnosis.summary}</p>
              {incident.diagnosis.probable_causes.map((cause) => <CauseRow key={cause.cause} cause={cause} />)}
            </div>
          ) : <EmptyPanel title="DIAGNOSIS PENDING" body="Diagnostic Agent has not completed." />}
        </div>

        <div className="panel knowledge-panel">
          <div className="panel-header">
            <h2>Knowledge</h2>
            <span className="model-badge">{incident.knowledge_result?.references.length ?? 0} references</span>
          </div>
          <div className="list">
            {incident.knowledge_result?.references.map((ref) => (
              <div key={ref.document_id} className={cls("list-row", ref.injection_risk && "security-risk")}>
                <strong>{ref.document_id} | {ref.title}</strong>
                <span>{ref.excerpt}</span>
                <small>
                  {ref.injection_risk ? "UNTRUSTED RETRIEVED CONTENT | " : ""}
                  {ref.document_type} | rev {ref.revision} | approved={String(ref.approved)} | {Math.round(ref.relevance_confidence * 100)}%
                </small>
              </div>
            )) ?? <EmptyPanel title="KNOWLEDGE PENDING" body="Relevant procedures and lessons will appear here." />}
          </div>
        </div>

        <div className="panel production-panel">
          <div className="panel-header">
            <h2>Production Impact</h2>
            {incident.production_impact && <span className={cls("pill", statusTone(incident.production_impact.delivery_risk))}>{incident.production_impact.delivery_risk}</span>}
          </div>
          {incident.production_impact ? (
            <div className="impact">
              <div className="detail-grid dense">
                <MetricCard label="Remaining" value={`${incident.production_impact.remaining_quantity} / ${order?.required_quantity ?? 120}`} />
                <MetricCard label="Estimated Downtime" value={`${incident.production_impact.estimated_downtime_minutes} min`} />
                <MetricCard label="Order Risk" value={incident.production_impact.delivery_risk} tone="amber" />
                <MetricCard label="Due" value={formatDue(order?.due_at)} />
                <MetricCard label="Schedule Recovery" value={`${incident.production_impact.saved_minutes_if_reassigned} min`} tone="cyan" />
              </div>
              <div className="capacity-list">
                <strong>Fallback Capacity</strong>
                {incident.production_impact.alternatives.filter((alt) => alt.capable).slice(0, 3).map((alt) => (
                  <span key={alt.machine_id}>{alt.machine_id} | {alt.current_state} | setup {alt.setup_minutes} min | queue {alt.queue_minutes} min</span>
                ))}
              </div>
              <p>{incident.production_impact.recommendation}</p>
            </div>
          ) : <EmptyPanel title="IMPACT PENDING" body="Production Agent has not completed deterministic schedule analysis." />}
        </div>

        <div className="panel recovery-panel">
          <div className="panel-header">
            <h2>Recovery Plan</h2>
            <span className="model-badge">{incident.recovery_plan?.steps.length ?? 0} steps</span>
          </div>
          {incident.recovery_plan ? (
            <div className="recovery-list">
              <RecoveryStep label={`${incident.machine_id} placed in maintenance state`} state={executed.has("set_machine_maintenance") ? "done" : "pending"} />
              <RecoveryStep label="P1 maintenance ticket created" state={executed.has("create_maintenance_ticket") ? "done" : "pending"} />
              <RecoveryStep label="Technician inspection checklist generated" state={executed.has("create_maintenance_ticket") ? "done" : "pending"} />
              <RecoveryStep label={`${proposal?.to_machine_id ?? "MC-02"} capacity reserved by proposal`} state={proposed.has("create_schedule_proposal") || proposal ? "done" : "pending"} />
              <RecoveryStep label="Schedule transfer awaiting approval" state={pending ? "active" : transferApproved ? "done" : "pending"} />
              <RecoveryStep label="Recovery verification" state={resolved ? "done" : transferApproved ? "active" : "pending"} />
              <RecoveryStep label="Incident closure" state={incident.status === "LEARNED" ? "done" : "pending"} />
              <RecoveryStep label="Lesson stored in memory" state={incident.learned_at ? "done" : "pending"} />
              <div className="safety-boundary">{incident.recovery_plan.physical_safety_boundary}</div>
            </div>
          ) : <EmptyPanel title="RECOVERY PENDING" body="Recovery Agent has not generated the bounded workflow." />}
        </div>

        <div className="panel approval-panel">
          <div className="panel-header">
            <h2>Supervisor Decision Required</h2>
            <span className={cls("pill", pending ? "amber" : transferApproved ? "running" : "neutral")}>{pending ? "WAITING" : transferApproved ? "APPROVED" : "NONE"}</span>
          </div>
          {pending && proposal ? (
            <>
              <div className="approval-detail">
                <strong>Transfer remaining production</strong>
                <span>Work Order: {proposal.work_order_id}</span>
                <span>Remaining: {proposal.quantity} parts</span>
                <span>Current Machine: {proposal.from_machine_id}</span>
                <span>Proposed Machine: {proposal.to_machine_id}</span>
                <span>Estimated Schedule Recovery: {proposal.estimated_minutes_saved} min</span>
                <span>Risk: {proposal.risk}</span>
              </div>
              <div className="approval-actions">
                <button type="button" className="primary" onClick={() => onApprove(pending.approval_id)}><CheckCircle2 size={18} /> Approve Transfer</button>
                <button type="button" onClick={() => onReject(pending.approval_id)}><XCircle size={18} /> Reject</button>
              </div>
            </>
          ) : transferApproved && proposal ? (
            <div className="approval-detail">
              <strong>Schedule transfer approved</strong>
              <span>{proposal.work_order_id} is assigned to {proposal.to_machine_id}.</span>
              <span>Approved by {proposal.approved_by ?? "synthetic-supervisor"} at {formatTime(proposal.approved_at)}</span>
            </div>
          ) : (
            <EmptyPanel title="NO PENDING APPROVAL" body="Approval requests appear here when policy gates a production change." />
          )}
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>Action Log</h2>
          <span className="model-badge">{incident.action_log?.length ?? 0} entries</span>
        </div>
        <div className="table action-table">
          <div className="table-row table-head">
            <span>Time</span>
            <span>Action</span>
            <span>Principal</span>
            <span>Summary</span>
          </div>
          {(incident.action_log ?? []).map((action) => (
            <div key={action.execution_id} className="table-row">
              <span>{formatTime(action.timestamp)}</span>
              <strong>{readableAction(action.action_type)}</strong>
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
      <section className="metrics-grid">
        <MetricCard label="Registered Agents" value={agents.length} />
        <MetricCard label="Healthy" value={agents.filter((agent) => agent.health !== "DEGRADED").length} tone="green" />
        <MetricCard label="Failures" value={agents.reduce((sum, agent) => sum + (agent.failures ?? 0), 0)} tone="red" />
        <MetricCard label="Denied Physical Ops" value={new Set(agents.flatMap((agent) => agent.denied_tools.filter((tool) => ["machine.control", "plc.write", "servo.reset"].includes(tool)))).size} tone="amber" />
      </section>
      <section className="agent-grid">
        {agents.map((agent) => (
          <div className="panel agent-card" key={agent.agent_id}>
            <div className="panel-header">
              <div>
                <p className="eyebrow">{agent.name}</p>
                <h2>{agent.agent_id}</h2>
                <span>{agent.role}</span>
              </div>
              <span className={cls("pill", statusTone(agent.latest_status ?? agent.status))}>{agent.latest_status ?? agent.status}</span>
            </div>
            <p>{agent.purpose}</p>
            <div className="detail-grid dense">
              <MetricCard label="Assignment" value={agent.current_task ?? "standby"} />
              <MetricCard label="Success" value={agent.successful_executions ?? 0} />
              <MetricCard label="Failures" value={agent.failures ?? 0} tone={agent.failures ? "red" : undefined} />
              <MetricCard label="Latency" value={agent.latency_ms ? `${agent.latency_ms} ms` : "-"} />
            </div>
            <div className="permission-block">
              <strong>Allowed</strong>
              <div className="tool-list">
                {agent.allowed_tools.map((tool) => <span key={tool}>{tool}</span>)}
              </div>
            </div>
            <div className="permission-block denied">
              <strong>Denied</strong>
              <div className="tool-list">
                {agent.denied_tools.map((tool) => <span key={tool} className="denied">{tool}</span>)}
              </div>
            </div>
          </div>
        ))}
      </section>
    </main>
  );
}

function RegistryView({ registry }: { registry: AgentManifest[] }) {
  const [selectedId, setSelectedId] = useState<string | undefined>(registry[0]?.agent_id);
  const selected = registry.find((agent) => agent.agent_id === selectedId) ?? registry[0];
  const healthy = registry.filter((agent) => agent.health !== "DEGRADED").length;
  return (
    <main className="view registry-view">
      <section className="metrics-grid wide">
        <MetricCard label="Registered Agents" value={registry.length} />
        <MetricCard label="Healthy" value={healthy} tone="green" />
        <MetricCard label="Degraded" value={registry.length - healthy} tone={registry.length - healthy ? "red" : undefined} />
        <MetricCard label="Unavailable" value={0} />
      </section>
      <section className="split registry-split">
        <div className="panel">
          <div className="panel-header">
            <h2>Agent Registry</h2>
            <span className="model-badge">local fallback truthful</span>
          </div>
          <div className="table registry-table" role="table" aria-label="Agent registry">
            <div className="table-row table-head" role="row">
              <span>Agent</span>
              <span>Version</span>
              <span>Owner</span>
              <span>Runtime</span>
              <span>Identity</span>
              <span>Policy Scope</span>
              <span>Deployment</span>
              <span>Health</span>
            </div>
            {registry.map((agent) => (
              <button key={agent.agent_id} type="button" className="table-row registry-row" onClick={() => setSelectedId(agent.agent_id)}>
                <strong>{agent.name}</strong>
                <span>{agent.version}</span>
                <span>{agent.owner}</span>
                <span>{agent.runtime}</span>
                <span>{agent.identity}</span>
                <span>{agent.policy_scope.join(", ")}</span>
                <span>{agent.deployment}</span>
                <span className={cls("pill", statusTone(agent.health ?? "HEALTHY"))}>{agent.health ?? "HEALTHY"}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="panel registry-detail">
          {selected ? (
            <>
              <div className="panel-header">
                <div>
                  <p className="eyebrow">{selected.agent_id}</p>
                  <h2>{selected.name}</h2>
                </div>
                <span className="model-badge">{selected.version}</span>
              </div>
              <p>{selected.purpose}</p>
              <div className="detail-grid dense">
                <MetricCard label="Model" value={selected.model} />
                <MetricCard label="Runtime Status" value={selected.latest_status ?? selected.status} />
                <MetricCard label="Latest Execution" value={selected.last_execution ? formatTime(selected.last_execution) : "none"} />
                <MetricCard label="Latency" value={selected.latency_ms ? `${selected.latency_ms} ms` : "-"} />
              </div>
              <div className="permission-block">
                <strong>Permissions</strong>
                <div className="tool-list">{selected.allowed_tools.map((tool) => <span key={tool}>{tool}</span>)}</div>
              </div>
              <div className="permission-block denied">
                <strong>Denied Permissions</strong>
                <div className="tool-list">{selected.denied_tools.map((tool) => <span key={tool} className="denied">{tool}</span>)}</div>
              </div>
              <div className="setup-copy">
                <strong>Instructions Summary</strong>
                <span>{selected.instructions_summary}</span>
              </div>
            </>
          ) : <EmptyPanel title="NO AGENT SELECTED" body="Select a registry row to inspect the manifest." />}
        </div>
      </section>
    </main>
  );
}

function SecurityView({ events, agents }: { events: SecurityEvent[]; agents: AgentManifest[] }) {
  const physicalDenied = new Set(agents.flatMap((agent) => agent.denied_tools.filter((tool) => ["machine.control", "plc.write", "servo.reset"].includes(tool))));
  return (
    <main className="view">
      <section className="metrics-grid">
        <MetricCard label="Security Events" value={events.length} tone={events.length ? "red" : "green"} />
        <MetricCard label="Agent Identities" value={agents.length} />
        <MetricCard label="Enforced Permissions" value={agents.reduce((sum, agent) => sum + agent.allowed_tools.length + agent.denied_tools.length, 0)} />
        <MetricCard label="Physical Ops Denied" value={physicalDenied.size} tone="amber" />
      </section>
      <section className="panel security-panel">
        <div className="panel-header">
          <h2>Security Center</h2>
          <span className="model-badge">Knowledge is evidence. Knowledge is not policy.</span>
        </div>
        {events.length ? (
          <div className="security-event-grid">
            {events.map((event) => (
              <div key={event.security_event_id} className="security-event">
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">SECURITY EVENT</p>
                    <h3>{event.title}</h3>
                  </div>
                  <span className={cls("pill", event.decision === "DENY" || event.decision === "BLOCKED" ? "critical" : "amber")}>{event.decision ?? "BLOCKED"}</span>
                </div>
                <p>{event.description}</p>
                <div className="security-fields">
                  <span>Type</span><strong>{event.event_type}</strong>
                  <span>Source</span><strong>{event.source ?? "synthetic policy"}</strong>
                  <span>Agent</span><strong>{event.agent ?? event.principal ?? "unknown"}</strong>
                  <span>Requested Action</span><strong>{event.requested_action ?? event.denied_tool ?? "policy override"}</strong>
                  <span>Policy</span><strong>{event.policy ?? "least privilege"}</strong>
                  <span>Reason</span><strong>{event.reason ?? "Untrusted input cannot expand permissions"}</strong>
                  <span>Incident</span><strong>{event.incident_id ?? "none"}</strong>
                  <span>Trace</span><strong>{event.trace_id ?? "none"}</strong>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyPanel
            title="SECURITY NOMINAL"
            body="No policy violations or injection attempts detected."
            items={[
              `${agents.length} agent identities protected`,
              `${physicalDenied.size} physical-control operation classes permanently denied`,
              "Synthetic prompt-injection test will populate this page with blocked events.",
            ]}
          />
        )}
      </section>
    </main>
  );
}

function ObservabilityView({ traces, incidents, incident }: { traces: TraceSpan[]; incidents: Incident[]; incident?: Incident }) {
  const traceIds = Array.from(new Set(traces.map((span) => span.correlation_id)));
  const defaultTrace = incident?.correlation_id ?? traceIds[0];
  const [selectedTrace, setSelectedTrace] = useState<string | undefined>(defaultTrace);
  const activeTrace = selectedTrace ?? defaultTrace;
  const selectedSpans = traces.filter((span) => span.correlation_id === activeTrace).sort((a, b) => a.started_at.localeCompare(b.started_at));
  const selectedIncident = incidents.find((item) => item.correlation_id === activeTrace) ?? incident;
  const started = selectedSpans[0]?.started_at;
  const duration = selectedSpans.reduce((sum, span) => sum + (span.duration_ms ?? 0), 0);
  const agents = new Set(selectedSpans.map((span) => span.agent_id).filter(Boolean));
  const toolCalls = selectedSpans.reduce((sum, span) => {
    const calls = span.attributes?.tool_calls;
    return sum + (Array.isArray(calls) ? calls.length : span.name.includes(".") ? 1 : 0);
  }, 0);
  const retries = selectedIncident?.agent_runs?.reduce((sum, run) => sum + run.retry_count, 0) ?? 0;
  if (!traces.length) {
    return (
      <main className="view">
        <EmptyPanel
          title="NO DECISION TRACES YET"
          body="Agent activity will appear here when an operational incident is processed."
          items={["6 agents", "event ingestion", "tool execution", "policy decisions", "workflow transitions"]}
        />
      </main>
    );
  }
  return (
    <main className="view observability-view">
      <section className="trace-summary-grid">
        <div className="panel trace-picker">
          <div className="panel-header">
            <h2>Traces</h2>
            <span className="model-badge">{traceIds.length}</span>
          </div>
          {traceIds.map((traceId) => {
            const relatedIncident = incidents.find((item) => item.correlation_id === traceId);
            const count = traces.filter((span) => span.correlation_id === traceId).length;
            return (
              <button key={traceId} type="button" className={cls("trace-card", activeTrace === traceId && "selected")} onClick={() => setSelectedTrace(traceId)}>
                <strong>{traceId}</strong>
                <span>{relatedIncident?.incident_id ?? "system trace"}</span>
                <small>{count} spans</small>
              </button>
            );
          })}
        </div>
        <div className="panel">
          <div className="panel-header">
            <h2>Trace Explorer</h2>
            <span className="model-badge">{activeTrace ?? "all traces"}</span>
          </div>
          <div className="detail-grid dense">
            <MetricCard label="Incident" value={selectedIncident?.incident_id ?? "system"} />
            <MetricCard label="Status" value={selectedIncident?.status ?? "OK"} />
            <MetricCard label="Duration" value={formatDuration(duration)} />
            <MetricCard label="Started" value={formatTime(started)} />
            <MetricCard label="Agents" value={agents.size} />
            <MetricCard label="Tool Calls" value={toolCalls} />
            <MetricCard label="Retries" value={retries} tone={retries ? "amber" : undefined} />
          </div>
          <div className="trace-list">
            {selectedSpans.map((span) => {
              const calls = span.attributes?.tool_calls;
              return (
                <div key={span.span_id} className={cls("trace-span", stateClass(span.status))}>
                  <span>{formatTime(span.started_at)}</span>
                  <strong>{span.name}</strong>
                  <small>{span.agent_id ?? "system"} | {formatDuration(span.duration_ms)} | {span.status}</small>
                  {Array.isArray(calls) && calls.length > 0 && <small>Tools: {calls.join(", ")}</small>}
                  {typeof span.attributes?.error === "string" && <small className="error-text">{span.attributes.error}</small>}
                </div>
              );
            })}
          </div>
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
          <div>
            <p className="eyebrow">Provider Status</p>
            <h2>Cloud / Fallback Runtime</h2>
          </div>
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
              <p className="eyebrow">LOCAL DEMO ADMIN UNLOCK</p>
              <h2>Demo Control Lock</h2>
            </div>
            <Lock size={24} />
          </div>
          <p className="setup-note">
            This local PIN only gates synthetic demonstration controls. Production authorization is enforced separately by backend policy and cloud identity.
          </p>
          <form
            className="admin-pin-form"
            onSubmit={(event) => {
              event.preventDefault();
              void loadAdmin(pin);
            }}
          >
            <label htmlFor="admin-pin">Demo PIN</label>
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
          <p className="eyebrow">LOCAL DEMO ADMIN</p>
          <h2>Runtime Diagnostics</h2>
          <span className={cls("seed-status", seedEnabled ? "enabled" : "disabled")}>
            Seed {seedEnabled ? "enabled" : "disabled"} | {status.seed.collections.machines} machines | {status.seed.collections.knowledge_documents} knowledge docs
          </span>
        </div>
        <div className="control-groups compact-groups">
          <div className="control-group">
            <span>DATA</span>
            <button type="button" onClick={() => void loadAdmin()} disabled={adminBusy}>
              <RotateCcw size={18} /> Refresh
            </button>
            <button type="button" className="primary" onClick={() => void runAdminAction("import")} disabled={adminBusy}>
              <Database size={18} /> Import Seed
            </button>
            <button type="button" onClick={() => void runAdminAction(seedEnabled ? "disable" : "enable")} disabled={adminBusy}>
              <ShieldCheck size={18} /> {seedEnabled ? "Disable Seed" : "Enable Seed"}
            </button>
            <button type="button" onClick={() => void runAdminAction("smoke")} disabled={adminBusy}>
              <RadioTower size={18} /> Gemini Smoke
            </button>
          </div>
        </div>
      </section>

      {adminError && <div className="error-banner">{adminError}</div>}

      <section className="split">
        <div className="panel">
          <h2>Provider Readiness</h2>
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
              detail={status.gemini.google_cloud_project ?? "Not configured for local fallback"}
            />
            <SetupCheck
              label="gcloud CLI"
              ok={status.gemini.gcloud_on_path}
              detail={status.gemini.gcloud_on_path ? "gcloud is on PATH" : "Not required for local demo mode"}
            />
            <SetupCheck
              label="Model"
              ok={status.gemini.model === "gemini-3.5-flash"}
              detail={status.gemini.model}
            />
          </div>
          {smoke && <pre className="admin-json">{JSON.stringify(smoke, null, 2)}</pre>}
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
            <strong>Demo Boundary</strong>
            <span>Local PIN unlocks synthetic controls only. Policy decisions still execute in the backend and deny physical machine-control actions.</span>
          </div>
        </div>
      </section>

      <section className="admin-columns">
        <div className="panel">
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
        </div>

        <div className="panel">
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
              <strong>{doc.document_id} | {doc.title}</strong>
              <span>{doc.document_type} | rev {doc.revision} | approved={String(doc.approved)}</span>
              <small>{doc.tags.join(", ")}</small>
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
    const active = snapshot.incidents.find((incident) => !["LEARNED", "CANCELLED", "FAILED", "ESCALATED"].includes(incident.status));
    return active?.incident_id ?? snapshot.incidents.at(-1)?.incident_id;
  }, [snapshot.incidents]);

  const refresh = useCallback(async () => {
    const [facility, machines, workOrders, incidents, agents, registry, security, traces, approvals, system, demoSeed] = await Promise.all([
      api.facility(),
      api.machines(),
      api.workOrders(),
      api.incidents(),
      api.agents(),
      api.registry(),
      api.security(),
      api.traces(),
      api.approvals(),
      api.system(),
      api.demoSeedStatus(),
    ]);
    const latestIncidentId = incidents.find((incident) => !["LEARNED", "CANCELLED", "FAILED", "ESCALATED"].includes(incident.status))?.incident_id ?? incidents.at(-1)?.incident_id;
    const activeIncident = latestIncidentId ? await api.incident(latestIncidentId) : undefined;
    setSnapshot({ facility, machines, workOrders, incidents, agents, registry, security, traces, approvals, system, demoSeed, activeIncident });
    setError(null);
  }, []);

  useEffect(() => {
    void refresh().catch((caught: unknown) => setError(caught instanceof Error ? caught.message : "Unable to load Forge state"));
    const timer = window.setInterval(() => {
      void refresh().catch((caught: unknown) => setError(caught instanceof Error ? caught.message : "Unable to load Forge state"));
    }, 2000);
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
        if (name === "security_attack") setView("security");
        if (name === "failure" || name === "servo_alarm" || name === "maintenance_resolved") setView("incident");
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
        <nav aria-label="Primary navigation">
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
          <span>{snapshot.system?.synthetic_facility ?? "Synthetic Hackathon Facility"}</span>
          <strong>{snapshot.system?.model_provider ?? "loading"} | {snapshot.system?.model ?? "gemini-3.5-flash"}</strong>
        </div>
      </aside>
      <div className="content">
        <header className="topbar">
          <div>
            <p className="eyebrow">The autonomous operations fleet for the factory floor.</p>
            <h1>{view === "overview" ? "Operations Center" : view.charAt(0).toUpperCase() + view.slice(1)}</h1>
          </div>
          <div className="topbar-actions">
            <span className="model-badge">Synthetic Hackathon Facility</span>
            {error && <div className="error-banner">{error}</div>}
          </div>
        </header>
        {view === "overview" && <Overview snapshot={snapshot} onAction={handleAction} busy={busy} setView={setView} />}
        {view === "factory" && <FactoryView machines={snapshot.machines} workOrders={snapshot.workOrders} />}
        {view === "incident" && <IncidentCommand incident={snapshot.activeIncident} approvals={snapshot.approvals} workOrders={snapshot.workOrders} machines={snapshot.machines} onApprove={approve} onReject={reject} />}
        {view === "fleet" && <AgentFleetView agents={snapshot.agents} />}
        {view === "registry" && <RegistryView registry={snapshot.agents.length ? snapshot.agents : snapshot.registry} />}
        {view === "security" && <SecurityView events={snapshot.security} agents={snapshot.agents} />}
        {view === "observability" && <ObservabilityView traces={snapshot.traces} incidents={snapshot.incidents} incident={snapshot.activeIncident} />}
        {view === "cloud" && <CloudView system={snapshot.system} />}
        {view === "admin" && <AdminPanel onPlatformChange={refresh} />}
      </div>
    </div>
  );
}
