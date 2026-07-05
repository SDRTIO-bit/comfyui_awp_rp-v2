"""AWPV2TraceDisplay — output node for displaying AWP trace data.

This is a terminal output node that accepts any AWP type and displays
its JSON representation. ComfyUI requires output nodes to execute workflows.
"""

from __future__ import annotations

import json
from typing import Any


class AnyType(str):
    def __ne__(self, _value: object) -> bool:
        return False


ANY_TYPE = AnyType("*")


class AWPV2TraceDisplay:

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "data": (ANY_TYPE,),
            },
            "optional": {
                "label": ("STRING", {"default": "AWP Trace"}),
            },
        }

    RETURN_TYPES = ()
    RETURN_NAMES = ()
    FUNCTION = "execute"
    CATEGORY = "AWP/RP_V2"
    OUTPUT_NODE = True

    def execute(self, data: Any, label: str = "AWP Trace") -> dict[str, Any]:
        # Format the data for display
        if isinstance(data, dict):
            text = json.dumps(data, indent=2, ensure_ascii=False)
        elif isinstance(data, str):
            text = data
        else:
            text = str(data)

        # Truncate for display
        if len(text) > 5000:
            text = text[:5000] + "\n... (truncated)"

        return {"ui": {"text": [text]}}
