from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AdkStatus:
    available: bool
    message: str


def build_adk_agents(model: str, prompts: dict[str, str]) -> tuple[AdkStatus, dict[str, Any]]:
    """Create ADK LlmAgent instances when google-adk is installed.

    The application-level orchestrator remains the deterministic event-driven
    control plane. These ADK agent objects are the deployable agent definitions
    used by Agent Runtime scripts and documented registry entries.
    """

    try:
        from google.adk.agents import LlmAgent
    except Exception as exc:  # pragma: no cover - depends on optional installed SDK
        return AdkStatus(False, f"google-adk unavailable: {exc}"), {}

    agents: dict[str, Any] = {}
    for agent_id, instruction in prompts.items():
        agents[agent_id] = LlmAgent(
            name=agent_id.replace("-", "_"),
            model=model,
            instruction=instruction,
            description=f"EPYK Forge {agent_id} for synthetic factory operations",
        )
    return AdkStatus(True, "google-adk LlmAgent definitions loaded"), agents
