"""P2 Tests: ComfyUI nodes and workflow validation."""

import pytest
import json
from pathlib import Path


class TestP2NodeRegistration:
    """Test P2 nodes registered."""

    def test_p2_nodes_present(self):
        from awp_rp_runtime_v2.nodes import NODE_CLASS_MAPPINGS
        p2 = {"AWPV2Director", "AWPV2DelegationPlan", "AWPV2DynamicSubAgentPool",
              "AWPV2SuggestionMerge", "AWPV2WriterInputBundle", "AWPV2AgentTrace"}
        for name in p2:
            assert name in NODE_CLASS_MAPPINGS, f"Missing: {name}"

    def test_all_nodes_p1_plus_p2(self):
        from awp_rp_runtime_v2.nodes import NODE_CLASS_MAPPINGS
        # 8 P1 + 6 P2 + 8 M1 + 12 C1 + 6 D1 + 7 D2 + 7 D3 + 7 D4 + 7 D5 + 9 P-CardImport + 10 P-CardSession + 8 P-FirstTurn + 2 Observability + 2 Canonical + 4 Persistent + 1 P1-RealEvolution + 1 AcceptedTextOutput + 7 MemoryCuration + 8 Novel
        assert len(NODE_CLASS_MAPPINGS) == 120

    def test_display_names_chinese(self):
        from awp_rp_runtime_v2.nodes import NODE_DISPLAY_NAME_MAPPINGS
        assert "AWP V2 叙事总控" in NODE_DISPLAY_NAME_MAPPINGS.values()
        assert "AWP V2 委派计划" in NODE_DISPLAY_NAME_MAPPINGS.values()

