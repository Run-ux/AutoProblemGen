from __future__ import annotations

import unittest
from pathlib import Path

from verification_runner import _build_error_payload


class VerificationRunnerTests(unittest.TestCase):
    def test_error_payload_preserves_structured_verification_details(self) -> None:
        error = RuntimeError("标准解修复达到最大轮数")
        error.details = {
            "phase": "standard_solution_repair",
            "final_code": "best_code",
            "failure_summary": {"failed_count": 1},
        }

        payload = _build_error_payload(Path("artifact.json"), error, "traceback")

        self.assertEqual(payload["error_type"], "RuntimeError")
        self.assertEqual(payload["details"]["final_code"], "best_code")
        self.assertEqual(payload["details"]["failure_summary"]["failed_count"], 1)

    def test_error_payload_omits_empty_details(self) -> None:
        payload = _build_error_payload(Path("artifact.json"), ValueError("bad"), "traceback")

        self.assertNotIn("details", payload)


if __name__ == "__main__":
    unittest.main()
