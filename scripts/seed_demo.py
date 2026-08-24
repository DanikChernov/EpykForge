from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from forge.config.settings import get_settings  # noqa: E402
from forge.repositories.local_store import LocalStore  # noqa: E402
from forge.simulator.seed import build_seed_state  # noqa: E402


def main() -> None:
    settings = get_settings()
    store = LocalStore(settings.state_path)
    store.reset(build_seed_state(settings.gemini_model))
    print(f"Seeded EPYK Forge demo state at {settings.state_path}")


if __name__ == "__main__":
    main()
