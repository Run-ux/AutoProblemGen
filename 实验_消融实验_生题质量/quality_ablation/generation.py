from __future__ import annotations

import json
import random
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from .manifest import load_manifest
from .utils import (
    DEFAULT_WORKFLOW_CONFIG,
    GENERATION_DIR,
    GENERATED_CONDITIONS,
    TUPLE_FIELDS,
    limited_rows,
    read_json,
    safe_name,
    sha256_text,
    shard_file_suffix,
    sharded_rows,
    stable_hash,
    utc_now_iso,
    write_json,
    write_text,
)

from markdown_renderer import render_problem_markdown
from models import DifferencePlan, GeneratedProblem, NewSchema, Theme, VariantPlan
from problem_generator import ProblemGenerator
from problem_quality import ProblemEvaluator
from problem_quality.report_renderer import render_report_markdown as render_quality_report_markdown
from qwen_client import QwenClient
from rulebook import RuleBook
from schema_tools import compute_changed_axes, compute_schema_distance
from variant_planner import THEMES, VariantPlanner

from orchestrator import WorkflowConfig
from pipeline import GenerationPipeline


DECLARED_FAILURE_STATUSES = {"schema_insufficient", "difference_insufficient"}


def run_generations(
    *,
    manifest_path: Path,
    output_root: Path,
    run_id: str,
    workflow_config_path: Path = DEFAULT_WORKFLOW_CONFIG,
    conditions: list[str] | None = None,
    limit: int | None = None,
    resume: bool = True,
    shard_count: int = 1,
    shard_index: int = 0,
    progress_writer: Callable[[str], None] | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    progress = progress_writer or (lambda message: print(message, flush=True))
    selected_conditions = conditions or list(GENERATED_CONDITIONS)
    for condition in selected_conditions:
        if condition not in ("full", *GENERATED_CONDITIONS):
            raise ValueError(f"未知实验组：{condition}")

    manifest = load_manifest(manifest_path)
    limited_problems = limited_rows(list(manifest["problems"]), limit)
    problems = sharded_rows(limited_problems, shard_count=shard_count, shard_index=shard_index)
    file_suffix = shard_file_suffix(shard_count=shard_count, shard_index=shard_index)
    run_dir = output_root.resolve() / safe_name(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    active_client = client or _load_qwen_client(workflow_config_path)

    outcomes: list[dict[str, Any]] = []
    write_json(
        run_dir / f"run_metadata{file_suffix}.json",
        {
            "schema_version": 1,
            "run_id": run_id,
            "manifest_path": str(manifest_path.resolve()),
            "condition_count": len(selected_conditions),
            "conditions": selected_conditions,
            "problem_count": len(problems),
            "limited_problem_count": len(limited_problems),
            "shard_count": shard_count,
            "shard_index": shard_index,
            "started_at": utc_now_iso(),
            "workflow_config_path": str(workflow_config_path.resolve()),
        },
    )

    for problem_index, problem in enumerate(problems, start=1):
        problem_id = str(problem["problem_id"])
        for condition in selected_conditions:
            progress(f"[run {problem_index}/{len(problems)}] {condition} {problem_id}")
            result = run_condition(
                problem=problem,
                condition=condition,
                run_dir=run_dir,
                client=active_client,
                resume=resume,
                progress_writer=progress,
            )
            outcomes.append(result)

    summary = {
        "run_dir": str(run_dir),
        "conditions": selected_conditions,
        "problem_count": len(problems),
        "limited_problem_count": len(limited_problems),
        "shard_count": shard_count,
        "shard_index": shard_index,
        "outcomes": outcomes,
        "completed_count": sum(item.get("status") == "completed" for item in outcomes),
        "declared_failure_count": sum(item.get("status") == "declared_failure" for item in outcomes),
        "failed_count": sum(item.get("status") == "failed" for item in outcomes),
    }
    write_json(run_dir / f"run_summary{file_suffix}.json", summary)
    return summary


def run_condition(
    *,
    problem: dict[str, Any],
    condition: str,
    run_dir: Path,
    client: Any,
    resume: bool = True,
    progress_writer: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    problem_id = str(problem["problem_id"])
    result_dir = run_dir / "generations" / condition / safe_name(problem_id)
    result_path = result_dir / "result.json"
    if resume and result_path.is_file():
        try:
            return read_json(result_path)
        except Exception:
            pass

    try:
        if condition == "full":
            result = _materialize_full_result(problem=problem, result_dir=result_dir)
        elif condition == "no_quality_loop":
            result = _run_no_quality_loop(
                problem=problem,
                result_dir=result_dir,
                client=client,
                progress_writer=progress_writer,
            )
        elif condition in {"no_tuple", "no_rules"}:
            result = _run_custom_condition(
                problem=problem,
                condition=condition,
                result_dir=result_dir,
                client=client,
            )
        else:
            raise ValueError(f"未知实验组：{condition}")
    except Exception as exc:  # noqa: BLE001 - 单题失败应落盘，避免整批中断。
        result = {
            "schema_version": 1,
            "problem_id": problem_id,
            "condition": condition,
            "status": "failed",
            "generated_status": "",
            "is_declared_failure": False,
            "artifact_path": "",
            "markdown_path": "",
            "quality_report_json_path": "",
            "quality_report_md_path": "",
            "iteration_summary_path": "",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "result_path": str(result_path),
        }
    write_json(result_path, result)
    return result


def build_custom_generation_prompts(
    *,
    condition: str,
    source_payload: dict[str, Any],
    rules_summary: list[dict[str, Any]] | None = None,
    revision_context: dict[str, Any] | None = None,
) -> tuple[str, str]:
    if condition == "no_tuple":
        system_prompt = """你是一名算法竞赛命题人，正在参加组件消融实验。

本组禁用外部结构抽取结果。你只能根据原题文本、元信息和规则摘要理解原题，并生成一个新题。
你需要先从原题文本中自行归纳工作 schema，再在规则摘要指导下生成新题规划和题面。
不要暴露原题编号、出处、链接或“改编自某题”等信息。
输出必须是严格 JSON。"""
        user_payload = {
            "condition": "without_extracted_tuple",
            "seed_metadata": _seed_metadata(source_payload),
            "original_problem": source_payload.get("original_problem", {}),
            "available_rule_summaries": rules_summary or [],
            "revision_context": revision_context or {},
            "output_contract": _custom_output_contract(require_seed_schema_estimate=True),
        }
    elif condition == "no_rules":
        system_prompt = """你是一名算法竞赛命题人，正在参加组件消融实验。

本组禁用规则库。你可以使用给定的原题结构化描述和原题文本，但不能依赖任何预设规则、helper 或规则专属审查。
请用通用规划能力生成一个新题，要求至少在 I/C/O/V 四个语义轴中实质改变两个轴，并避免表层换皮。
不要暴露原题编号、出处、链接或“改编自某题”等信息。
输出必须是严格 JSON。"""
        user_payload = {
            "condition": "without_planning_rules",
            "seed_schema": _schema_only(source_payload),
            "original_problem": source_payload.get("original_problem", {}),
            "revision_context": revision_context or {},
            "generic_planning_requirements": [
                "至少实质改变 I/C/O/V 中两个轴。",
                "新题主要求解义务必须不同于原题，不能只是改名、换背景或输出包装。",
                "题面必须完整包含描述、输入格式、输出格式、约束、至少两组样例和说明。",
            ],
            "output_contract": _custom_output_contract(require_seed_schema_estimate=False),
        }
    else:
        raise ValueError(f"不支持自定义生成的实验组：{condition}")
    return system_prompt, json.dumps(user_payload, ensure_ascii=False, indent=2)


def condition_quality_iterations(condition: str) -> int:
    if condition == "no_quality_loop":
        return 0
    if condition in {"no_tuple", "no_rules", "full"}:
        return 3
    raise ValueError(f"未知实验组：{condition}")


def _run_custom_condition(
    *,
    problem: dict[str, Any],
    condition: str,
    result_dir: Path,
    client: Any,
) -> dict[str, Any]:
    problem_id = str(problem["problem_id"])
    source_payload = read_json(problem["source_path"])
    rules_summary = _load_rule_summaries() if condition == "no_tuple" else None
    source_schema_path = result_dir / "source_schema_for_eval.json"
    revision_context: dict[str, Any] | None = None
    revision_history: list[dict[str, Any]] = []
    round_records: list[dict[str, Any]] = []
    final_record: dict[str, Any] | None = None
    final_generated_status = ""
    stop_reason = "reached_requested_rounds"

    for round_index in range(1, condition_quality_iterations(condition) + 1):
        system_prompt, user_prompt = build_custom_generation_prompts(
            condition=condition,
            source_payload=source_payload,
            rules_summary=rules_summary,
            revision_context=revision_context,
        )
        payload = client.chat_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.2,
            request_label=f"quality_ablation_{condition}_round{round_index}",
        )
        artifact, eval_source_schema = _normalize_custom_payload(
            condition=condition,
            problem_id=problem_id,
            source_payload=source_payload,
            payload=payload,
            client=client,
        )
        write_json(source_schema_path, eval_source_schema)
        generated = _generated_problem_from_payload(artifact["generated_problem"])
        plan = _plan_from_artifact(artifact, source_payload=source_payload, condition=condition)
        artifact_path = result_dir / "artifacts" / f"{problem_id}_{condition}_round{round_index}.json"
        markdown_path = result_dir / "output" / f"{problem_id}_{condition}_round{round_index}.md"
        write_json(artifact_path, artifact)
        write_text(markdown_path, render_problem_markdown(generated, plan))

        final_generated_status = generated.status
        round_record = {
            "round_index": round_index,
            "artifact_path": str(artifact_path),
            "markdown_path": str(markdown_path),
            "generated_status": final_generated_status,
            "quality_report_json_path": "",
            "quality_report_md_path": "",
            "overall_status": "not_evaluated",
            "quality_score": 0.0,
            "divergence_score": 0.0,
        }
        if final_generated_status in DECLARED_FAILURE_STATUSES:
            round_records.append(round_record)
            final_record = round_record
            stop_reason = final_generated_status
            break

        evaluator = ProblemEvaluator(judge_client=client)
        quality_report = evaluator.evaluate_problem(
            schema_path=source_schema_path,
            artifact_path=artifact_path,
            original_problem_override=source_payload.get("original_problem", {}),
            markdown_path=markdown_path,
            round_index=round_index,
        )
        quality_json_path = result_dir / "reports" / f"{problem_id}_{condition}_round{round_index}_quality_report.json"
        quality_md_path = result_dir / "reports" / f"{problem_id}_{condition}_round{round_index}_quality_report.md"
        write_json(quality_json_path, quality_report)
        write_text(quality_md_path, render_quality_report_markdown(quality_report))
        overall = quality_report.get("overall", {})
        round_record.update(
            {
                "quality_report_json_path": str(quality_json_path),
                "quality_report_md_path": str(quality_md_path),
                "overall_status": str(overall.get("status", "")),
                "quality_score": float(overall.get("quality_score", 0.0) or 0.0),
                "divergence_score": float(overall.get("divergence_score", 0.0) or 0.0),
            }
        )
        round_records.append(round_record)
        final_record = round_record
        revision_brief = quality_report.get("revision_brief", {})
        revision_history.append(revision_brief)
        revision_context = {
            "latest_revision_brief": revision_brief,
            "revision_history": revision_history,
        }
        if overall.get("status") == "pass":
            stop_reason = "pass"
            break

    if final_record is None:
        raise RuntimeError(f"{condition} 未产出任何生成轮次：{problem_id}")

    iteration_summary_path = result_dir / "artifacts" / f"{problem_id}_{condition}_iteration_summary.json"
    write_json(
        iteration_summary_path,
        {
            "run_id": f"{problem_id}_{condition}",
            "requested_rounds": condition_quality_iterations(condition),
            "final_round_index": final_record["round_index"],
            "stop_reason": stop_reason,
            "rounds": round_records,
        },
    )
    status = "declared_failure" if final_generated_status in DECLARED_FAILURE_STATUSES else "completed"
    return {
        "schema_version": 1,
        "problem_id": problem_id,
        "condition": condition,
        "status": status,
        "generated_status": final_generated_status,
        "is_declared_failure": status == "declared_failure",
        "artifact_path": final_record["artifact_path"],
        "markdown_path": final_record["markdown_path"],
        "quality_report_json_path": final_record["quality_report_json_path"],
        "quality_report_md_path": final_record["quality_report_md_path"],
        "iteration_summary_path": str(iteration_summary_path),
        "final_round_index": final_record["round_index"],
        "source_schema_for_eval_path": str(source_schema_path),
        "full_reused": False,
    }


def _run_no_quality_loop(
    *,
    problem: dict[str, Any],
    result_dir: Path,
    client: Any,
    progress_writer: Callable[[str], None] | None,
) -> dict[str, Any]:
    problem_id = str(problem["problem_id"])
    source_dir = result_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    source_payload = read_json(problem["source_path"])
    write_json(source_dir / f"{problem_id}.json", source_payload)

    random.seed(int(sha256_text(f"{problem_id}:no_quality_loop")[:8], 16))
    pipeline = GenerationPipeline(
        source_dir=source_dir,
        output_dir=result_dir / "output",
        artifact_dir=result_dir / "artifacts",
        report_dir=result_dir / "reports",
        generator=ProblemGenerator(client=client, temperature=0.2),
        planner=VariantPlanner(client=client, rulebook=RuleBook.load(Path(GENERATION_DIR) / "planning_rules.json")),
        quality_evaluator=ProblemEvaluator(judge_client=client),
        progress_writer=progress_writer or (lambda _message: None),
    )
    records = pipeline.run(
        mode="single",
        problem_ids=[problem_id],
        quality_iterations=0,
    )
    if not records:
        raise RuntimeError(f"no_quality_loop 未产出记录：{problem_id}")
    record = records[0]
    generated_status = str(record.get("generated_status", ""))
    status = "declared_failure" if generated_status in DECLARED_FAILURE_STATUSES else "completed"
    return {
        "schema_version": 1,
        "problem_id": problem_id,
        "condition": "no_quality_loop",
        "status": status,
        "generated_status": generated_status,
        "is_declared_failure": status == "declared_failure",
        "artifact_path": str(record.get("artifact_path", "")),
        "markdown_path": str(record.get("markdown_path", "")),
        "quality_report_json_path": "",
        "quality_report_md_path": "",
        "iteration_summary_path": "",
        "final_round_index": 1,
        "full_reused": False,
    }


def _materialize_full_result(*, problem: dict[str, Any], result_dir: Path) -> dict[str, Any]:
    problem_id = str(problem["problem_id"])
    full = problem.get("full", {})
    markdown_path = str(full.get("markdown_path", ""))
    artifact_path = str(full.get("artifact_path", ""))
    if not markdown_path or not artifact_path:
        raise RuntimeError(f"full 组缺少最终产物路径：{problem_id}")
    return {
        "schema_version": 1,
        "problem_id": problem_id,
        "condition": "full",
        "status": "completed",
        "generated_status": str(full.get("generated_status", "ok") or "ok"),
        "is_declared_failure": False,
        "artifact_path": artifact_path,
        "markdown_path": markdown_path,
        "quality_report_json_path": str(full.get("quality_report_json_path", "")),
        "quality_report_md_path": "",
        "iteration_summary_path": str(full.get("iteration_summary_path", "")),
        "final_round_index": full.get("final_round_index"),
        "full_reused": True,
        "full_source_dir": str(full.get("full_source_dir", "")),
        "result_path": str(result_dir / "result.json"),
    }


def _normalize_custom_payload(
    *,
    condition: str,
    problem_id: str,
    source_payload: dict[str, Any],
    payload: dict[str, Any],
    client: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    status = str(payload.get("status", "ok") or "ok").strip()
    raw_generated = payload.get("generated_problem")
    if not isinstance(raw_generated, dict):
        raw_generated = {}
    generated = _normalize_generated_problem(raw_generated, status=status, fallback_error=str(payload.get("error_reason", "")))
    seed_schema = payload.get("seed_schema_estimate") if condition == "no_tuple" else _schema_only(source_payload)
    if not isinstance(seed_schema, dict) or not seed_schema:
        seed_schema = _minimal_schema(problem_id=problem_id, source=str(source_payload.get("source", "")))
    new_schema = payload.get("new_schema")
    if not isinstance(new_schema, dict) or status != "ok":
        new_schema = _minimal_schema(problem_id=f"{problem_id}_{condition}", source=str(source_payload.get("source", "")))

    if status == "ok":
        distance = compute_schema_distance(seed_schema, new_schema, embedding_client=client)
        changed_axes = compute_changed_axes(seed_schema, new_schema, embedding_client=client, distance=distance)
    else:
        distance = _zero_distance()
        changed_axes = []

    difference_plan = payload.get("difference_plan")
    if not isinstance(difference_plan, dict):
        difference_plan = {}
    artifact = {
        "problem_id": str(new_schema.get("problem_id") or f"{problem_id}_{condition}"),
        "source_problem_ids": [problem_id],
        "variant_index": 1,
        "theme_random_value": 0,
        "mode": f"quality_ablation_{condition}",
        "rule_version": "disabled" if condition == "no_rules" else "summary_only",
        "theme": _theme_payload(_theme_for(problem_id, condition, 1)),
        "difference_plan": {
            "target_distance_band": {"min": 0.35, "max": 0.60},
            "changed_axes": [str(item) for item in difference_plan.get("changed_axes", changed_axes)],
            "same_family_allowed": True,
            "forbidden_reuse": [],
            "rationale": str(difference_plan.get("rationale", "")),
            "summary": str(difference_plan.get("summary", "")),
            "mode": f"quality_ablation_{condition}",
        },
        "predicted_schema_distance": distance["total"],
        "distance_breakdown": distance,
        "changed_axes_realized": changed_axes,
        "objective": new_schema.get("objective", {}),
        "rule_selection_reason": "规则库禁用，使用通用规划。" if condition == "no_rules" else "外部四元组禁用，基于原题文本和规则摘要规划。",
        "new_schema": new_schema,
        "new_schema_snapshot": new_schema,
        "applied_rule": str(payload.get("applied_rule", "generic_planning" if condition == "no_rules" else "")),
        "rejected_candidates": [],
        "algorithmic_delta_claim": _normalize_algorithmic_delta(payload.get("algorithmic_delta_claim", {})),
        "anti_shallow_rationale": str(payload.get("anti_shallow_rationale", "")),
        "shared_core_summary": "",
        "shared_core_anchors": {},
        "seed_contributions": {},
        "fusion_ablation": {},
        "applied_helpers": [],
        "planning_status": status,
        "planning_error_reason": str(payload.get("error_reason", "")),
        "planning_feedback": str(payload.get("feedback", "")),
        "selection_trace": [],
        "validation_trace": [],
        "candidate_attempts": [],
        "ablation_condition": condition,
        "generated_problem": generated,
    }
    return artifact, seed_schema


def _generated_problem_from_payload(payload: dict[str, Any]) -> GeneratedProblem:
    return GeneratedProblem(
        title=str(payload.get("title", "")),
        description=str(payload.get("description", "")),
        input_format=str(payload.get("input_format", "")),
        output_format=str(payload.get("output_format", "")),
        constraints=[str(item) for item in payload.get("constraints", []) if str(item).strip()],
        samples=[
            {
                "input": str(item.get("input", "")),
                "output": str(item.get("output", "")),
                "explanation": str(item.get("explanation", "")),
            }
            for item in payload.get("samples", [])
            if isinstance(item, dict)
        ],
        notes=str(payload.get("notes", "")),
        status=str(payload.get("status", "ok")),
        error_reason=str(payload.get("error_reason", "")),
        feedback=str(payload.get("feedback", "")),
    )


def _plan_from_artifact(artifact: dict[str, Any], *, source_payload: dict[str, Any], condition: str) -> VariantPlan:
    theme = _theme_for(str(source_payload.get("problem_id", "")), condition, 1)
    new_schema = artifact.get("new_schema") or artifact.get("new_schema_snapshot") or {}
    return VariantPlan(
        problem_id=str(artifact.get("problem_id", "")),
        variant_index=1,
        theme_random_value=0,
        mode=str(artifact.get("mode", "")),
        theme=theme,
        source_problem_ids=[str(source_payload.get("problem_id", ""))],
        objective=dict(new_schema.get("objective", {})),
        difficulty=str(new_schema.get("difficulty", "")),
        rule_selection_reason=str(artifact.get("rule_selection_reason", "")),
        input_summary=str(new_schema.get("input_structure", {}).get("type", "")),
        constraint_summary=[
            str(item.get("description", ""))
            for item in new_schema.get("core_constraints", {}).get("constraints", [])
            if isinstance(item, dict)
        ],
        invariant_summary=[
            str(item.get("description", ""))
            for item in new_schema.get("invariant", {}).get("invariants", [])
            if isinstance(item, dict)
        ],
        difference_plan=DifferencePlan(**artifact["difference_plan"]),
        new_schema_snapshot=NewSchema(**_new_schema_contract(new_schema)),
        predicted_schema_distance=float(artifact.get("predicted_schema_distance", 0.0)),
        distance_breakdown=dict(artifact.get("distance_breakdown", {})),
        changed_axes_realized=list(artifact.get("changed_axes_realized", [])),
        applied_rule=str(artifact.get("applied_rule", "")),
        algorithmic_delta_claim=dict(artifact.get("algorithmic_delta_claim", {})),
        anti_shallow_rationale=str(artifact.get("anti_shallow_rationale", "")),
        rule_version=str(artifact.get("rule_version", "")),
    )


def _normalize_generated_problem(raw: dict[str, Any], *, status: str, fallback_error: str) -> dict[str, Any]:
    if status != "ok":
        return {
            "status": status,
            "error_reason": fallback_error,
            "feedback": str(raw.get("feedback", "")),
            "title": "",
            "description": "",
            "input_format": "",
            "output_format": "",
            "constraints": [],
            "samples": [],
            "notes": "",
        }
    samples = raw.get("samples", [])
    if not isinstance(samples, list):
        samples = []
    constraints = raw.get("constraints", [])
    if not isinstance(constraints, list):
        constraints = []
    return {
        "status": "ok",
        "error_reason": "",
        "feedback": "",
        "title": str(raw.get("title", "")),
        "description": str(raw.get("description", "")),
        "input_format": str(raw.get("input_format", "")),
        "output_format": str(raw.get("output_format", "")),
        "constraints": [str(item) for item in constraints],
        "samples": [
            {
                "input": str(item.get("input", "")),
                "output": str(item.get("output", "")),
                "explanation": str(item.get("explanation", "")),
            }
            for item in samples
            if isinstance(item, dict)
        ],
        "notes": str(raw.get("notes", "")),
    }


def _load_qwen_client(workflow_config_path: Path) -> QwenClient:
    config = WorkflowConfig.from_file(workflow_config_path)
    return QwenClient(generation_config=config.generation_llm, embedding_config=config.embedding_llm)


def _load_rule_summaries() -> list[dict[str, Any]]:
    rule_path = Path(GENERATION_DIR) / "planning_rules.json"
    payload = read_json(rule_path)
    rules = payload.get("modes", {}).get("single_seed_extension", {}).get("rules", [])
    summaries: list[dict[str, Any]] = []
    for rule in rules:
        if not isinstance(rule, dict) or not rule.get("enabled", False):
            continue
        summaries.append(
            {
                "id": str(rule.get("id", "")),
                "family": str(rule.get("family", "")),
                "summary": str(rule.get("summary", "")),
                "required_axis_changes": rule.get("required_axis_changes", {}),
                "helpers": [
                    {
                        "id": str(helper.get("id", "")),
                        "summary": str(helper.get("summary", "")),
                        "target_axes": helper.get("target_axes", []),
                    }
                    for helper in rule.get("helpers", [])
                    if isinstance(helper, dict)
                ],
            }
        )
    return summaries


def _schema_only(source_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "problem_id": source_payload.get("problem_id", ""),
        "source": source_payload.get("source", ""),
        "input_structure": source_payload.get("input_structure", {}),
        "core_constraints": source_payload.get("core_constraints", {}),
        "objective": source_payload.get("objective", {}),
        "invariant": source_payload.get("invariant", {}),
    }


def _seed_metadata(source_payload: dict[str, Any]) -> dict[str, Any]:
    original = source_payload.get("original_problem", {})
    return {
        "problem_id": source_payload.get("problem_id", ""),
        "source": source_payload.get("source", ""),
        "title": original.get("title", "") if isinstance(original, dict) else "",
    }


def _custom_output_contract(*, require_seed_schema_estimate: bool) -> dict[str, Any]:
    contract = {
        "status": "ok|schema_insufficient|difference_insufficient",
        "error_reason": "string",
        "feedback": "string",
        "new_schema": {
            "problem_id": "string",
            "source": "string",
            "input_structure": "object",
            "core_constraints": {"constraints": "array"},
            "objective": "object",
            "invariant": {"invariants": "array"},
            "difficulty": "Easy|Medium|Hard",
        },
        "difference_plan": {"changed_axes": "array", "rationale": "string", "summary": "string"},
        "algorithmic_delta_claim": {
            "seed_solver_core": "string",
            "reusable_subroutines": "string",
            "new_solver_core": "string",
            "new_proof_obligation": "string",
            "why_direct_reuse_fails": "string",
        },
        "anti_shallow_rationale": "string",
        "generated_problem": {
            "status": "ok",
            "title": "string",
            "description": "string",
            "input_format": "string",
            "output_format": "string",
            "constraints": "string[]",
            "samples": [{"input": "string", "output": "string", "explanation": "string"}],
            "notes": "string",
        },
    }
    if require_seed_schema_estimate:
        contract["seed_schema_estimate"] = {
            "problem_id": "string",
            "source": "string",
            "input_structure": "object",
            "core_constraints": {"constraints": "array"},
            "objective": "object",
            "invariant": {"invariants": "array"},
        }
    return contract


def _minimal_schema(*, problem_id: str, source: str) -> dict[str, Any]:
    return {
        "problem_id": problem_id,
        "source": source,
        "input_structure": {},
        "core_constraints": {"constraints": []},
        "objective": {},
        "invariant": {"invariants": []},
        "difficulty": "",
    }


def _new_schema_contract(schema: dict[str, Any]) -> dict[str, Any]:
    normalized = _minimal_schema(
        problem_id=str(schema.get("problem_id", "")),
        source=str(schema.get("source", "")),
    )
    for field in TUPLE_FIELDS:
        if isinstance(schema.get(field), dict):
            normalized[field] = schema[field]
    normalized["theme"] = schema.get("theme", {})
    normalized["difficulty"] = str(schema.get("difficulty", ""))
    return normalized


def _normalize_algorithmic_delta(value: Any) -> dict[str, str]:
    data = value if isinstance(value, dict) else {}
    return {
        "seed_solver_core": str(data.get("seed_solver_core", "")),
        "reusable_subroutines": str(data.get("reusable_subroutines", "")),
        "new_solver_core": str(data.get("new_solver_core", "")),
        "new_proof_obligation": str(data.get("new_proof_obligation", "")),
        "why_direct_reuse_fails": str(data.get("why_direct_reuse_fails", "")),
    }


def _zero_distance() -> dict[str, Any]:
    return {
        "distance_version": "v2",
        "backend": "not_evaluated",
        "total": 0.0,
        "axis_scores": {"I": 0.0, "C": 0.0, "O": 0.0, "V": 0.0},
        "components": {
            "input_tree_distance": 0.0,
            "constraint_match_distance": 0.0,
            "objective_type_distance": 0.0,
            "objective_text_distance": 0.0,
            "invariant_match_distance": 0.0,
        },
    }


def _theme_for(problem_id: str, condition: str, round_index: int) -> Theme:
    if not THEMES:
        return Theme("campus_ops", "校园运营", "日常、清晰", ["任务"], "映射成日常任务。")
    index = int(sha256_text(f"{problem_id}:{condition}:{round_index}")[:8], 16) % len(THEMES)
    return THEMES[index]


def _theme_payload(theme: Theme) -> dict[str, Any]:
    return {
        "id": theme.theme_id,
        "name": theme.name,
        "tone": theme.tone,
        "keywords": list(theme.keywords),
        "mapping_hint": theme.mapping_hint,
    }
