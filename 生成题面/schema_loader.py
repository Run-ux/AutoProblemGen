from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SchemaLoader:
    def __init__(self, source_dir: Path):
        self.source_dir = source_dir

    def list_problem_ids(self) -> list[str]:
        return sorted(path.stem for path in self.source_dir.glob("*.json"))

    def load(self, problem_id: str) -> dict[str, Any]:
        path = self.source_dir / f"{problem_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Schema file not found: {path}")
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

