"""Tests for observable workflow graphs."""

from __future__ import annotations

import json
from pathlib import Path

from awp_rp_runtime_v2.nodes import NODE_CLASS_MAPPINGS


def _input_type(node_cls, input_name: str):
    input_spec = node_cls.INPUT_TYPES()
    for group in ("required", "optional"):
        if input_name in input_spec.get(group, {}):
            return input_spec[group][input_name][0]
    return None


def _validate_api_link_types(workflow: dict) -> list[tuple[str, str, str, str, str]]:
    from comfy_execution.validation import validate_node_input

    mismatches = []
    for node_id, node_def in workflow.items():
        node_cls = NODE_CLASS_MAPPINGS[node_def["class_type"]]
        for input_name, value in node_def.get("inputs", {}).items():
            if not isinstance(value, list):
                continue
            source_id, source_slot = str(value[0]), int(value[1])
            source_def = workflow[source_id]
            source_cls = NODE_CLASS_MAPPINGS[source_def["class_type"]]
            received = source_cls.RETURN_TYPES[source_slot]
            expected = _input_type(node_cls, input_name)
            if expected is None or not validate_node_input(received, expected):
                mismatches.append((
                    node_id,
                    node_def["class_type"],
                    input_name,
                    received,
                    str(expected),
                ))
    return mismatches


def _validate_gui_link_types(workflow: dict) -> list[tuple[str, str, str, str, str]]:
    from comfy_execution.validation import validate_node_input

    nodes = {str(node["id"]): node for node in workflow["nodes"]}
    links = {int(link[0]): link for link in workflow["links"]}
    mismatches = []

    for node in workflow["nodes"]:
        node_id = str(node["id"])
        node_cls = NODE_CLASS_MAPPINGS[node["type"]]
        for input_index, input_def in enumerate(node.get("inputs", [])):
            link_id = input_def.get("link")
            if link_id is None:
                continue
            link = links[int(link_id)]
            source_id = str(link[1])
            source_slot = int(link[2])
            source_node = nodes[source_id]
            source_cls = NODE_CLASS_MAPPINGS[source_node["type"]]
            received = source_cls.RETURN_TYPES[source_slot]
            expected = _input_type(node_cls, input_def["name"])
            if expected is None or not validate_node_input(received, expected):
                mismatches.append((
                    node_id,
                    node["type"],
                    input_def["name"],
                    received,
                    str(expected),
                ))
    return mismatches


def test_full_architecture_turn_is_type_valid_observable_gui_graph():
    path = Path("workflows/awp_v2_playable_workflows/full_architecture_turn.graph.json")
    workflow = json.loads(path.read_text(encoding="utf-8"))

    class_types = {node["type"] for node in workflow["nodes"]}

    assert "AWPV2PersistentContinuationTurn" in class_types
    assert "AWPV2PersistentTurnObserver" in class_types
    assert _validate_gui_link_types(workflow) == []


def test_playable_send_turn_is_type_valid_gui_graph():
    path = Path("workflows/awp_v2_playable_workflows/03_send_turn.api.json")
    workflow = json.loads(path.read_text(encoding="utf-8"))

    assert "nodes" in workflow
    assert "links" in workflow
    assert _validate_gui_link_types(workflow) == []


def test_api_send_turn_prompt_stays_type_valid():
    path = Path("workflows/api/send_turn.api.json")
    workflow = json.loads(path.read_text(encoding="utf-8"))

    assert "nodes" not in workflow
    assert _validate_api_link_types(workflow) == []


def test_all_workflow_json_links_are_type_valid():
    failures = []
    for path in sorted(Path("workflows").glob("**/*.json")):
        workflow = json.loads(path.read_text(encoding="utf-8"))
        if "nodes" in workflow and "links" in workflow:
            mismatches = _validate_gui_link_types(workflow)
        elif all(isinstance(value, dict) and "class_type" in value for value in workflow.values()):
            mismatches = _validate_api_link_types(workflow)
        else:
            mismatches = []
        if mismatches:
            failures.append((str(path), mismatches))

    assert failures == []
