from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from forge.agents.fleet import load_prompts  # noqa: E402
from forge.agents.adk_runtime import build_adk_agents  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy EPYK Forge ADK agents to Agent Runtime.")
    parser.add_argument("--project", default=os.environ.get("GOOGLE_CLOUD_PROJECT"), required=False)
    parser.add_argument("--location", default=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"))
    parser.add_argument("--bucket", default=os.environ.get("FORGE_AGENT_STAGING_BUCKET"))
    parser.add_argument("--model", default=os.environ.get("FORGE_GEMINI_MODEL", "gemini-3.5-flash"))
    args = parser.parse_args()
    if not args.project or not args.bucket:
        raise SystemExit("Set --project and --bucket or GOOGLE_CLOUD_PROJECT and FORGE_AGENT_STAGING_BUCKET.")

    try:
        import vertexai
        from vertexai.agent_engines import AdkApp
    except Exception as exc:
        raise SystemExit(f"Install google-cloud-aiplatform[agent_engines,adk] first: {exc}") from exc

    status, agents = build_adk_agents(args.model, load_prompts())
    if not status.available:
        raise SystemExit(status.message)

    client = vertexai.Client(project=args.project, location=args.location)
    for agent_id, agent in agents.items():
        adk_app = AdkApp(agent=agent)
        engine = client.agent_engines.create(
            agent_engine=adk_app,
            config={
                "staging_bucket": args.bucket,
                "display_name": f"epyk-forge-{agent_id}",
                "requirements": ["google-cloud-aiplatform[agent_engines,adk]", "google-adk"],
                "env_vars": {
                    "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY": "true",
                    "OTEL_SEMCONV_STABILITY_OPT_IN": "gen_ai_latest_experimental",
                    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "EVENT_ONLY",
                },
            },
        )
        print(f"{agent_id}: {engine.api_resource.name}")


if __name__ == "__main__":
    asyncio.run(main())
