from __future__ import annotations

import json
import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock


MODULE_DIR = Path(__file__).resolve().parents[1]
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

import main as workflow_main
from llm_trace import (
    WORKFLOW_LLM_TRACE_PATH,
    fail_call,
    finish_call,
    new_call_id,
    retry_call,
    start_call,
)
from orchestrator import CommandResult, TUPLE_DIMENSIONS, WorkflowConfig, run_workflow
from runtime_config import (
    ContextLimits,
    ExecutionLimits,
    LLMEndpointConfig,
    RUNTIME_CONTEXT_ENV,
    RUNTIME_EMBEDDING_LLM_ENV,
    RUNTIME_EXECUTION_ENV,
    RUNTIME_GENERATION_LLM_ENV,
    RuntimeConfigError,
    context_limits_from_runtime_env,
    execution_limits_from_runtime_env,
    llm_config_from_runtime_env,
)


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


def _make_workflow_config(
    *,
    input_path: Path,
    output_root: Path,
    run_id: str | None = "run",
    quality_iterations: int = 3,
    verification_timeout_seconds: float = 3600.0,
) -> WorkflowConfig:
    return WorkflowConfig(
        input_path=input_path,
        output_root=output_root,
        run_id=run_id,
        quality_iterations=quality_iterations,
        verification_timeout_seconds=verification_timeout_seconds,
        generation_llm=LLMEndpointConfig(
            api_key="secret-generation-key",
            base_url="https://generation.test/v1",
            model="chat-model",
            timeout_seconds=123.0,
            max_retries=4,
        ),
        embedding_llm=LLMEndpointConfig(
            api_key="secret-embedding-key",
            base_url="https://embedding.test/v1",
            model="embedding-model",
            timeout_seconds=45.0,
            max_retries=2,
        ),
        execution_limits=ExecutionLimits(
            test_input_timeout_seconds=6.0,
            test_input_memory_limit_mb=256,
            bruteforce_timeout_seconds=7.0,
            bruteforce_memory_limit_mb=384,
            checker_timeout_seconds=8.0,
            checker_memory_limit_mb=512,
        ),
        context_limits=ContextLimits(
            llm_case_max_chars=111,
            llm_case_input_max_chars=112,
            llm_case_output_max_chars=113,
            llm_case_total_chars=114,
            llm_case_max_count=5,
            max_llm_prompt_chars=115,
            llm_trace_max_text_chars=116,
        ),
    )


def _write_workflow_files(temp: Path, input_path: Path, *, quality_iterations: int = 3) -> Path:
    generation_path = temp / "generation_llm.env"
    embedding_path = temp / "embedding_llm.env"
    workflow_path = temp / f"workflow_{quality_iterations}.env"
    generation_path.write_text(
        "\n".join(
            [
                "API_KEY=secret-generation-key",
                "BASE_URL=https://generation.test/v1",
                "MODEL=chat-model",
                "TIMEOUT_SECONDS=123",
                "MAX_RETRIES=4",
            ]
        ),
        encoding="utf-8",
    )
    embedding_path.write_text(
        "\n".join(
            [
                "API_KEY=secret-embedding-key",
                "BASE_URL=https://embedding.test/v1",
                "MODEL=embedding-model",
                "TIMEOUT_SECONDS=45",
                "MAX_RETRIES=2",
            ]
        ),
        encoding="utf-8",
    )
    workflow_path.write_text(
        "\n".join(
            [
                f"INPUT_PATH={input_path}",
                f"OUTPUT_ROOT={temp / 'out'}",
                "RUN_ID=run",
                f"QUALITY_ITERATIONS={quality_iterations}",
                "QUALITY_FULL_SCORE_MAX_ITERATIONS=10",
                "VERIFICATION_TIMEOUT_SECONDS=3600",
                f"GENERATION_LLM_CONFIG={generation_path}",
                f"EMBEDDING_LLM_CONFIG={embedding_path}",
                "EXECUTION_TEST_INPUT_TIMEOUT_SECONDS=6",
                "EXECUTION_TEST_INPUT_MEMORY_LIMIT_MB=256",
                "EXECUTION_BRUTEFORCE_TIMEOUT_SECONDS=7",
                "EXECUTION_BRUTEFORCE_MEMORY_LIMIT_MB=384",
                "EXECUTION_CHECKER_TIMEOUT_SECONDS=8",
                "EXECUTION_CHECKER_MEMORY_LIMIT_MB=512",
                "LLM_CASE_MAX_CHARS=111",
                "LLM_CASE_INPUT_MAX_CHARS=112",
                "LLM_CASE_OUTPUT_MAX_CHARS=113",
                "LLM_CASE_TOTAL_CHARS=114",
                "LLM_CASE_MAX_COUNT=5",
                "MAX_LLM_PROMPT_CHARS=115",
                "LLM_TRACE_MAX_TEXT_CHARS=116",
            ]
        ),
        encoding="utf-8",
    )
    return workflow_path


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
        env: dict[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> CommandResult:
        self.calls.append(
            {
                "command": list(command),
                "cwd": cwd,
                "log_path": log_path,
                "env": dict(env or {}),
                "timeout_seconds": timeout_seconds,
            }
        )
        script = Path(command[1])
        if script.name == "extract.py":
            self._write_raw_outputs(command)
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
                        "result": self._dimension_result(dimension),
                    },
                )

    def _dimension_result(self, dimension: str) -> dict[str, Any]:
        if dimension == "input_structure":
            return {"type": "array", "length": {"min": 1, "max": 3}, "value_range": {"min": 0, "max": 9}}
        if dimension == "core_constraints":
            return {"constraints": [{"name": "limit", "description": "限制"}]}
        if dimension == "objective":
            return {"type": "optimization", "description": "最大化结果"}
        if dimension == "invariant":
            return {"invariants": [{"name": "state", "description": "状态不变量"}]}
        return {}

    def _write_generation_outputs(self, command: list[str]) -> None:
        source_dir = Path(_option(command, "--source-dir"))
        artifact_dir = Path(_option(command, "--artifact-dir"))
        output_dir = Path(_option(command, "--output-dir"))
        report_dir = Path(_option(command, "--report-dir"))
        problem_ids = [path.stem for path in sorted(source_dir.glob("*.json"))]
        items: list[dict[str, Any]] = []
        for problem_id in problem_ids:
            stem = f"{problem_id}_campus_ops_20260101_round1"
            artifact_path = artifact_dir / problem_id / f"{stem}.json"
            markdown_path = output_dir / problem_id / f"{stem}.md"
            quality_path = report_dir / problem_id / f"{stem}_quality_report.json"
            iteration_summary_path = artifact_dir / problem_id / f"{problem_id}_summary.json"
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
            record = {
                "artifact_path": str(artifact_path),
                "markdown_path": str(markdown_path),
                "quality_report_json_path": str(quality_path),
                "quality_report_md_path": str(quality_path.with_suffix(".md")),
                "iteration_summary_path": str(iteration_summary_path),
                "generated_status": self.generated_status,
                "final_round_index": 1,
            }
            items.append(
                {
                    "problem_id": problem_id,
                    "status": "completed",
                    "error_reason": "",
                    "record": record,
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


class RuntimeConfigTests(unittest.TestCase):
    def test_runtime_env_payload_round_trips_to_child_process_config(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            temp = Path(tempdir)
            input_path = temp / "A.json"
            _make_input(input_path)
            config = _make_workflow_config(input_path=input_path, output_root=temp / "out")

            with mock.patch.dict(os.environ, config.runtime_env(), clear=False):
                generation = llm_config_from_runtime_env(RUNTIME_GENERATION_LLM_ENV)
                embedding = llm_config_from_runtime_env(RUNTIME_EMBEDDING_LLM_ENV)
                execution_limits = execution_limits_from_runtime_env()
                context_limits = context_limits_from_runtime_env()

        self.assertEqual(generation.model, "chat-model")
        self.assertEqual(generation.api_key, "secret-generation-key")
        self.assertEqual(embedding.model, "embedding-model")
        self.assertEqual(embedding.api_key, "secret-embedding-key")
        self.assertEqual(execution_limits.test_input_timeout_seconds, 6.0)
        self.assertEqual(execution_limits.checker_memory_limit_mb, 512)
        self.assertEqual(context_limits.llm_case_max_chars, 111)
        self.assertEqual(context_limits.max_llm_prompt_chars, 115)


class LLMTraceTests(unittest.TestCase):
    def test_llm_trace_records_events_without_api_key_and_keeps_terminal_compact(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            trace_path = Path(tempdir) / "llm_calls.jsonl"
            stdout = io.StringIO()
            with mock.patch.dict(os.environ, {WORKFLOW_LLM_TRACE_PATH: str(trace_path)}, clear=False):
                with contextlib.redirect_stdout(stdout):
                    call_id = new_call_id()
                    started = start_call(
                        call_id=call_id,
                        task_name="unit_task",
                        model="chat-model",
                        endpoint="https://example.test/v1/chat/completions",
                        temperature=0.2,
                        timeout_seconds=30,
                        attempt=1,
                        max_retries=2,
                        system_prompt="SYSTEM_PROMPT_SECRET",
                        user_prompt="USER_PROMPT_SECRET",
                        payload={"api_key": "secret-generation-key", "messages": []},
                    )
                    retry_call(
                        call_id=call_id,
                        task_name="unit_task",
                        attempt=1,
                        max_retries=2,
                        elapsed_seconds=0.1,
                        error="temporary",
                        retry_delay_seconds=1.5,
                    )
                    finish_call(
                        call_id=call_id,
                        task_name="unit_task",
                        elapsed_seconds=0.2,
                        http_status=200,
                        response_text='{"status":"ok"}',
                        raw_response={"status": "ok", "api_key": "secret-generation-key"},
                        usage={"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
                        json_parse="success",
                        summary={"status": "ok"},
                    )
                    fail_call(
                        call_id=call_id,
                        task_name="unit_task",
                        attempt=2,
                        max_retries=2,
                        elapsed_seconds=0.3,
                        error="final",
                    )

            terminal = stdout.getvalue()
            self.assertIn("[llm call", terminal)
            self.assertIn("第 1/2 次未成功", terminal)
            self.assertIn("调用失败", terminal)
            self.assertNotIn("开始", terminal)
            self.assertNotIn("system_chars=", terminal)
            self.assertNotIn("返回成功", terminal)
            self.assertNotIn("SYSTEM_PROMPT_SECRET", terminal)
            self.assertNotIn("USER_PROMPT_SECRET", terminal)
            events = [
                json.loads(line)
                for line in trace_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual([event["event"] for event in events], ["start", "retry", "success", "failed"])
            trace_text = trace_path.read_text(encoding="utf-8")
            self.assertIn("SYSTEM_PROMPT_SECRET", trace_text)
            self.assertNotIn("secret-generation-key", trace_text)
            self.assertIn("[REDACTED]", trace_text)

    def test_llm_trace_truncates_large_prompt_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            trace_path = Path(tempdir) / "llm_calls.jsonl"
            env = {
                WORKFLOW_LLM_TRACE_PATH: str(trace_path),
                RUNTIME_CONTEXT_ENV: json.dumps({"llm_trace_max_text_chars": 30}),
            }
            with mock.patch.dict(os.environ, env, clear=False):
                start_call(
                    call_id=new_call_id(),
                    task_name="large_task",
                    model="chat-model",
                    endpoint="https://example.test",
                    temperature=0.2,
                    timeout_seconds=30,
                    attempt=1,
                    max_retries=1,
                    system_prompt="S" * 80,
                    user_prompt="U" * 80,
                    payload={"messages": [{"content": "P" * 80}]},
                )

            event = json.loads(trace_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertTrue(event["system_prompt_truncated"])
            self.assertTrue(event["user_prompt_truncated"])
            self.assertTrue(event["payload_truncated"])
            self.assertLess(len(event["system_prompt"]), 80)
            self.assertIn("truncated", event["system_prompt"])


class CliTests(unittest.TestCase):
    def test_cli_reads_workflow_config_and_rejects_disabled_quality_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            temp = Path(tempdir)
            input_path = Path(tempdir) / "A.json"
            _make_input(input_path)
            workflow_path = _write_workflow_files(temp, input_path)
            parser = workflow_main.build_parser()
            args = parser.parse_args(["--workflow-config", str(workflow_path)])
            config = WorkflowConfig.from_file(args.workflow_config)

            workflow_main.validate_config(parser, config)

            self.assertEqual(config.quality_iterations, 3)
            self.assertEqual(config.quality_full_score_max_iterations, 10)
            self.assertEqual(config.generation_llm.model, "chat-model")
            self.assertEqual(config.embedding_llm.model, "embedding-model")
            self.assertEqual(config.context_limits.llm_case_max_chars, 111)
            self.assertEqual(config.context_limits.llm_trace_max_text_chars, 116)

            bad_workflow_path = _write_workflow_files(temp, input_path, quality_iterations=0)
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    workflow_main.validate_config(parser, WorkflowConfig.from_file(bad_workflow_path))

    def test_workflow_config_rejects_removed_theme_and_variants(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            temp = Path(tempdir)
            input_path = temp / "A.json"
            _make_input(input_path)

            workflow_path = _write_workflow_files(temp, input_path)
            workflow_path.write_text(
                workflow_path.read_text(encoding="utf-8") + "\nVARIANTS=2\nTHEME=campus_ops\n",
                encoding="utf-8",
            )

            with self.assertRaises(RuntimeConfigError) as ctx:
                WorkflowConfig.from_file(workflow_path)
            message = str(ctx.exception)
            self.assertIn("VARIANTS", message)
            self.assertIn("THEME", message)


class OrchestratorTests(unittest.TestCase):
    def test_extract_failure_skips_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            temp = Path(tempdir)
            input_path = temp / "A.json"
            _make_input(input_path)
            runner = FakeCommandRunner(failed_dimensions={"A": {"objective"}})

            summary = run_workflow(
                _make_workflow_config(input_path=input_path, output_root=temp / "out"),
                command_runner=runner,
                progress_writer=lambda _: None,
            )

            self.assertEqual(summary["status"], "completed_with_failures")
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
                _make_workflow_config(
                    input_path=input_path,
                    output_root=temp / "out",
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
            self.assertNotIn("--variants", command)
            self.assertNotIn("--theme", command)
            source_dir = Path(_option(command, "--source-dir"))
            self.assertEqual(source_dir, temp / "out" / "run" / "generation" / "source" / "A")
            self.assertTrue((source_dir / "A.json").exists())
            source_payload = json.loads((source_dir / "A.json").read_text(encoding="utf-8"))
            self.assertEqual(source_payload["input_structure"]["type"], "array")
            self.assertEqual(source_payload["objective"]["type"], "optimization")
            self.assertEqual(source_payload["original_problem"]["title"], "示例题")
            self.assertIn("题面", source_payload["original_problem"]["description"])
            self.assertFalse(any(Path(call["command"][1]).name == "normalize.py" for call in runner.calls))
            self.assertIn(RUNTIME_GENERATION_LLM_ENV, generation_calls[0]["env"])
            self.assertIn(RUNTIME_EMBEDDING_LLM_ENV, generation_calls[0]["env"])
            self.assertIn(RUNTIME_EXECUTION_ENV, generation_calls[0]["env"])
            self.assertIn(RUNTIME_CONTEXT_ENV, generation_calls[0]["env"])
            self.assertEqual(summary["problems"][0]["status"], "quality_gate_failed")
            self.assertEqual(summary["problems"][0]["generation"]["status"], "quality_gate_failed")
            self.assertFalse(any(Path(call["command"][1]).name == "verification_runner.py" for call in runner.calls))

    def test_non_ok_generated_status_skips_quality_gate_paths_and_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            temp = Path(tempdir)
            input_path = temp / "A.json"
            _make_input(input_path)
            runner = FakeCommandRunner(
                quality_status="pass",
                generated_status="difference_insufficient",
                stop_reason="difference_insufficient",
            )

            summary = run_workflow(
                _make_workflow_config(input_path=input_path, output_root=temp / "out"),
                command_runner=runner,
                progress_writer=lambda _: None,
            )

            generation = summary["problems"][0]["generation"]
            self.assertEqual(summary["problems"][0]["status"], "quality_gate_failed")
            self.assertEqual(generation["status"], "quality_gate_failed")
            self.assertFalse(generation["quality_gate"]["passed"])
            self.assertIn("difference_insufficient", generation["quality_gate"]["reason"])
            self.assertFalse(any(Path(call["command"][1]).name == "verification_runner.py" for call in runner.calls))

    def test_empty_run_id_uses_stable_input_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            temp = Path(tempdir)
            input_path = temp / "A.json"
            _make_input(input_path)

            first = run_workflow(
                _make_workflow_config(input_path=input_path, output_root=temp / "out", run_id=None),
                command_runner=FakeCommandRunner(),
                progress_writer=lambda _: None,
            )
            second = run_workflow(
                _make_workflow_config(input_path=input_path, output_root=temp / "out", run_id=None),
                command_runner=FakeCommandRunner(),
                progress_writer=lambda _: None,
            )

            self.assertEqual(first["run_id"], second["run_id"])
            self.assertTrue(first["run_id"].startswith("input_A.json_"))
            self.assertEqual(first["run_id_source"], "INPUT_PATH 稳定指纹")

    def test_resume_skips_verified_problem_when_input_hash_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            temp = Path(tempdir)
            input_path = temp / "A.json"
            _make_input(input_path)

            first_runner = FakeCommandRunner()
            first = run_workflow(
                _make_workflow_config(input_path=input_path, output_root=temp / "out", run_id=None),
                command_runner=first_runner,
                progress_writer=lambda _: None,
            )
            second_runner = FakeCommandRunner()
            second = run_workflow(
                _make_workflow_config(input_path=input_path, output_root=temp / "out", run_id=None),
                command_runner=second_runner,
                progress_writer=lambda _: None,
            )

            self.assertEqual(first["status"], "completed")
            self.assertEqual(second["status"], "completed")
            self.assertEqual(second_runner.calls, [])
            self.assertTrue(second["problems"][0]["skipped_this_run"])

    def test_resume_reprocesses_verified_problem_when_input_hash_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            temp = Path(tempdir)
            input_path = temp / "A.json"
            _make_input(input_path)
            run_workflow(
                _make_workflow_config(input_path=input_path, output_root=temp / "out", run_id=None),
                command_runner=FakeCommandRunner(),
                progress_writer=lambda _: None,
            )
            _make_input(input_path, problem_id="A")
            payload = json.loads(input_path.read_text(encoding="utf-8"))
            payload["description"] = "题面已变化"
            _write_json(input_path, payload)

            runner = FakeCommandRunner()
            summary = run_workflow(
                _make_workflow_config(input_path=input_path, output_root=temp / "out", run_id=None),
                command_runner=runner,
                progress_writer=lambda _: None,
            )

            self.assertEqual(summary["status"], "completed")
            self.assertGreater(len(runner.calls), 0)
            self.assertFalse(summary["problems"][0].get("skipped_this_run", False))

    def test_directory_input_runs_full_workflow_per_problem_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            temp = Path(tempdir)
            input_dir = temp / "input"
            _make_input(input_dir / "A.json", "A")
            _make_input(input_dir / "B.json", "B")
            runner = FakeCommandRunner()

            summary = run_workflow(
                _make_workflow_config(input_path=input_dir, output_root=temp / "out"),
                command_runner=runner,
                progress_writer=lambda _: None,
            )

            self.assertEqual(summary["status"], "completed")
            stage_names = [stage["name"] for stage in summary["stages"]]
            self.assertEqual(stage_names[0], "tuple_extract:A")
            self.assertEqual(stage_names[1], "problem_generation:A")
            self.assertTrue(stage_names[2].startswith("verification:A:"))
            self.assertEqual(stage_names[3], "tuple_extract:B")
            self.assertEqual(stage_names[4], "problem_generation:B")
            self.assertTrue(stage_names[5].startswith("verification:B:"))
            generation_sources = [
                Path(_option(call["command"], "--source-dir"))
                for call in runner.calls
                if Path(call["command"][1]).name == "main.py"
                and Path(call["command"][1]).parent.name == "生成题面"
            ]
            self.assertEqual([path.name for path in generation_sources], ["A", "B"])
            self.assertTrue(all(len(list(path.glob("*.json"))) == 1 for path in generation_sources))

    def test_quality_pass_runs_verification_and_records_result_path(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            temp = Path(tempdir)
            input_path = temp / "A.json"
            _make_input(input_path)
            runner = FakeCommandRunner()

            summary = run_workflow(
                _make_workflow_config(
                    input_path=input_path,
                    output_root=temp / "out",
                    verification_timeout_seconds=12.5,
                ),
                command_runner=runner,
                progress_writer=lambda _: None,
            )

            verification_calls = [call for call in runner.calls if Path(call["command"][1]).name == "verification_runner.py"]
            self.assertEqual(len(verification_calls), 1)
            self.assertIsNone(verification_calls[0]["timeout_seconds"])
            generation = summary["problems"][0]["generation"]
            self.assertEqual(summary["status"], "completed")
            self.assertEqual(summary["problems"][0]["status"], "verified")
            self.assertEqual(generation["status"], "verified")
            self.assertFalse(summary["config"]["verification_outer_timeout_enabled"])
            self.assertEqual(summary["config"]["verification_timeout_seconds"], 12.5)
            self.assertTrue(Path(generation["verification_result_path"]).exists())
            self.assertTrue((temp / "out" / "run" / "workflow_summary.json").exists())
            summary_text = (temp / "out" / "run" / "workflow_summary.json").read_text(encoding="utf-8")
            self.assertNotIn("secret-generation-key", summary_text)
            self.assertNotIn("secret-embedding-key", summary_text)
            self.assertIn("chat-model", summary_text)

    def test_workflow_emits_stage_progress_messages(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            temp = Path(tempdir)
            input_path = temp / "A.json"
            _make_input(input_path)
            runner = FakeCommandRunner()
            messages: list[str] = []

            summary = run_workflow(
                _make_workflow_config(input_path=input_path, output_root=temp / "out"),
                command_runner=runner,
                progress_writer=messages.append,
            )

            self.assertEqual(summary["status"], "completed")
            self.assertTrue(messages)
            self.assertTrue(any("运行开始" in message for message in messages))
            self.assertTrue(any("题目总数=1" in message for message in messages))
            self.assertTrue(any("[problem 1/1] 开始处理" in message for message in messages))
            self.assertTrue(any("[stage 1/5] 四元组抽取开始" in message for message in messages))
            self.assertTrue(any("[stage 3/5] 题面生成开始" in message for message in messages))
            self.assertTrue(any("[stage 5/5] 验证完成" in message for message in messages))
            self.assertTrue(any("LLM 详细调用日志" in message for message in messages))

    def test_generation_command_failure_is_recorded_as_stage_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            temp = Path(tempdir)
            input_path = temp / "A.json"
            _make_input(input_path)
            runner = FakeCommandRunner(generation_returncode=1)

            summary = run_workflow(
                _make_workflow_config(input_path=input_path, output_root=temp / "out"),
                command_runner=runner,
                progress_writer=lambda _: None,
            )

            self.assertEqual(summary["status"], "failed")
            self.assertEqual(summary["stages"][-1]["name"], "problem_generation:A")
            self.assertEqual(summary["stages"][-1]["status"], "failed")
            self.assertIn("生成题面子进程失败", summary["error"])

    def test_verification_timeout_marks_variant_failed_without_hiding_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            temp = Path(tempdir)
            input_path = temp / "A.json"
            _make_input(input_path)
            runner = FakeCommandRunner(verification_timed_out=True)

            summary = run_workflow(
                _make_workflow_config(input_path=input_path, output_root=temp / "out"),
                command_runner=runner,
                progress_writer=lambda _: None,
            )

            self.assertEqual(summary["status"], "completed_with_failures")
            self.assertEqual(summary["problems"][0]["status"], "verification_failed")
            self.assertEqual(summary["problems"][0]["generation"]["status"], "verification_failed")
            self.assertTrue(summary["stages"][-1]["timed_out"])


if __name__ == "__main__":
    unittest.main()
