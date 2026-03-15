from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from markdown_renderer import render_problem_markdown
from models import VariantPlan
from problem_generator import ProblemGenerator
from schema_loader import SchemaLoader
from variant_planner import VariantPlanner


class GenerationPipeline:
    def __init__(
        self,
        source_dir: Path,
        output_dir: Path,
        artifact_dir: Path,
        generator: ProblemGenerator,
        planner: VariantPlanner,
    ):
        self.loader = SchemaLoader(source_dir)
        self.output_dir = output_dir
        self.artifact_dir = artifact_dir
        self.generator = generator
        self.planner = planner
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        problem_ids: list[str],
        variants: int = 1,
        theme_id: str | None = None,
        dry_run: bool = False,
    ) -> list[dict[str, Any]]:
        if not problem_ids:
            problem_ids = self.loader.list_problem_ids()

        records: list[dict[str, Any]] = []
        for problem_id in problem_ids:
            schema = self.loader.load(problem_id)
            for variant_index in range(1, variants + 1):
                plan = self.planner.build_plan(
                    schema=schema, variant_index=variant_index, theme_id=theme_id
                )
                generated = self.generator.generate(schema, plan, dry_run=dry_run)
                markdown = render_problem_markdown(generated, plan)
                record = self._save_outputs(problem_id, plan, generated.__dict__, markdown)
                records.append(record)
        return records

    def _save_outputs(
        self,
        problem_id: str,
        plan: VariantPlan,
        payload: dict[str, Any],
        markdown: str,
    ) -> dict[str, Any]:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = f"{problem_id}_v{plan.variant_index}_{plan.theme.theme_id}_{timestamp}"

        json_path = self.artifact_dir / f"{stem}.json"
        md_path = self.output_dir / f"{stem}.md"

        artifact = {
            "problem_id": problem_id,
            "variant_index": plan.variant_index,
            "seed": plan.seed,
            "theme": {
                "id": plan.theme.theme_id,
                "name": plan.theme.name,
            },
            "objective": plan.objective,
            "numerical_parameters": plan.numerical_parameters,
            "structural_options": plan.structural_options,
            "generated_problem": payload,
        }

        with json_path.open("w", encoding="utf-8") as handle:
            json.dump(artifact, handle, ensure_ascii=False, indent=2)

        with md_path.open("w", encoding="utf-8") as handle:
            handle.write(markdown)

        return {
            "problem_id": problem_id,
            "variant_index": plan.variant_index,
            "markdown_path": str(md_path),
            "artifact_path": str(json_path),
        }

