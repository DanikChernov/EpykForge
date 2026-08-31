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
  WorkOrder,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8080";
const DEMO_TOKEN = import.meta.env.VITE_DEMO_SUPERVISOR_TOKEN ?? "demo-supervisor-token";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export const api = {
  facility: () => request<Facility>("/api/facility"),
  machines: () => request<Machine[]>("/api/machines"),
  workOrders: () => request<WorkOrder[]>("/api/work-orders"),
  incidents: () => request<Incident[]>("/api/incidents"),
  incident: (incidentId: string) => request<Incident>(`/api/incidents/${incidentId}`),
  agents: () => request<AgentManifest[]>("/api/agents"),
  registry: () => request<AgentManifest[]>("/api/registry"),
  security: () => request<SecurityEvent[]>("/api/security/events"),
  traces: () => request<TraceSpan[]>("/api/traces"),
  approvals: () => request<Approval[]>("/api/approvals"),
  system: () => request<SystemInfo>("/api/system/info"),
  demoSeedStatus: () => request<DemoSeedStatus>("/api/demo/seed/status"),
  importDemoSeed: () => request<DemoSeedStatus & { status: string }>("/api/demo/seed/import", { method: "POST" }),
  enableDemoSeed: () => request<DemoSeedStatus & { status: string }>("/api/demo/seed/enable", { method: "POST" }),
  disableDemoSeed: () => request<DemoSeedStatus & { status: string }>("/api/demo/seed/disable", { method: "POST" }),
  adminSetupStatus: (pin: string) => request<AdminSetupStatus>("/api/admin/setup/status", { headers: { "x-admin-pin": pin } }),
  adminSeedPreview: (pin: string) => request<AdminSeedPreview>("/api/admin/seed/preview", { headers: { "x-admin-pin": pin } }),
  adminImportSeed: (pin: string) => request<DemoSeedStatus & { status: string }>("/api/admin/seed/import", { method: "POST", headers: { "x-admin-pin": pin } }),
  adminEnableSeed: (pin: string) => request<DemoSeedStatus & { status: string }>("/api/admin/seed/enable", { method: "POST", headers: { "x-admin-pin": pin } }),
  adminDisableSeed: (pin: string) => request<DemoSeedStatus & { status: string }>("/api/admin/seed/disable", { method: "POST", headers: { "x-admin-pin": pin } }),
  adminGeminiSmoke: (pin: string) => request<Record<string, unknown>>("/api/admin/gemini/smoke", { method: "POST", headers: { "x-admin-pin": pin } }),
  resetDemo: () => request<{ status: string }>("/api/demo/reset", { method: "POST" }),
  startDemo: () => request<{ status: string; incident_id?: string }>("/api/demo/start", { method: "POST", body: JSON.stringify({ sync: false }) }),
  startDemoSync: () => request<{ status: string; incident_id?: string }>("/api/demo/start", { method: "POST", body: JSON.stringify({ sync: true, speed: 99 }) }),
  inject: (name: string) => request<Record<string, unknown>>(`/api/demo/inject/${name}`, { method: "POST" }),
  approve: (incidentId: string, approvalId?: string) =>
    request<Record<string, unknown>>(`/api/incidents/${incidentId}/approve`, {
      method: "POST",
      headers: { "x-demo-token": DEMO_TOKEN },
      body: JSON.stringify({ approval_id: approvalId, decision_note: "Approved in synthetic demo console" }),
    }),
  reject: (incidentId: string, approvalId?: string) =>
    request<Record<string, unknown>>(`/api/incidents/${incidentId}/reject`, {
      method: "POST",
      headers: { "x-demo-token": DEMO_TOKEN },
      body: JSON.stringify({ approval_id: approvalId, decision_note: "Rejected in synthetic demo console" }),
    }),
};
