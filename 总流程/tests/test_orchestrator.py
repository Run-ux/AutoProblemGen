from __future__ import annotations

import json
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


MODULE_DIR = Path(__file__).resolve().parents[1]
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

import main as workflow_main
from orchestrator import CommandResult, TUPLE_DIMENSIONS, WorkflowConfig, run_workflow


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _option(command: list[str], name: str) -> str:
    index = command.index(name)
    return command[index + 1]


def _make_input(path: Path, problem_id: str = "A") -> None:
    _write_json(
        path,
        {
            "problem_id": problem_id,
            "title": "示例题",
            "description": "题面\nInput\n输入\nOutput\n输出",
            "source": {"source_name": "codeforces"},
        },
    )


class FakeCommandRunner:
    def __init__(
        self,
        *,
        failed_dimensions: dict[str, set[str]] | None = None,
        quality_status: str = "pass",
        generated_status: str = "ok",
        stop_reason: str = "pass",
        generation_returncode: int = 0,
        verification_returncode: int = 0,
        verification_timed_out: bool = False,
    ) -> None:
        self.failed_dimensions = failed_dimensions or {}
        self.quality_status = quality_status
        self.generated_status = generated_status
        self.stop_reason = stop_reason
        self.generation_returncode = generation_returncode
        self.verification_returncode = verification_returncode
        self.verification_timed_out = verification_timed_out
        self.calls: list[dict[str, Any]] = []
        self.problem_ids: list[str] = []

    def __call__(
        self,
        command: list[str],
        *,
        cwd: Path,
        log_path: Path,
        timeout_seconds: float | None = None,
    ) -> CommandResult:
        self.calls.append(
            {
                "command": list(command),
                "cwd": cwd,
                "log_path": log_path,
                "timeout_seconds": timeout_seconds,
            }
        )
        script = Path(command[1])
        if script.name == "extract.py":
            self._write_raw_outputs(command)
            return self._result(command, cwd, log_path)
        if script.name == "normalize.py":
            self._write_normalized_outputs(command)
            return self._result(command, cwd, log_path)
        if script.name == "main.py" and script.parent.name == "生成题面":
            if self.generation_returncode:
                return self._result(command, cwd, log_path, returncode=self.generation_returncode)
            self._write_generation_outputs(command)
            return self._result(command, cwd, log_path)
        if script.name == "verification_runner.py":
            if not self.verification_timed_out and self.verification_returncode == 0:
                output_path = Path(_option(command, "--output"))
                _write_json(output_path, {"status": "ok"})
            return self._result(
                command,
                cwd,
                log_path,
                returncode=self.verification_returncode if not self.verification_timed_out else -1,
                timed_out=self.verification_timed_out,
            )
        raise AssertionError(f"未预期的命令: {command}")

    def _result(
        self,
        command: list[str],
        cwd: Path,
        log_path: Path,
        *,
        returncode: int = 0,
        timed_out: bool = False,
    ) -> CommandResult:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("fake log", encoding="utf-8")
        return CommandResult(
            command=list(command),
            cwd=str(cwd),
            log_path=str(log_path),
            returncode=returncode,
            timed_out=timed_out,
        )

    def _write_raw_outputs(self, command: list[str]) -> None:
        input_path = Path(_option(command, "--input"))
        output_dir = Path(_option(command, "--output"))
        self.problem_ids = self._read_problem_ids(input_path)
        raw_dir = output_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        for problem_id in self.problem_ids:
            failed = self.failed_dimensions.get(problem_id, set())
            for dimension in TUPLE_DIMENSIONS:
                status = "failed" if dimension in failed else "success"
                _write_json(
                    raw_dir / f"{problem_id}_{dimension}.json",
                    {
                        "problem_id": problem_id,
                        "source": "codeforces",
                        "dimension": dimension,
                        "status": status,
                        "result": {},
                    },
                )

    def _write_normalized_outputs(self, command: list[str]) -> None:
        output_dir = Path(_option(command, "--output"))
        output_dir.mkdir(parents=True, exist_ok=True)
        for problem_id in self.problem_ids:
            _write_json(
                output_dir / f"{problem_id}.json",
                {
                    "problem_id": problem_id,
                    "source": "codeforces",
                    "input_structure": {"type": "array"},
                    "core_constraints": {"constraints": []},
                    "objective": {"type": "optimization"},
                    "invariant": {"invariants": []},
                },
            )

    def _write_generation_outputs(self, command: list[str]) -> None:
        source_dir = Path(_option(command, "--source-dir"))
        artifact_dir = Path(_option(command, "--artifact-dir"))
        output_dir = Path(_option(command, "--output-dir"))
        report_dir = Path(_option(command, "--report-dir"))
        variants = int(_option(command, "--variants"))
        problem_ids = [path.stem for path in sorted(source_dir.glob("*.json"))]
        items: list[dict[str, Any]] = []
        for problem_id in problem_ids:
            variant_records: list[dict[str, Any]] = []
            for variant_index in range(1, variants + 1):
                stem = f"{problem_id}_v{variant_index}_campus_ops_20260101_round1"
                artifact_path = artifact_dir / problem_id / f"{stem}.json"
                markdown_path = output_dir / problem_id / f"{stem}.md"
                quality_path = report_dir / problem_id / f"{stem}_quality_report.json"
                iteration_summary_path = artifact_dir / problem_id / f"{problem_id}_v{variant_index}_summary.json"
                _write_json(artifact_path, {"generated_problem": {"status": self.generated_status}})
                markdown_path.parent.mkdir(parents=True, exist_ok=True)
                markdown_path.write_text("# fake", encoding="utf-8")
                _write_json(
                    quality_path,
                    {
                        "overall": {
                            "status": self.quality_status,
                            "generated_status": self.generated_status,
                        }
                    },
                )
                _write_json(iteration_summary_path, {"stop_reason": self.stop_reason})
                variant_records.append(
                    {
                        "artifact_path": str(artifact_path),
                        "markdown_path": str(markdown_path),
                        "quality_report_json_path": str(quality_path),
                        "quality_report_md_path": str(quality_path.with_suffix(".md")),
                        "iteration_summary_path": str(iteration_summary_path),
                        "generated_status": self.generated_status,
                        "final_round_index": 1,
                    }
                )
            items.append(
                {
                    "problem_id": problem_id,
                    "status": "completed",
                    "error_reason": "",
                    "variant_records": variant_records,
                }
            )
        _write_json(artifact_dir / "batch_20260101_000000.json", {"items": items, "status": "completed"})

    def _read_problem_ids(self, input_path: Path) -> list[str]:
        files = sorted(input_path.glob("*.json")) if input_path.is_dir() else [input_path]
        result: list[str] = []
        for path in files:
            payload = json.loads(path.read_text(encoding="utf-8"))
            result.append(str(payload["problem_id"]))
        return result

    def stage_calls(self, script_name: str) -> list[dict[str, Any]]:
        return [call for call in self.calls if Path(call["command"][1]).name == script_name]


class CliTests(unittest.TestCase):
    def test_cli_defaults_and_rejects_disabled_quality_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            input_path = Path(tempdir) / "A.json"
            _make_input(input_path)
            parser = workflow_main.build_parser()
            args = parser.parse_args(["--input", str(input_path)])

            workflow_main.validate_args(parser, args)

            self.assertEqual(args.quality_iterations, 3)
            self.assertEqual(args.quality_full_score_max_iterations, 10)
            self.assertEqual(args.embedding_threshold, 0.85)

            bad_args = parser.parse_args(["--input", str(input_path), "--quality-iterations", "0"])
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    workflow_main.validate_args(parser, bad_args)


class OrchestratorTests(unittest.TestCase):
    def test_extract_failure_skips_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            temp = Path(tempdir)
            input_path = temp / "A.json"
            _make_input(input_path)
            runner = FakeCommandRunner(failed_dimensions={"A": {"objective"}})

            summary = run_workflow(
                WorkflowConfig(input_path=input_path, output_root=temp / "out", run_id="run"),
                command_runner=runner,
                progress_writer=lambda _: None,
            )

            self.assertEqual(summary["status"], "failed")
            self.assertEqual(summary["problems"][0]["status"], "skipped_before_generation")
            self.assertFalse(
                any(Path(call["command"][1]).parent.name == "生成题面" for call in runner.calls)
            )

    def test_generation_command_uses_quality_iterations_and_isolated_source_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            temp = Path(tempdir)
            input_path = temp / "A.json"
            _make_input(input_path)
            runner = FakeCommandRunner(quality_status="revise_quality", stop_reason="reached_requested_rounds")

            summary = run_workflow(
                WorkflowConfig(
                    input_path=input_path,
                    output_root=temp / "out",
                    run_id="run",
                    variants=2,
                    quality_iterations=3,
                ),
                command_runner=runner,
                progress_writer=lambda _: None,
            )

            generation_calls = [
                call
                for call in runner.calls
                if Path(call["command"][1]).name == "main.py"
                and Path(call["command"][1]).parent.name == "生成题面"
            ]
            self.assertEqual(len(generation_calls), 1)
            command = generation_calls[0]["command"]
            self.assertEqual(_option(command, "--quality-iterations"), "3")
            self.assertEqual(_option(command, "--variants"), "2")
            source_dir = Path(_option(command, "--source-dir"))
            self.assertEqual(source_dir, temp / "out" / "run" / "generation" / "source")
            self.assertTrue((source_dir / "A.json").exists())
            self.assertEqual(summary["problems"][0]["status"], "quality_gate_failed")
            self.assertFalse(any(Path(call["command"][1]).name == "verification_runner.py" for call in runner.calls))

    def test_quality_pass_runs_verification_and_records_result_path(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            temp = Path(tempdir)
            input_path = temp / "A.json"
            _make_input(input_path)
            runner = FakeCommandRunner()

            summary = run_workflow(
                WorkflowConfig(
                    input_path=input_path,
                    output_root=temp / "out",
                    run_id="run",
                    verification_timeout_seconds=12.5,
                ),
                command_runner=runner,
                progress_writer=lambda _: None,
            )

            verification_calls = [call for call in runner.calls if Path(call["command"][1]).name == "verification_runner.py"]
            self.assertEqual(len(verification_calls), 1)
            self.assertEqual(verification_calls[0]["timeout_seconds"], 12.5)
            variant = summary["problems"][0]["variants"][0]
            self.assertEqual(summary["status"], "completed")
            self.assertEqual(summary["problems"][0]["status"], "verified")
            self.assertEqual(variant["status"], "verified")
            self.assertTrue(Path(variant["verification_result_path"]).exists())
            self.assertTrue((temp / "out" / "run" / "workflow_summary.json").exists())

    def test_generation_command_failure_is_recorded_as_stage_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            temp = Path(tempdir)
            input_path = temp / "A.json"
            _make_input(input_path)
            runner = FakeCommandRunner(generation_returncode=1)

            summary = run_workflow(
                WorkflowConfig(input_path=input_path, output_root=temp / "out", run_id="run"),
                command_runner=runner,
                progress_writer=lambda _: None,
            )

            self.assertEqual(summary["status"], "failed")
            self.assertEqual(summary["stages"][-1]["name"], "problem_generation")
            self.assertEqual(summary["stages"][-1]["status"], "failed")
            self.assertIn("生成题面阶段失败", summary["error"])

    def test_verification_timeout_marks_variant_failed_without_hiding_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            temp = Path(tempdir)
            input_path = temp / "A.json"
            _make_input(input_path)
            runner = FakeCommandRunner(verification_timed_out=True)

            summary = run_workflow(
                WorkflowConfig(input_path=input_path, output_root=temp / "out", run_id="run"),
                command_runner=runner,
                progress_writer=lambda _: None,
            )

            self.assertEqual(summary["status"], "completed_with_failures")
            self.assertEqual(summary["problems"][0]["status"], "verification_failed")
            self.assertEqual(summary["problems"][0]["variants"][0]["status"], "verification_failed")
            self.assertTrue(summary["stages"][-1]["timed_out"])


if __name__ == "__main__":
    unittest.main()
