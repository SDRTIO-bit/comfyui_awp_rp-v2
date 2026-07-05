"""P1 Tests: ComfyUI nodes registration and workflow validation."""

import pytest
import json
from pathlib import Path


class TestNodeRegistration:
    """Test 19: all nodes registered."""

    def test_all_nodes_registered(self):
        from awp_rp_runtime_v2.nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

        p1_expected = {
            "AWPV2CardStateInit", "AWPV2RoundSnapshot", "AWPV2QualityGate",
            "AWPV2CardStateCommit", "AWPV2TurnRecordCommit",
            "AWPV2RetryTurn", "AWPV2ContinueTurn", "AWPV2ExecutionTrace",
        }
        p2_expected = {
            "AWPV2Director", "AWPV2DelegationPlan", "AWPV2DynamicSubAgentPool",
            "AWPV2SuggestionMerge", "AWPV2WriterInputBundle", "AWPV2AgentTrace",
        }
        m1_expected = {
            "AWPV2AcceptedTurnWindow", "AWPV2ActiveMemoryRecall", "AWPV2RagMemoryRecall",
            "AWPV2MemoryContextAssembler", "AWPV2MemoryCommitPlan",
            "AWPV2ActiveMemoryCommit", "AWPV2RagMemoryCommit", "AWPV2MemoryDiagnostics",
        }
        c1_expected = {
            "AWPV2DirectorPlan", "AWPV2ToolPlan", "AWPV2ToolGateway",
            "AWPV2EnrichmentMerge", "AWPV2FinalTurnBrief", "AWPV2WriterV2",
            "AWPV2WriterInputBundleV2", "AWPV2QualityPipeline", "AWPV2Reviser",
            "AWPV2WriterOutput", "AWPV2ToolTrace", "AWPV2WriterGenerate",
        }
        d1_expected = {
            "AWPV2HistoryRecallTrigger", "AWPV2HistoryRecallRequest",
            "AWPV2HistoryRecallAgent", "AWPV2RecallEvidenceRanker",
            "AWPV2HistoryRecallResult", "AWPV2HistoryRecallDiagnostics",
        }
        d2_expected = {
            "AWPV2OpportunityTrigger", "AWPV2OpportunityRequest",
            "AWPV2OpportunityAgent", "AWPV2OpportunityValidator",
            "AWPV2OpportunityRanker", "AWPV2OpportunityResult",
            "AWPV2OpportunityDiagnostics",
        }
        d3_expected = {
            "AWPV2WorldLifeTrigger", "AWPV2WorldLifeRequest",
            "AWPV2WorldLifeAgent", "AWPV2WorldLifeValidator",
            "AWPV2WorldLifeRanker", "AWPV2WorldLifeResult",
            "AWPV2WorldLifeDiagnostics",
        }
        d4_expected = {
            "AWPV2EmotionRelationshipTrigger", "AWPV2EmotionRelationshipRequest",
            "AWPV2EmotionRelationshipAgent", "AWPV2EmotionRelationshipValidator",
            "AWPV2EmotionRelationshipRanker", "AWPV2EmotionRelationshipResult",
            "AWPV2EmotionRelationshipDiagnostics",
        }
        d5_expected = {
            "AWPV2ContinuityTrigger", "AWPV2ContinuityRequest",
            "AWPV2ContinuityAgent", "AWPV2ContinuityValidator",
            "AWPV2ContinuityRanker", "AWPV2ContinuityResult",
            "AWPV2ContinuityDiagnostics",
        }
        card_import_expected = {
            "AWPV2CardSourceLoad", "AWPV2CardPayloadParse", "AWPV2CardSecurityScan",
            "AWPV2CardNormalize", "AWPV2CardImportReview", "AWPV2CardImportApproval",
            "AWPV2CardDefinitionCommit", "AWPV2CardCatalogLookup", "AWPV2CardImportDiagnostics",
        }
        card_session_expected = {
            "AWPV2CardSessionBootstrapRequest", "AWPV2CardDefinitionReadyValidator",
            "AWPV2GreetingSelection", "AWPV2CardStateInitializer",
            "AWPV2OpeningRecordCommit", "AWPV2WorldbookBindingBuilder",
            "AWPV2CardSessionBindingCommit", "AWPV2CardSessionBootstrapDiagnostics",
            "AWPV2CardImportAndBootstrap", "AWPV2CardDefinitionFixtureLoad",
        }
        first_turn_expected = {
            "AWPV2FirstTurnRequest", "AWPV2SessionReadyValidator",
            "AWPV2OpeningContextLoader", "AWPV2SessionBoundWorldbookRetriever",
            "AWPV2FirstTurnContextAssembler", "AWPV2FirstTurnReceipt",
            "AWPV2FirstTurnDiagnostics", "AWPV2FirstTurnExecution",
        }
        observability_expected = {
            "AWPV2TraceDisplay", "AWPV2PersistentTurnObserver",
        }
        canonical_expected = {
            "AWPV2AcceptedTextOutput",
            "AWPV2TurnResultProbe",
            "AWPV2ContinuationTurnExecution",
            "AWPV2SessionRuntimeLoad",
            "AWPV2PersistentBootstrap",
            "AWPV2PersistentFirstTurn",
            "AWPV2PersistentContinuationTurn",
        }
        p1_real_expected = {
            "AWPV2ContinueTurnP1",
        }
        memory_curation_expected = {
            "AWPV2MemoryCurationTrigger", "AWPV2MemoryCurationRequest",
            "AWPV2MemoryCurationValidator", "AWPV2MemoryCurationRanker",
            "AWPV2MemoryCurationCommitPlan", "AWPV2MemoryCurationDiagnostics",
            "AWPV2MemoryCuratorAgent",
        }
        novel_expected = {
            "AWPV2NovelProjectCreate", "AWPV2NovelVolumePlan",
            "AWPV2NovelChapterPlan", "AWPV2NovelChapterWrite",
            "AWPV2NovelChapterRevise", "AWPV2NovelLedgerView",
            "AWPV2NovelExport", "AWPV2NovelBatchWrite",
        }
        all_expected = p1_expected | p2_expected | m1_expected | c1_expected | d1_expected | d2_expected | d3_expected | d4_expected | d5_expected | card_import_expected | card_session_expected | first_turn_expected | observability_expected | canonical_expected | p1_real_expected | memory_curation_expected | novel_expected
        assert set(NODE_CLASS_MAPPINGS.keys()) == all_expected
        assert set(NODE_DISPLAY_NAME_MAPPINGS.keys()) == all_expected

    def test_nodes_have_required_attributes(self):
        from awp_rp_runtime_v2.nodes import NODE_CLASS_MAPPINGS

        for name, cls in NODE_CLASS_MAPPINGS.items():
            assert hasattr(cls, 'INPUT_TYPES'), f"{name} missing INPUT_TYPES"
            assert hasattr(cls, 'RETURN_TYPES'), f"{name} missing RETURN_TYPES"
            assert hasattr(cls, 'RETURN_NAMES'), f"{name} missing RETURN_NAMES"
            assert hasattr(cls, 'FUNCTION'), f"{name} missing FUNCTION"
            assert hasattr(cls, 'CATEGORY'), f"{name} missing CATEGORY"

    def test_node_display_names_chinese(self):
        from awp_rp_runtime_v2.nodes import NODE_DISPLAY_NAME_MAPPINGS
        for name, display in NODE_DISPLAY_NAME_MAPPINGS.items():
            assert "AWP V2" in display, f"{name} display name should contain 'AWP V2'"

    def test_trace_display_declares_comfy_union_input_type(self):
        from comfy_execution.validation import validate_node_input
        from awp_rp_runtime_v2.nodes.trace_display_node import AWPV2TraceDisplay

        data_type = AWPV2TraceDisplay.INPUT_TYPES()["required"]["data"][0]

        assert isinstance(data_type, str)
        assert validate_node_input("JSON", data_type)
        assert validate_node_input("DIRECTOR_PLAN", data_type)


class TestNodeExecution:
    """Test nodes execute without errors."""

    def test_card_state_init(self):
        from awp_rp_runtime_v2.nodes.card_state_init_node import AWPV2CardStateInit
        node = AWPV2CardStateInit()
        (result,) = node.execute("card1", "sess1")
        assert result["card_id"] == "card1"
        assert result["session_id"] == "sess1"
        assert result["revision"] == 0

    def test_round_snapshot(self):
        from awp_rp_runtime_v2.nodes.round_snapshot_node import AWPV2RoundSnapshot
        node = AWPV2RoundSnapshot()
        state = {"card_id": "c1", "session_id": "s1", "revision": 0,
                 "schema_id": "awp.rp.card-state.v1", "schema_version": 1,
                 "variables": {}, "event_flags": {}, "active_stage_ids": [],
                 "scene_state": {}, "diagnostics": {}}
        (result,) = node.execute(state, "hello")
        assert result["card_id"] == "c1"
        assert result["player_input"] == "hello"
        assert "snapshot_id" in result

    def test_quality_gate_accept(self):
        from awp_rp_runtime_v2.nodes.quality_gate_node import AWPV2QualityGate
        node = AWPV2QualityGate()
        snap = {"card_id": "c1", "session_id": "s1", "trace_id": "t1",
                "snapshot_id": "s1", "schema_id": "awp.rp.round-snapshot.v1",
                "schema_version": 1, "base_card_state_revision": 0,
                "card_state": {}, "player_input": "", "recent_turn_records": [],
                "active_worldbook_entries": [], "active_memories": [], "rag_recall": []}
        (result,) = node.execute("This is a long enough text to pass the length check.", snap, auto_accept=True)
        assert result["verdict"] == "accept"

    def test_quality_gate_revise(self):
        from awp_rp_runtime_v2.nodes.quality_gate_node import AWPV2QualityGate
        node = AWPV2QualityGate()
        snap = {"card_id": "c1", "session_id": "s1", "trace_id": "t1",
                "snapshot_id": "s1", "schema_id": "awp.rp.round-snapshot.v1",
                "schema_version": 1, "base_card_state_revision": 0,
                "card_state": {}, "player_input": "", "recent_turn_records": [],
                "active_worldbook_entries": [], "active_memories": [], "rag_recall": []}
        (result,) = node.execute("Hi", snap)  # Too short
        assert result["verdict"] == "revise"
        assert len(result["blocking_reasons"]) > 0

    def test_retry_turn(self):
        from awp_rp_runtime_v2.nodes.retry_turn_node import AWPV2RetryTurn
        node = AWPV2RetryTurn()
        decision = {"verdict": "revise", "blocking_reasons": ["too short"],
                    "retry_count": 0, "max_retries": 3, "retry_allowed": True}
        ctx, can_retry, count = node.execute(decision)
        assert can_retry
        assert count == 1
        assert "too short" in ctx

    def test_retry_turn_rejected_final(self):
        from awp_rp_runtime_v2.nodes.retry_turn_node import AWPV2RetryTurn
        node = AWPV2RetryTurn()
        decision = {"verdict": "reject", "blocking_reasons": ["fatal"],
                    "retry_count": 3, "max_retries": 3, "retry_allowed": False}
        ctx, can_retry, count = node.execute(decision)
        assert not can_retry


class TestD1NodeRegistration:
    """D1: History/Recall node registration tests."""

    def test_d1_nodes_present(self):
        from awp_rp_runtime_v2.nodes import NODE_CLASS_MAPPINGS
        d1 = {
            "AWPV2HistoryRecallTrigger", "AWPV2HistoryRecallRequest",
            "AWPV2HistoryRecallAgent", "AWPV2RecallEvidenceRanker",
            "AWPV2HistoryRecallResult", "AWPV2HistoryRecallDiagnostics",
        }
        for name in d1:
            assert name in NODE_CLASS_MAPPINGS, f"Missing: {name}"

    def test_d1_display_names_chinese(self):
        from awp_rp_runtime_v2.nodes import NODE_DISPLAY_NAME_MAPPINGS
        d1_displays = [
            "AWP V2 历史回查触发", "AWP V2 历史回查请求",
            "AWP V2 历史回查Agent", "AWP V2 回查证据排序",
            "AWP V2 历史回查结果", "AWP V2 历史回查诊断",
        ]
        for display in d1_displays:
            assert display in NODE_DISPLAY_NAME_MAPPINGS.values(), f"Missing: {display}"
