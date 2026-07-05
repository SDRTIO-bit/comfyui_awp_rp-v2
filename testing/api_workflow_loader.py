"""API Workflow Loader — loads and validates API workflow JSON files.

API workflows are the prompt-format JSON files submitted to /prompt.
They live in workflows/api/*.api.json.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_DEFAULT_WORKFLOW_DIR = Path(__file__).resolve().parents[1] / "workflows" / "api"


class APIWorkflowLoader:
    """Load and validate API workflow files."""

    def __init__(self, workflow_dir: str | Path | None = None) -> None:
        self.workflow_dir = Path(workflow_dir) if workflow_dir is not None else _DEFAULT_WORKFLOW_DIR

    def load(self, name: str) -> dict[str, Any]:
        """Load an API workflow by name (without .api.json extension)."""
        path = self.workflow_dir / f"{name}.api.json"
        if not path.exists():
            raise FileNotFoundError(f"API workflow not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.validate(data, name)
        return data

    def validate(self, workflow: dict[str, Any], name: str = "unknown") -> None:
        """Validate an API workflow has the expected structure.

        API workflows are dicts of node_id -> {class_type, inputs}.
        """
        if not isinstance(workflow, dict):
            raise ValueError(f"API workflow '{name}' must be a dict, got {type(workflow).__name__}")

        if not workflow:
            raise ValueError(f"API workflow '{name}' is empty")

        for node_id, node_def in workflow.items():
            if not isinstance(node_def, dict):
                raise ValueError(f"Node '{node_id}' in '{name}' must be a dict")
            if "class_type" not in node_def:
                raise ValueError(f"Node '{node_id}' in '{name}' missing 'class_type'")
            if "inputs" not in node_def:
                raise ValueError(f"Node '{node_id}' in '{name}' missing 'inputs'")

    def list_workflows(self) -> list[str]:
        """List all available API workflow names."""
        if not self.workflow_dir.exists():
            return []
        return sorted([
            f.stem.replace(".api", "")
            for f in self.workflow_dir.glob("*.api.json")
        ])
