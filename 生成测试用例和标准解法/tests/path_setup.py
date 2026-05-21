from __future__ import annotations

import sys
from pathlib import Path


MODULE_DIR = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = Path(__file__).resolve().parents[2] / "总流程"

module_dir_text = str(MODULE_DIR)
if module_dir_text not in sys.path:
    sys.path.insert(0, module_dir_text)

workflow_dir_text = str(WORKFLOW_DIR)
if workflow_dir_text not in sys.path:
    sys.path.append(workflow_dir_text)
