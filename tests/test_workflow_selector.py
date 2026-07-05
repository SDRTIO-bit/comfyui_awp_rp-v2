from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from awp_rp_runtime_v2.tests.test_management_api_new_endpoints import (
    _Request,
    _data,
    _load_api,
)


def test_list_workflows_returns_api_format_only(monkeypatch):
    _module, routes = _load_api(monkeypatch)

    handler = routes.handlers[("GET", "/awp/api/v1/workflows")]
    response = asyncio.run(handler(_Request()))

    assert response.status == 200
    workflows = _data(response)
    names = [w["name"] for w in workflows]
    assert names == ["continue_world", "first_turn", "send_turn"]
    assert all("class_types" in w for w in workflows)
    assert all(w["node_count"] > 0 for w in workflows)


def test_list_workflows_works_when_package_loaded_from_custom_nodes(monkeypatch, tmp_path):
    _module, routes = _load_api(monkeypatch)
    package_root = Path(__file__).resolve().parents[1]
    custom_nodes_root = package_root.parent
    cleaned_path = [
        path
        for path in sys.path
        if Path(path or ".").resolve() != package_root
    ]
    monkeypatch.setattr(sys, "path", [str(custom_nodes_root), *cleaned_path])
    monkeypatch.chdir(tmp_path)
    monkeypatch.delitem(sys.modules, "testing", raising=False)

    handler = routes.handlers[("GET", "/awp/api/v1/workflows")]
    response = asyncio.run(handler(_Request()))

    assert response.status == 200
    assert [w["name"] for w in _data(response)] == [
        "continue_world",
        "first_turn",
        "send_turn",
    ]


def test_list_writer_presets(monkeypatch):
    _module, routes = _load_api(monkeypatch)

    handler = routes.handlers[("GET", "/awp/api/v1/presets/writer")]
    response = asyncio.run(handler(_Request()))

    assert response.status == 200
    presets = _data(response)
    assert "kedai_heavy_v1" in presets
    assert "addvar_keidai" in presets


def test_get_writer_preset_content(monkeypatch):
    _module, routes = _load_api(monkeypatch)

    handler = routes.handlers[("GET", "/awp/api/v1/presets/writer/{name}")]
    response = asyncio.run(handler(_Request(match_info={"name": "kedai_heavy_v1"})))

    assert response.status == 200
    preset = _data(response)
    assert preset["name"] == "kedai_heavy_v1"
    assert preset["content"]
    assert preset["path"].endswith("kedai_heavy_v1.txt")
