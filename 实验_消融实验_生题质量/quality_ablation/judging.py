from __future__ import annotations

import json
import random
import traceback
from pathlib import Path
from typing import Any, Callable

from .generation import DECLARED_FAILURE_STATUSES
from .manifest import load_manifest
from .utils import (
    ALL_CONDITIONS,
    DEFAULT_WORKFLOW_CONFIG,
    average,
    append_jsonl,
    limited_rows,
    read_json,
    read_text,
    safe_name,
    shard_file_suffix,
    sharded_rows,
    stable_hash,
    utc_now_iso,
    write_jsonl,
)

from qwen_client import QwenClient
from orchestrator import WorkflowConfig


JUDGE_METRICS = ("solvability", "clarity", "novelty", "difficulty")
REASON_FIELDS = (
    "solvability_reasoning",
    "clarity_reasoning",
    "novelty_reasoning",
    "difficulty_reasoning",
    "overall_comment",
)


def run_judging(
    *,
    manifest_path: Path,
    run_dir: Path,
    workflow_config_path: Path = DEFAULT_WORKFLOW_CONFIG,
    conditions: list[str] | None = None,
    limit: int | None = None,
    resume: bool = True,
    blind_seed: int = 20260624,
    shard_count: int = 1,
    shard_index: int = 0,
    progress_writer: Callable[[str], None] | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    progress = progress_writer or (lambda message: print(message, flush=True))
    selected_conditions = conditions or list(ALL_CONDITIONS)
    for condition in selected_conditions:
        if condition not in ALL_CONDITIONS:
            raise ValueError(f"未知实验组：{condition}")

    manifest = load_manifest(manifest_path)
    limited_problems = limited_rows(list(manifest["problems"]), limit)
    problems = sharded_rows(limited_problems, shard_count=shard_count, shard_index=shard_index)
    file_suffix = shard_file_suffix(shard_count=shard_count, shard_index=shard_index)
    judging_dir = run_dir.resolve() / "judging"
    judging_dir.mkdir(parents=True, exist_ok=True)

    items = build_blind_items(
        manifest=manifest,
        run_dir=run_dir.resolve(),
        conditions=selected_conditions,
        problems=problems,
        blind_seed=blind_seed,
    )
    blind_items_path = judging_dir / f"blind_items{file_suffix}.jsonl"
    write_jsonl(blind_items_path, items)

    scores_path = run_dir.resolve() / f"scores{file_suffix}.jsonl"
    existing_ids = _load_existing_score_ids(scores_path) if resume else set()
    active_client = client or _load_qwen_client(workflow_config_path)

    scored_count = 0
    skipped_count = 0
    for index, item in enumerate(items, start=1):
        blind_id = str(item["blind_id"])
        if blind_id in existing_ids:
            skipped_count += 1
            continue

        progress(f"[judge {index}/{len(items)}] {blind_id}")
        score = judge_one_item(item=item, client=active_client)
        append_jsonl(scores_path, score)
        scored_count += 1

    summary = {
        "schema_version": 1,
        "run_dir": str(run_dir.resolve()),
        "manifest_path": str(manifest_path.resolve()),
        "conditions": selected_conditions,
        "problem_count": len(problems),
        "limited_problem_count": len(limited_problems),
        "shard_count": shard_count,
        "shard_index": shard_index,
        "blind_item_count": len(items),
        "scored_count": scored_count,
        "skipped_count": skipped_count,
        "scores_path": str(scores_path),
        "blind_items_path": str(blind_items_path),
        "finished_at": utc_now_iso(),
    }
    write_jsonl(judging_dir / f"judge_summary{file_suffix}.jsonl", [summary])
    return summary


def build_blind_items(
    *,
    manifest: dict[str, Any],
    run_dir: Path,
    conditions: list[str],
    problems: list[dict[str, Any]],
    blind_seed: int,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for problem in problems:
        problem_id = str(problem["problem_id"])
        seed_json = _seed_for_judge(problem)
        for condition in conditions:
            generation = _generation_for_judge(problem=problem, run_dir=run_dir, condition=condition)
            blind_id = stable_hash(f"{problem_id}:{condition}:{blind_seed}")
            item = {
                "schema_version": 1,
                "blind_id": blind_id,
                "problem_id": problem_id,
                "condition": condition,
                "seed_hash": problem.get("seed_hash", ""),
                "judge_payload": {
                    "seed_json": seed_json,
                    "new_problem_section": generation["new_problem_section"],
                },
                "generation_status": generation["generation_status"],
                "declared_failure_status": generation["declared_failure_status"],
                "missing_reason": generation["missing_reason"],
            }
            items.append(item)

    rng = random.Random(blind_seed)
    rng.shuffle(items)
    return items


def judge_one_item(*, item: dict[str, Any], client: Any) -> dict[str, Any]:
    base = {
        "schema_version": 1,
        "blind_id": item["blind_id"],
        "problem_id": item["problem_id"],
        "condition": item["condition"],
        "generation_status": item.get("generation_status", ""),
        "declared_failure_status": item.get("declared_failure_status", ""),
        "missing_reason": item.get("missing_reason", ""),
        "judged_at": utc_now_iso(),
    }

    declared_status = str(item.get("declared_failure_status") or "")
    if declared_status in DECLARED_FAILURE_STATUSES:
        return {
            **base,
            "judge_status": "declared_failure_zero",
            **{metric: 0.0 for metric in JUDGE_METRICS},
            "overall_score": 0.0,
            "solvability_reasoning": f"生成阶段声明失败：{declared_status}",
            "clarity_reasoning": f"生成阶段声明失败：{declared_status}",
            "novelty_reasoning": f"生成阶段声明失败：{declared_status}",
            "difficulty_reasoning": f"生成阶段声明失败：{declared_status}",
            "overall_comment": f"声明性失败按实验方案记 0 分：{declared_status}",
        }

    if item.get("missing_reason"):
        return {
            **base,
            "judge_status": "missing",
            **{metric: None for metric in JUDGE_METRICS},
            "overall_score": None,
            "solvability_reasoning": "",
            "clarity_reasoning": "",
            "novelty_reasoning": "",
            "difficulty_reasoning": "",
            "overall_comment": str(item["missing_reason"]),
        }

    try:
        prompt = build_judge_prompt(
            seed_json=item["judge_payload"]["seed_json"],
            new_problem_section=item["judge_payload"]["new_problem_section"],
        )
        response = client.chat_json(
            system_prompt="你是一名算法竞赛题目质量评审专家。只返回严格 JSON，不要输出任何额外文本。",
            user_prompt=prompt,
            temperature=0.0,
            request_label="quality_ablation_judge",
        )
        normalized = normalize_judge_response(response)
        return {
            **base,
            "judge_status": "completed",
            **normalized,
        }
    except Exception as exc:  # noqa: BLE001 - 单条 judge 失败应记录为 missing。
        return {
            **base,
            "judge_status": "judge_failed",
            **{metric: None for metric in JUDGE_METRICS},
            "overall_score": None,
            "solvability_reasoning": "",
            "clarity_reasoning": "",
            "novelty_reasoning": "",
            "difficulty_reasoning": "",
            "overall_comment": str(exc),
            "error_type": type(exc).__name__,
            "traceback": traceback.format_exc(),
        }


def build_judge_prompt(*, seed_json: dict[str, Any], new_problem_section: str) -> str:
    return f"""你是一名算法竞赛题目质量评审专家。你的任务是将新生成的算法题与种子题（原题）进行对比，评估新题的整体质量。

种子题目（原题）：
{json.dumps(seed_json, ensure_ascii=False, indent=2)}

{new_problem_section}

请从以下 4 个维度评价新题：

1. **可解性（solvability）** - 0 到 100 分
   - 题目是否存在有效解法？
   - 题面逻辑是否自洽？
   - 约束和要求是否可以实现？
   - 样例是否与题目描述一致？
   - 是否存在导致题目不可解的矛盾或歧义？

2. **清晰度（clarity）** - 0 到 100 分
   - 题目描述是否清楚、易懂？
   - 输入和输出格式是否定义完整？
   - 约束条件是否明确给出？
   - 样例是否有帮助，且解释是否恰当？
   - 语言是否精确、无歧义？
   - 普通算法竞赛选手是否能理解需要完成什么？

3. **新颖度（novelty）** - 0 到 100 分
   - 新题与种子题之间的差异有多大？
   - 核心算法思路是否发生了显著变化？
   - 是否存在超出变量改名的实质性改动？
   - 题目是否引入了新的概念、约束或转折？
   - 这是有意义的转化，还是只有表面包装变化？
   - 注意：如果只是改变量名或替换相似主题，新颖度应给低分。

4. **难度（difficulty）** - 0 到 100 分
   - 难度是否适合目标受众？
   - 实际难度是否符合题目声明的难度等级（Easy/Medium/Hard）？
   - 题目是否具有足够挑战性，但又不至于无法完成？
   - 约束是否适合预期解法复杂度？
   - 题目复杂度与时间限制之间是否平衡？

评分参考：
- 90-100：优秀，各项标准都满足得很好。
- 75-89：良好，大多数标准满足，仅有轻微问题。
- 60-74：可接受，满足基本标准，但存在明显缺陷。
- 40-59：较差，存在影响质量的重要问题。
- 0-39：不可接受，存在使题目难以使用的严重缺陷。

关键要求：
1. 新颖度：如果新题与种子题本质相同，只做了变量名、主题等表面修改，应给低分（低于 40）。只有存在实质性的算法或结构差异，才应给高新颖度。
2. 可解性：如果题目不可解、互相矛盾或样例错误，应给低于 40 的分数。
3. 清晰度：如果题面混乱、有歧义或缺少关键信息，应给低于 60 的分数。
4. 难度：同时考虑实际复杂度和题目声明的难度等级。

只返回一个合法 JSON object，且必须严格使用以下结构：
{{
  "solvability": <0 到 100 的数字>,
  "clarity": <0 到 100 的数字>,
  "novelty": <0 到 100 的数字>,
  "difficulty": <0 到 100 的数字>,
  "solvability_reasoning": "<可解性评分的详细理由>",
  "clarity_reasoning": "<清晰度评分的详细理由>",
  "novelty_reasoning": "<新颖度评分的详细理由>",
  "difficulty_reasoning": "<难度评分的详细理由>",
  "overall_comment": "<整体质量、主要优点和主要问题的总结>"
}}

不要输出任何其他文本、解释或 Markdown 格式。
"""


def normalize_judge_response(response: Any) -> dict[str, Any]:
    if not isinstance(response, dict):
        raise ValueError("judge 响应不是 JSON object")

    normalized: dict[str, Any] = {}
    values: list[float] = []
    for metric in JUDGE_METRICS:
        raw_value = response.get(metric)
        if not isinstance(raw_value, (int, float)):
            raise ValueError(f"judge 缺少数值字段：{metric}")
        value = max(0.0, min(100.0, float(raw_value)))
        normalized[metric] = value
        values.append(value)

    normalized["overall_score"] = average(values)
    for field in REASON_FIELDS:
        normalized[field] = str(response.get(field, ""))
    return normalized


def _generation_for_judge(*, problem: dict[str, Any], run_dir: Path, condition: str) -> dict[str, str]:
    if condition == "full":
        markdown_path = Path(problem["full"]["markdown_path"])
        if not markdown_path.is_file():
            return _missing_generation("full_markdown_missing")
        return {
            "new_problem_section": _sanitize_problem_markdown(read_text(markdown_path)),
            "generation_status": "completed",
            "declared_failure_status": "",
            "missing_reason": "",
        }

    result_path = run_dir / "generations" / condition / safe_name(str(problem["problem_id"])) / "result.json"
    if not result_path.is_file():
        return _missing_generation("generation_result_missing")

    result = read_json(result_path)
    declared_status = str(result.get("generated_status") or "")
    if result.get("status") == "declared_failure" or declared_status in DECLARED_FAILURE_STATUSES:
        return {
            "new_problem_section": "",
            "generation_status": str(result.get("status", "")),
            "declared_failure_status": declared_status or "declared_failure",
            "missing_reason": "",
        }
    if result.get("status") != "completed":
        return _missing_generation(str(result.get("status") or "generation_failed"))

    markdown_path = Path(str(result.get("markdown_path", "")))
    if not markdown_path.is_file():
        return _missing_generation("markdown_missing")
    return {
        "new_problem_section": _sanitize_problem_markdown(read_text(markdown_path)),
        "generation_status": "completed",
        "declared_failure_status": "",
        "missing_reason": "",
    }


def _seed_for_judge(problem: dict[str, Any]) -> dict[str, Any]:
    source_payload = read_json(Path(problem["source_path"]))
    original_problem = source_payload.get("original_problem", {})
    return {
        "problem_id": source_payload.get("problem_id", problem.get("problem_id")),
        "source": source_payload.get("source", problem.get("source", "")),
        "original_problem": original_problem,
    }


def _sanitize_problem_markdown(markdown: str) -> str:
    # 渲染器会写入“生成任务”等内部元信息；盲评 prompt 不应携带这些上下文。
    sanitized_lines = [
        line
        for line in markdown.splitlines()
        if not line.strip().startswith("> 生成任务：")
    ]
    return "\n".join(sanitized_lines).strip() + "\n"


def _missing_generation(reason: str) -> dict[str, str]:
    return {
        "new_problem_section": "",
        "generation_status": "missing",
        "declared_failure_status": "",
        "missing_reason": reason,
    }


def _load_existing_score_ids(scores_path: Path) -> set[str]:
    if not scores_path.is_file():
        return set()
    ids: set[str] = set()
    with scores_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            ids.add(str(item.get("blind_id", "")))
    return ids


def _load_qwen_client(workflow_config_path: Path) -> QwenClient:
    config = WorkflowConfig.from_file(workflow_config_path)
    return QwenClient(generation_config=config.generation_llm, embedding_config=config.embedding_llm)
