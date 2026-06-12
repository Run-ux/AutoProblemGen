from __future__ import annotations

import copy
import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from extract import (
    RateLimiter,
    extract_all_problems,
    extract_single_dimension,
    normalize_input_structure_result,
    validate_input_structure_result,
)
from qwen_client import QwenJSONError, _extract_chat_content


class FakeClient:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def chat_json(self, system_prompt, user_prompt, temperature=0.4, **_):
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "temperature": temperature,
            }
        )
        if isinstance(self.result, list):
            index = min(len(self.calls) - 1, len(self.result) - 1)
            return copy.deepcopy(self.result[index])
        return copy.deepcopy(self.result)


class InputStructureValidationTests(unittest.TestCase):
    def test_validate_composite_requires_role_description(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            r"components\[0\]\.role_description 必须是非空字符串",
        ):
            validate_input_structure_result(
                {
                    "type": "composite",
                    "length": {"min": None, "max": None},
                    "value_range": {"min": None, "max": None},
                    "properties": {},
                    "components": [
                        {
                            "role": "queries",
                            "type": "array",
                            "length": {"min": 1, "max": 5},
                            "value_range": {"min": 0, "max": 20},
                            "properties": {},
                        }
                    ],
                }
            )

    def test_validate_composite_accepts_role_description(self) -> None:
        validate_input_structure_result(
            {
                "type": "composite",
                "length": {"min": None, "max": None},
                "value_range": {"min": None, "max": None},
                "properties": {},
                "components": [
                    {
                        "role": "queries",
                        "role_description": "online query stream",
                        "type": "array",
                        "length": {"min": 1, "max": 5},
                        "value_range": {"min": 0, "max": 20},
                        "properties": {"online_queries": True},
                    }
                ],
            }
        )

    def test_validate_non_composite_keeps_existing_behavior(self) -> None:
        validate_input_structure_result(
            {
                "type": "array",
                "length": {"min": 1, "max": 5},
                "value_range": {"min": 0, "max": 20},
                "properties": {},
            }
        )

    def test_normalize_input_structure_fills_unknown_component_ranges(self) -> None:
        normalized = normalize_input_structure_result(
            {
                "type": "composite",
                "length": None,
                "value_range": {"min": None},
                "properties": {},
                "components": [
                    {
                        "role": "queries",
                        "role_description": "online query stream",
                        "type": "array",
                        "length": None,
                        "properties": {},
                    }
                ],
            }
        )

        self.assertEqual(normalized["length"], {"min": None, "max": None})
        self.assertEqual(normalized["value_range"], {"min": None, "max": None})
        self.assertEqual(
            normalized["components"][0]["length"],
            {"min": None, "max": None},
        )
        self.assertEqual(
            normalized["components"][0]["value_range"],
            {"min": None, "max": None},
        )
        validate_input_structure_result(normalized)

    def test_extract_single_dimension_normalizes_range_shape_without_repair(self) -> None:
        client = FakeClient(
            {
                "type": "composite",
                "length": {"min": None, "max": None},
                "value_range": {"min": None, "max": None},
                "properties": {},
                "components": [
                    {
                        "role": "queries",
                        "role_description": "online query stream",
                        "type": "array",
                        "length": None,
                        "value_range": None,
                        "properties": {},
                    }
                ],
            }
        )

        result = extract_single_dimension(
            client=client,
            problem={
                "problem_id": "demo",
                "source": {"source_name": "cf"},
                "title": "",
                "description": "",
            },
            dimension_name="input_structure",
            rate_limiter=RateLimiter(min_interval=0.0),
            logger=logging.getLogger("extract-test"),
            temperature=0.0,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(
            result["result"]["components"][0]["value_range"],
            {"min": None, "max": None},
        )

    def test_extract_single_dimension_repairs_failed_input_structure_once(self) -> None:
        client = FakeClient(
            [
                {
                    "type": "composite",
                    "length": {"min": None, "max": None},
                    "value_range": {"min": None, "max": None},
                    "properties": {},
                    "components": [
                        {
                            "role": "queries",
                            "type": "array",
                            "length": {"min": 1, "max": 5},
                            "value_range": {"min": 0, "max": 20},
                            "properties": {},
                        }
                    ],
                },
                {
                    "type": "composite",
                    "length": {"min": None, "max": None},
                    "value_range": {"min": None, "max": None},
                    "properties": {},
                    "components": [
                        {
                            "role": "queries",
                            "role_description": "online query stream",
                            "type": "array",
                            "length": {"min": 1, "max": 5},
                            "value_range": {"min": 0, "max": 20},
                            "properties": {},
                        }
                    ],
                },
            ]
        )

        result = extract_single_dimension(
            client=client,
            problem={
                "problem_id": "demo",
                "source": {"source_name": "cf"},
                "title": "",
                "description": "",
            },
            dimension_name="input_structure",
            rate_limiter=RateLimiter(min_interval=0.0),
            logger=logging.getLogger("extract-test"),
            temperature=0.0,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(
            result["result"]["components"][0]["role_description"],
            "online query stream",
        )

    def test_extract_single_dimension_marks_invalid_composite_as_failed(self) -> None:
        result = extract_single_dimension(
            client=FakeClient(
                {
                    "type": "composite",
                    "length": {"min": None, "max": None},
                    "value_range": {"min": None, "max": None},
                    "properties": {},
                    "components": [
                        {
                            "role": "queries",
                            "type": "array",
                            "length": {"min": 1, "max": 5},
                            "value_range": {"min": 0, "max": 20},
                            "properties": {},
                        }
                    ],
                }
            ),
            problem={
                "problem_id": "demo",
                "source": {"source_name": "cf"},
                "title": "",
                "description": "",
            },
            dimension_name="input_structure",
            rate_limiter=RateLimiter(min_interval=0.0),
            logger=logging.getLogger("extract-test"),
            temperature=0.0,
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["result"], {})
        self.assertIn("components[0].role_description", result["error"])


class ResumeTests(unittest.TestCase):
    def test_resume_reuses_only_successful_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            output_dir = Path(tempdir)
            raw_dir = output_dir / "raw"
            raw_dir.mkdir()
            problem_id = "demo"
            (raw_dir / f"{problem_id}_input_structure.json").write_text(
                json.dumps({"status": "success", "result": {"kept": True}}),
                encoding="utf-8",
            )
            (raw_dir / f"{problem_id}_core_constraints.json").write_text(
                json.dumps({"status": "failed", "error": "HTTP Error 402: Payment Required"}),
                encoding="utf-8",
            )
            (raw_dir / f"{problem_id}_objective.json").write_text("not-json", encoding="utf-8")
            (raw_dir / f"{problem_id}_invariant.json").write_text(
                json.dumps({"result": {}}),
                encoding="utf-8",
            )

            def successful_result(_client, problem, dimension_name, _rate_limiter, _logger, temperature=0.4):
                return {
                    "problem_id": problem["problem_id"],
                    "source": problem.get("source", ""),
                    "dimension": dimension_name,
                    "result": {"retried": True},
                    "status": "success",
                }

            with mock.patch("extract.extract_single_dimension", side_effect=successful_result) as extract_mock:
                extract_all_problems(
                    client=FakeClient({}),
                    problems=[{"problem_id": problem_id, "source": "codeforces"}],
                    output_dir=output_dir,
                    resume=True,
                    logger=logging.getLogger("extract-resume-test"),
                    temperature=0.0,
                )

            retried_dimensions = [call.args[2] for call in extract_mock.call_args_list]
            self.assertEqual(
                retried_dimensions,
                ["core_constraints", "objective", "invariant"],
            )
            kept = json.loads(
                (raw_dir / f"{problem_id}_input_structure.json").read_text(encoding="utf-8")
            )
            self.assertEqual(kept["result"], {"kept": True})
            for dimension in retried_dimensions:
                payload = json.loads(
                    (raw_dir / f"{problem_id}_{dimension}.json").read_text(encoding="utf-8")
                )
                self.assertEqual(payload["status"], "success")
                self.assertEqual(payload["result"], {"retried": True})


class QwenClientResponseValidationTests(unittest.TestCase):
    def test_extract_chat_content_accepts_normal_response(self) -> None:
        content = _extract_chat_content(
            {"choices": [{"message": {"content": '{"status":"ok"}'}}]},
            http_status=200,
        )

        self.assertEqual(content, '{"status":"ok"}')

    def test_extract_chat_content_rejects_missing_choices(self) -> None:
        with self.assertRaisesRegex(QwenJSONError, "缺少非空 choices"):
            _extract_chat_content({"id": "chatcmpl-empty"}, http_status=200)

    def test_extract_chat_content_rejects_none_message(self) -> None:
        with self.assertRaisesRegex(QwenJSONError, "message 缺失或不是对象"):
            _extract_chat_content({"choices": [{"message": None}]}, http_status=200)

    def test_extract_chat_content_rejects_empty_content_with_http_status(self) -> None:
        with self.assertRaisesRegex(QwenJSONError, "HTTP 200.*content 为空"):
            _extract_chat_content({"choices": [{"message": {"content": ""}}]}, http_status=200)


if __name__ == "__main__":
    unittest.main()
