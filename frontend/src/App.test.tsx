import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { App } from "./App";

vi.mock("./api", () => ({
  api: {
    facility: () => Promise.resolve({
      facility_name: "Northstar Precision Works",
      synthetic: true,
      health_score: 92,
      machines_total: 1,
      machines_running: 1,
      machines_idle: 0,
      machines_alarmed: 0,
      machines_maintenance: 0,
      active_incidents: 0,
      at_risk_orders: 0,
      agent_fleet_status: "ACTIVE",
      model_provider: "TEST_STUB",
    }),
    machines: () => Promise.resolve([]),
    incidents: () => Promise.resolve([]),
    agents: () => Promise.resolve([]),
    registry: () => Promise.resolve([]),
    security: () => Promise.resolve([]),
    traces: () => Promise.resolve([]),
    approvals: () => Promise.resolve([]),
    system: () => Promise.resolve({
      product: "EPYK Forge",
      synthetic_facility: "Northstar Precision Works",
      environment: "local",
      service: "forge-api",
      model: "gemini-3.5-flash",
      model_provider: "TEST_STUB",
      agent_framework: "Google ADK",
      adk_status: "loaded",
      event_bus: "in-process event bus",
      state_store: "local JSON store",
      managed_agent_platform: {},
      cloud_claim_active: false,
    }),
  },
}));

describe("App", () => {
  it("renders the operations center", async () => {
    render(<App />);
    expect(await screen.findByText("Operations Center")).toBeInTheDocument();
    expect(screen.getByText("SYNTHETIC DEMO CONTROLS")).toBeInTheDocument();
  });
});
