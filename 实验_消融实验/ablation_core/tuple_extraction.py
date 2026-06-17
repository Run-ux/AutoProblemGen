from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .config import TUPLE_DIR
from .problem_adapter import write_tuple_input
from .utils import read_json


EXTRACT_SCRIPT = TUPLE_DIR / "extract.py"
RUNTIME_GENERATION_LLM_ENV = "AUTOPROBLEMGEN_GENERATION_LLM_CONFIG"
DIMENSIONS = ("input_structure", "core_constraints", "objective", "invariant")


def extract_tuple_snapshot(
    *,
    problem_row: dict[str, Any],
    output_dir: Path,
    generation_llm: Any,
    resume: bool = True,
    temperature: float = 0.4,
) -> dict[str, Any]:
    problem_id = str(problem_row["problem_id"])
    tuple_dir = output_dir / "tuple"
    raw_dir = tuple_dir / "raw"
    input_path = output_dir / "tuple_input.json"
    raw_dir.mkdir(parents=True, exist_ok=True)
    write_tuple_input(input_path, problem_row)

    if not resume or not all((raw_dir / f"{problem_id}_{dimension}.json").is_file() for dimension in DIMENSIONS):
        env = os.environ.copy()
        env[RUNTIME_GENERATION_LLM_ENV] = json.dumps(generation_llm.to_runtime_payload(), ensure_ascii=False)
        command = [
            sys.executable,
            str(EXTRACT_SCRIPT),
            "--input",
            str(input_path),
            "--output",
            str(tuple_dir),
            "--temperature",
            str(temperature),
        ]
        if resume:
            command.append("--resume")
        completed = subprocess.run(
            command,
            cwd=str(TUPLE_DIR),
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=None,
        )
        (tuple_dir / "extract_stdout.log").write_text(completed.stdout, encoding="utf-8")
        (tuple_dir / "extract_stderr.log").write_text(completed.stderr, encoding="utf-8")
        if completed.returncode != 0:
            raise RuntimeError(
                f"四元组抽取子进程失败：problem_id={problem_id} returncode={completed.returncode} "
                f"stderr={completed.stderr[-2000:]}"
            )

    snapshot: dict[str, Any] = {}
    for dimension in DIMENSIONS:
        payload = read_json(raw_dir / f"{problem_id}_{dimension}.json")
        if not isinstance(payload, dict) or payload.get("status") != "success":
            raise RuntimeError(f"四元组抽取失败：problem_id={problem_id} dimension={dimension} payload={payload}")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise RuntimeError(f"四元组抽取结果非法：problem_id={problem_id} dimension={dimension}")
        snapshot[dimension] = result
    return snapshot
