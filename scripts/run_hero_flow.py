from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from forge.api.main import services  # noqa: E402


def main() -> None:
    result = services.runner.run_hero(speed=99, sleep=False)
    print(json.dumps(result, indent=2))
    print(json.dumps(services.store.get("incidents", "INC-1042"), indent=2))


if __name__ == "__main__":
    main()
