"""ComfyUI nodes for RP Runtime V2 — P1 + P2 + C1 + D + P-CardImport + P-CardSession + P-FirstTurn + P1-RealEvolution."""

from .card_state_init_node import AWPV2CardStateInit
from .round_snapshot_node import AWPV2RoundSnapshot
from .quality_gate_node import AWPV2QualityGate
from .card_state_commit_node import AWPV2CardStateCommit
from .turn_record_commit_node import AWPV2TurnRecordCommit
from .retry_turn_node import AWPV2RetryTurn
from .continue_turn_node import AWPV2ContinueTurn
from .execution_trace_node import AWPV2ExecutionTrace

# P1: Real Continue (world-advance)
from .continue_turn_execution_node import AWPV2ContinueTurn as AWPV2ContinueTurnP1

# P2 nodes
from .director_node import AWPV2Director
from .delegation_plan_node import AWPV2DelegationPlan
from .dynamic_subagent_pool_node import AWPV2DynamicSubAgentPool
from .suggestion_merge_node import AWPV2SuggestionMerge
from .writer_input_bundle_node import AWPV2WriterInputBundle
from .agent_trace_node import AWPV2AgentTrace

# M1 memory nodes
from .accepted_turn_window_node import AWPV2AcceptedTurnWindow
from .active_memory_recall_node import AWPV2ActiveMemoryRecall
from .rag_memory_recall_node import AWPV2RagMemoryRecall
from .memory_context_assembler_node import AWPV2MemoryContextAssembler
from .memory_commit_plan_node import AWPV2MemoryCommitPlan
from .active_memory_commit_node import AWPV2ActiveMemoryCommit
from .rag_memory_commit_node import AWPV2RagMemoryCommit
from .memory_diagnostics_node import AWPV2MemoryDiagnostics

# C1: Dual Main Agent + Tool Gateway nodes
from .director_plan_node import AWPV2DirectorPlan
from .tool_plan_node import AWPV2ToolPlan
from .tool_gateway_node import AWPV2ToolGateway
from .enrichment_merge_node import AWPV2EnrichmentMerge
from .final_turn_brief_node import AWPV2FinalTurnBrief
from .writer_output_node import AWPV2WriterOutput as AWPV2WriterV2
from .writer_v2_node import AWPV2WriterGenerate
from .writer_input_bundle_v2_node import AWPV2WriterInputBundleV2
from .quality_pipeline_node import AWPV2QualityPipeline
from .reviser_node import AWPV2Reviser
from .writer_output_node import AWPV2WriterOutput
from .tool_trace_node import AWPV2ToolTrace

# D1: History/Recall nodes
from .history_recall_trigger_node import AWPV2HistoryRecallTrigger
from .history_recall_request_node import AWPV2HistoryRecallRequest
from .history_recall_agent_node import AWPV2HistoryRecallAgent
from .recall_evidence_ranker_node import AWPV2RecallEvidenceRanker
from .history_recall_result_node import AWPV2HistoryRecallResult
from .history_recall_diagnostics_node import AWPV2HistoryRecallDiagnostics

# D2: Opportunity nodes
from .opportunity_trigger_node import AWPV2OpportunityTrigger
from .opportunity_request_node import AWPV2OpportunityRequest
from .opportunity_agent_node import AWPV2OpportunityAgent
from .opportunity_validator_node import AWPV2OpportunityValidator
from .opportunity_ranker_node import AWPV2OpportunityRanker
from .opportunity_result_node import AWPV2OpportunityResult
from .opportunity_diagnostics_node import AWPV2OpportunityDiagnostics

# D3: World-Life nodes
from .world_life_trigger_node import AWPV2WorldLifeTrigger
from .world_life_request_node import AWPV2WorldLifeRequest
from .world_life_agent_node import AWPV2WorldLifeAgent
from .world_life_validator_node import AWPV2WorldLifeValidator
from .world_life_ranker_node import AWPV2WorldLifeRanker
from .world_life_result_node import AWPV2WorldLifeResult
from .world_life_diagnostics_node import AWPV2WorldLifeDiagnostics

# D4: Emotion/Relationship nodes
from .emotion_relationship_trigger_node import AWPV2EmotionRelationshipTrigger
from .emotion_relationship_request_node import AWPV2EmotionRelationshipRequest
from .emotion_relationship_agent_node import AWPV2EmotionRelationshipAgent
from .emotion_relationship_validator_node import AWPV2EmotionRelationshipValidator
from .emotion_relationship_ranker_node import AWPV2EmotionRelationshipRanker
from .emotion_relationship_result_node import AWPV2EmotionRelationshipResult
from .emotion_relationship_diagnostics_node import AWPV2EmotionRelationshipDiagnostics

# D5: Continuity nodes
from .continuity_trigger_node import AWPV2ContinuityTrigger
from .continuity_request_node import AWPV2ContinuityRequest
from .continuity_agent_node import AWPV2ContinuityAgent
from .continuity_validator_node import AWPV2ContinuityValidator
from .continuity_ranker_node import AWPV2ContinuityRanker
from .continuity_result_node import AWPV2ContinuityResult
from .continuity_diagnostics_node import AWPV2ContinuityDiagnostics

# D6: Memory Curation nodes
from .memory_curation_trigger_node import AWPV2MemoryCurationTrigger
from .memory_curation_request_node import AWPV2MemoryCurationRequest
from .memory_curator_agent_node import AWPV2MemoryCuratorAgent
from .memory_curation_validator_node import AWPV2MemoryCurationValidator
from .memory_curation_ranker_node import AWPV2MemoryCurationRanker
from .memory_curation_diagnostics_node import AWPV2MemoryCurationDiagnostics
from .memory_curation_commit_plan_node import AWPV2MemoryCurationCommitPlan

# P-CardImport nodes
from .card_source_load_node import AWPV2CardSourceLoad
from .card_payload_parse_node import AWPV2CardPayloadParse
from .card_security_scan_node import AWPV2CardSecurityScan
from .card_normalize_node import AWPV2CardNormalize
from .card_import_review_node import AWPV2CardImportReview
from .card_import_approval_node import AWPV2CardImportApproval
from .card_definition_commit_node import AWPV2CardDefinitionCommit
from .card_catalog_lookup_node import AWPV2CardCatalogLookup
from .card_import_diagnostics_node import AWPV2CardImportDiagnostics

# P-CardSession Bootstrap nodes
from .card_session_bootstrap_request_node import AWPV2CardSessionBootstrapRequest
from .card_definition_ready_validator_node import AWPV2CardDefinitionReadyValidator
from .greeting_selection_node import AWPV2GreetingSelection
from .card_state_initializer_node import AWPV2CardStateInitializer
from .opening_record_commit_node import AWPV2OpeningRecordCommit
from .worldbook_binding_builder_node import AWPV2WorldbookBindingBuilder
from .card_session_binding_commit_node import AWPV2CardSessionBindingCommit
from .card_session_bootstrap_diagnostics_node import AWPV2CardSessionBootstrapDiagnostics
from .card_import_and_bootstrap_node import AWPV2CardImportAndBootstrap
from .card_definition_fixture_load_node import AWPV2CardDefinitionFixtureLoad

# P-FirstTurn: First Turn Execution nodes
from .first_turn_request_node import AWPV2FirstTurnRequest
from .session_ready_validator_node import AWPV2SessionReadyValidator
from .opening_context_loader_node import AWPV2OpeningContextLoader
from .session_bound_worldbook_retriever_node import AWPV2SessionBoundWorldbookRetriever
from .first_turn_context_assembler_node import AWPV2FirstTurnContextAssembler
from .first_turn_receipt_node import AWPV2FirstTurnReceipt
from .first_turn_diagnostics_node import AWPV2FirstTurnDiagnostics
from .first_turn_execution_node import AWPV2FirstTurnExecution

# Observability: trace display output node
from .trace_display_node import AWPV2TraceDisplay
from .persistent_turn_observer_node import AWPV2PersistentTurnObserver

# P-Canonical: Turn Result Probe + Continuation Turn
from .accepted_text_output_node import AWPV2AcceptedTextOutput
from .turn_result_probe_node import AWPV2TurnResultProbe
from .continuation_turn_execution_node import AWPV2ContinuationTurnExecution

# P-Persistent: Session Runtime Load + Persistent Bootstrap/First/Continuation
from .session_runtime_load_node import AWPV2SessionRuntimeLoad
from .persistent_bootstrap_node import AWPV2PersistentBootstrap
from .persistent_first_turn_node import AWPV2PersistentFirstTurn
from .persistent_continuation_turn_node import AWPV2PersistentContinuationTurn

# Novel Mode nodes
from .novel_nodes import (
    AWPV2NovelProjectCreate,
    AWPV2NovelVolumePlan,
    AWPV2NovelChapterPlan,
    AWPV2NovelChapterWrite,
    AWPV2NovelChapterRevise,
    AWPV2NovelLedgerView,
    AWPV2NovelExport,
    AWPV2NovelBatchWrite,
)

NODE_CLASS_MAPPINGS = {
    # P1
    "AWPV2CardStateInit": AWPV2CardStateInit,
    "AWPV2RoundSnapshot": AWPV2RoundSnapshot,
    "AWPV2QualityGate": AWPV2QualityGate,
    "AWPV2CardStateCommit": AWPV2CardStateCommit,
    "AWPV2TurnRecordCommit": AWPV2TurnRecordCommit,
    "AWPV2RetryTurn": AWPV2RetryTurn,
    "AWPV2ContinueTurn": AWPV2ContinueTurn,
    "AWPV2ExecutionTrace": AWPV2ExecutionTrace,
    # P2
    "AWPV2Director": AWPV2Director,
    "AWPV2DelegationPlan": AWPV2DelegationPlan,
    "AWPV2DynamicSubAgentPool": AWPV2DynamicSubAgentPool,
    "AWPV2SuggestionMerge": AWPV2SuggestionMerge,
    "AWPV2WriterInputBundle": AWPV2WriterInputBundle,
    "AWPV2AgentTrace": AWPV2AgentTrace,
    # M1
    "AWPV2AcceptedTurnWindow": AWPV2AcceptedTurnWindow,
    "AWPV2ActiveMemoryRecall": AWPV2ActiveMemoryRecall,
    "AWPV2RagMemoryRecall": AWPV2RagMemoryRecall,
    "AWPV2MemoryContextAssembler": AWPV2MemoryContextAssembler,
    "AWPV2MemoryCommitPlan": AWPV2MemoryCommitPlan,
    "AWPV2ActiveMemoryCommit": AWPV2ActiveMemoryCommit,
    "AWPV2RagMemoryCommit": AWPV2RagMemoryCommit,
    "AWPV2MemoryDiagnostics": AWPV2MemoryDiagnostics,
    # C1
    "AWPV2DirectorPlan": AWPV2DirectorPlan,
    "AWPV2ToolPlan": AWPV2ToolPlan,
    "AWPV2ToolGateway": AWPV2ToolGateway,
    "AWPV2EnrichmentMerge": AWPV2EnrichmentMerge,
    "AWPV2FinalTurnBrief": AWPV2FinalTurnBrief,
    "AWPV2WriterV2": AWPV2WriterV2,
    "AWPV2WriterInputBundleV2": AWPV2WriterInputBundleV2,
    "AWPV2QualityPipeline": AWPV2QualityPipeline,
    "AWPV2Reviser": AWPV2Reviser,
    "AWPV2WriterOutput": AWPV2WriterOutput,
    "AWPV2ToolTrace": AWPV2ToolTrace,
    # D1: History/Recall
    "AWPV2HistoryRecallTrigger": AWPV2HistoryRecallTrigger,
    "AWPV2HistoryRecallRequest": AWPV2HistoryRecallRequest,
    "AWPV2HistoryRecallAgent": AWPV2HistoryRecallAgent,
    "AWPV2RecallEvidenceRanker": AWPV2RecallEvidenceRanker,
    "AWPV2HistoryRecallResult": AWPV2HistoryRecallResult,
    "AWPV2HistoryRecallDiagnostics": AWPV2HistoryRecallDiagnostics,
    # D2: Opportunity
    "AWPV2OpportunityTrigger": AWPV2OpportunityTrigger,
    "AWPV2OpportunityRequest": AWPV2OpportunityRequest,
    "AWPV2OpportunityAgent": AWPV2OpportunityAgent,
    "AWPV2OpportunityValidator": AWPV2OpportunityValidator,
    "AWPV2OpportunityRanker": AWPV2OpportunityRanker,
    "AWPV2OpportunityResult": AWPV2OpportunityResult,
    "AWPV2OpportunityDiagnostics": AWPV2OpportunityDiagnostics,
    # D3: World-Life
    "AWPV2WorldLifeTrigger": AWPV2WorldLifeTrigger,
    "AWPV2WorldLifeRequest": AWPV2WorldLifeRequest,
    "AWPV2WorldLifeAgent": AWPV2WorldLifeAgent,
    "AWPV2WorldLifeValidator": AWPV2WorldLifeValidator,
    "AWPV2WorldLifeRanker": AWPV2WorldLifeRanker,
    "AWPV2WorldLifeResult": AWPV2WorldLifeResult,
    "AWPV2WorldLifeDiagnostics": AWPV2WorldLifeDiagnostics,
    # D4: Emotion/Relationship
    "AWPV2EmotionRelationshipTrigger": AWPV2EmotionRelationshipTrigger,
    "AWPV2EmotionRelationshipRequest": AWPV2EmotionRelationshipRequest,
    "AWPV2EmotionRelationshipAgent": AWPV2EmotionRelationshipAgent,
    "AWPV2EmotionRelationshipValidator": AWPV2EmotionRelationshipValidator,
    "AWPV2EmotionRelationshipRanker": AWPV2EmotionRelationshipRanker,
    "AWPV2EmotionRelationshipResult": AWPV2EmotionRelationshipResult,
    "AWPV2EmotionRelationshipDiagnostics": AWPV2EmotionRelationshipDiagnostics,
    # D5: Continuity
    "AWPV2ContinuityTrigger": AWPV2ContinuityTrigger,
    "AWPV2ContinuityRequest": AWPV2ContinuityRequest,
    "AWPV2ContinuityAgent": AWPV2ContinuityAgent,
    "AWPV2ContinuityValidator": AWPV2ContinuityValidator,
    "AWPV2ContinuityRanker": AWPV2ContinuityRanker,
    "AWPV2ContinuityResult": AWPV2ContinuityResult,
    "AWPV2ContinuityDiagnostics": AWPV2ContinuityDiagnostics,
    # D6: Memory Curation
    "AWPV2MemoryCurationTrigger": AWPV2MemoryCurationTrigger,
    "AWPV2MemoryCurationRequest": AWPV2MemoryCurationRequest,
    "AWPV2MemoryCuratorAgent": AWPV2MemoryCuratorAgent,
    "AWPV2MemoryCurationValidator": AWPV2MemoryCurationValidator,
    "AWPV2MemoryCurationRanker": AWPV2MemoryCurationRanker,
    "AWPV2MemoryCurationDiagnostics": AWPV2MemoryCurationDiagnostics,
    "AWPV2MemoryCurationCommitPlan": AWPV2MemoryCurationCommitPlan,
    # P-CardImport
    "AWPV2CardSourceLoad": AWPV2CardSourceLoad,
    "AWPV2CardPayloadParse": AWPV2CardPayloadParse,
    "AWPV2CardSecurityScan": AWPV2CardSecurityScan,
    "AWPV2CardNormalize": AWPV2CardNormalize,
    "AWPV2CardImportReview": AWPV2CardImportReview,
    "AWPV2CardImportApproval": AWPV2CardImportApproval,
    "AWPV2CardDefinitionCommit": AWPV2CardDefinitionCommit,
    "AWPV2CardCatalogLookup": AWPV2CardCatalogLookup,
    "AWPV2CardImportDiagnostics": AWPV2CardImportDiagnostics,
    # P-CardSession Bootstrap
    "AWPV2CardSessionBootstrapRequest": AWPV2CardSessionBootstrapRequest,
    "AWPV2CardDefinitionReadyValidator": AWPV2CardDefinitionReadyValidator,
    "AWPV2GreetingSelection": AWPV2GreetingSelection,
    "AWPV2CardStateInitializer": AWPV2CardStateInitializer,
    "AWPV2OpeningRecordCommit": AWPV2OpeningRecordCommit,
    "AWPV2WorldbookBindingBuilder": AWPV2WorldbookBindingBuilder,
    "AWPV2CardSessionBindingCommit": AWPV2CardSessionBindingCommit,
    "AWPV2CardSessionBootstrapDiagnostics": AWPV2CardSessionBootstrapDiagnostics,
    "AWPV2CardImportAndBootstrap": AWPV2CardImportAndBootstrap,
    "AWPV2CardDefinitionFixtureLoad": AWPV2CardDefinitionFixtureLoad,
    # P-FirstTurn
    "AWPV2FirstTurnRequest": AWPV2FirstTurnRequest,
    "AWPV2SessionReadyValidator": AWPV2SessionReadyValidator,
    "AWPV2OpeningContextLoader": AWPV2OpeningContextLoader,
    "AWPV2SessionBoundWorldbookRetriever": AWPV2SessionBoundWorldbookRetriever,
    "AWPV2FirstTurnContextAssembler": AWPV2FirstTurnContextAssembler,
    "AWPV2FirstTurnReceipt": AWPV2FirstTurnReceipt,
    "AWPV2FirstTurnDiagnostics": AWPV2FirstTurnDiagnostics,
    "AWPV2FirstTurnExecution": AWPV2FirstTurnExecution,
    # Observability
    "AWPV2TraceDisplay": AWPV2TraceDisplay,
    "AWPV2PersistentTurnObserver": AWPV2PersistentTurnObserver,
    # P-Canonical
    "AWPV2AcceptedTextOutput": AWPV2AcceptedTextOutput,
    "AWPV2TurnResultProbe": AWPV2TurnResultProbe,
    "AWPV2ContinuationTurnExecution": AWPV2ContinuationTurnExecution,
    # P-Persistent
    "AWPV2SessionRuntimeLoad": AWPV2SessionRuntimeLoad,
    "AWPV2PersistentBootstrap": AWPV2PersistentBootstrap,
    "AWPV2PersistentFirstTurn": AWPV2PersistentFirstTurn,
    "AWPV2PersistentContinuationTurn": AWPV2PersistentContinuationTurn,
    # P1: Real Continue (world-advance)
    "AWPV2ContinueTurnP1": AWPV2ContinueTurnP1,
    # Writer V2 (explicit C1 pipeline)
    "AWPV2WriterGenerate": AWPV2WriterGenerate,
    # Novel Mode
    "AWPV2NovelProjectCreate": AWPV2NovelProjectCreate,
    "AWPV2NovelVolumePlan": AWPV2NovelVolumePlan,
    "AWPV2NovelChapterPlan": AWPV2NovelChapterPlan,
    "AWPV2NovelChapterWrite": AWPV2NovelChapterWrite,
    "AWPV2NovelChapterRevise": AWPV2NovelChapterRevise,
    "AWPV2NovelLedgerView": AWPV2NovelLedgerView,
    "AWPV2NovelExport": AWPV2NovelExport,
    "AWPV2NovelBatchWrite": AWPV2NovelBatchWrite,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    # P1
    "AWPV2CardStateInit": "AWP V2 卡片状态初始化",
    "AWPV2RoundSnapshot": "AWP V2 回合快照",
    "AWPV2QualityGate": "AWP V2 质量门",
    "AWPV2CardStateCommit": "AWP V2 状态提交",
    "AWPV2TurnRecordCommit": "AWP V2 回合记录提交",
    "AWPV2RetryTurn": "AWP V2 重试回合",
    "AWPV2ContinueTurn": "AWP V2 继续回合",
    "AWPV2ExecutionTrace": "AWP V2 执行追踪",
    # P2
    "AWPV2Director": "AWP V2 叙事总控",
    "AWPV2DelegationPlan": "AWP V2 委派计划",
    "AWPV2DynamicSubAgentPool": "AWP V2 动态子Agent池",
    "AWPV2SuggestionMerge": "AWP V2 建议合并",
    "AWPV2WriterInputBundle": "AWP V2 Writer输入包",
    "AWPV2AgentTrace": "AWP V2 Agent追踪",
    # M1
    "AWPV2AcceptedTurnWindow": "AWP V2 已接受回合窗口",
    "AWPV2ActiveMemoryRecall": "AWP V2 活跃记忆召回",
    "AWPV2RagMemoryRecall": "AWP V2 RAG记忆召回",
    "AWPV2MemoryContextAssembler": "AWP V2 记忆上下文组装",
    "AWPV2MemoryCommitPlan": "AWP V2 记忆提交计划",
    "AWPV2ActiveMemoryCommit": "AWP V2 活跃记忆提交",
    "AWPV2RagMemoryCommit": "AWP V2 RAG记忆提交",
    "AWPV2MemoryDiagnostics": "AWP V2 记忆诊断",
    # C1
    "AWPV2DirectorPlan": "AWP V2 Director规划",
    "AWPV2ToolPlan": "AWP V2 工具计划",
    "AWPV2ToolGateway": "AWP V2 工具网关",
    "AWPV2EnrichmentMerge": "AWP V2 丰富合并",
    "AWPV2FinalTurnBrief": "AWP V2 最终回合简报",
    "AWPV2WriterV2": "AWP V2 写作节点V2",
    "AWPV2WriterInputBundleV2": "AWP V2 Writer输入包V2",
    "AWPV2QualityPipeline": "AWP V2 质量检查流水线",
    "AWPV2Reviser": "AWP V2 修订器",
    "AWPV2WriterOutput": "AWP V2 Writer输出",
    "AWPV2ToolTrace": "AWP V2 工具追踪",
    # D1: History/Recall
    "AWPV2HistoryRecallTrigger": "AWP V2 历史回查触发",
    "AWPV2HistoryRecallRequest": "AWP V2 历史回查请求",
    "AWPV2HistoryRecallAgent": "AWP V2 历史回查Agent",
    "AWPV2RecallEvidenceRanker": "AWP V2 回查证据排序",
    "AWPV2HistoryRecallResult": "AWP V2 历史回查结果",
    "AWPV2HistoryRecallDiagnostics": "AWP V2 历史回查诊断",
    # D2: Opportunity
    "AWPV2OpportunityTrigger": "AWP V2 戏剧机会触发",
    "AWPV2OpportunityRequest": "AWP V2 戏剧机会请求",
    "AWPV2OpportunityAgent": "AWP V2 戏剧机会Agent",
    "AWPV2OpportunityValidator": "AWP V2 戏剧机会验证",
    "AWPV2OpportunityRanker": "AWP V2 戏剧机会排序",
    "AWPV2OpportunityResult": "AWP V2 戏剧机会结果",
    "AWPV2OpportunityDiagnostics": "AWP V2 戏剧机会诊断",
    # D3: World-Life
    "AWPV2WorldLifeTrigger": "AWP V2 世界活性触发",
    "AWPV2WorldLifeRequest": "AWP V2 世界活性请求",
    "AWPV2WorldLifeAgent": "AWP V2 世界活性Agent",
    "AWPV2WorldLifeValidator": "AWP V2 世界活性验证",
    "AWPV2WorldLifeRanker": "AWP V2 世界活性排序",
    "AWPV2WorldLifeResult": "AWP V2 世界活性结果",
    "AWPV2WorldLifeDiagnostics": "AWP V2 世界活性诊断",
    # D4: Emotion/Relationship
    "AWPV2EmotionRelationshipTrigger": "AWP V2 情绪关系触发",
    "AWPV2EmotionRelationshipRequest": "AWP V2 情绪关系请求",
    "AWPV2EmotionRelationshipAgent": "AWP V2 情绪关系Agent",
    "AWPV2EmotionRelationshipValidator": "AWP V2 情绪关系验证",
    "AWPV2EmotionRelationshipRanker": "AWP V2 情绪关系排序",
    "AWPV2EmotionRelationshipResult": "AWP V2 情绪关系结果",
    "AWPV2EmotionRelationshipDiagnostics": "AWP V2 情绪关系诊断",
    # D5: Continuity
    "AWPV2ContinuityTrigger": "AWP V2 连续性触发",
    "AWPV2ContinuityRequest": "AWP V2 连续性请求",
    "AWPV2ContinuityAgent": "AWP V2 连续性Agent",
    "AWPV2ContinuityValidator": "AWP V2 连续性验证",
    "AWPV2ContinuityRanker": "AWP V2 连续性排序",
    "AWPV2ContinuityResult": "AWP V2 连续性结果",
    "AWPV2ContinuityDiagnostics": "AWP V2 连续性诊断",
    # D6: Memory Curation
    "AWPV2MemoryCurationTrigger": "AWP V2 记忆治理触发",
    "AWPV2MemoryCurationRequest": "AWP V2 记忆治理请求",
    "AWPV2MemoryCuratorAgent": "AWP V2 记忆治理Agent",
    "AWPV2MemoryCurationValidator": "AWP V2 记忆治理验证",
    "AWPV2MemoryCurationRanker": "AWP V2 记忆治理排序",
    "AWPV2MemoryCurationDiagnostics": "AWP V2 记忆治理诊断",
    "AWPV2MemoryCurationCommitPlan": "AWP V2 记忆治理提交计划",
    # P-CardImport
    "AWPV2CardSourceLoad": "AWP V2 角色卡源读取",
    "AWPV2CardPayloadParse": "AWP V2 角色卡结构解析",
    "AWPV2CardSecurityScan": "AWP V2 角色卡安全扫描",
    "AWPV2CardNormalize": "AWP V2 角色卡规范化",
    "AWPV2CardImportReview": "AWP V2 角色卡导入审核",
    "AWPV2CardImportApproval": "AWP V2 角色卡导入批准",
    "AWPV2CardDefinitionCommit": "AWP V2 角色卡定义提交",
    "AWPV2CardCatalogLookup": "AWP V2 角色卡目录查询",
    "AWPV2CardImportDiagnostics": "AWP V2 角色卡导入诊断",
    # P-CardSession Bootstrap
    "AWPV2CardSessionBootstrapRequest": "AWP V2 会话启动请求",
    "AWPV2CardDefinitionReadyValidator": "AWP V2 角色卡就绪验证",
    "AWPV2GreetingSelection": "AWP V2 开场白选择",
    "AWPV2CardStateInitializer": "AWP V2 卡状态初始化器",
    "AWPV2OpeningRecordCommit": "AWP V2 开场记录提交",
    "AWPV2WorldbookBindingBuilder": "AWP V2 世界书绑定构建",
    "AWPV2CardSessionBindingCommit": "AWP V2 会话绑定提交",
    "AWPV2CardSessionBootstrapDiagnostics": "AWP V2 会话启动诊断",
    "AWPV2CardImportAndBootstrap": "AWP V2 角色卡导入并启动",
    "AWPV2CardDefinitionFixtureLoad": "AWP V2 角色卡Fixture加载",
    # P-FirstTurn
    "AWPV2FirstTurnRequest": "AWP V2 首回合请求",
    "AWPV2SessionReadyValidator": "AWP V2 会话就绪校验",
    "AWPV2OpeningContextLoader": "AWP V2 开场上文加载",
    "AWPV2SessionBoundWorldbookRetriever": "AWP V2 会话绑定世界书检索",
    "AWPV2FirstTurnContextAssembler": "AWP V2 首回合上下文装配",
    "AWPV2FirstTurnReceipt": "AWP V2 首回合收据",
    "AWPV2FirstTurnDiagnostics": "AWP V2 首回合诊断",
    "AWPV2FirstTurnExecution": "AWP V2 首回合执行",
    # Observability
    "AWPV2TraceDisplay": "AWP V2 追踪显示",
    # P-Canonical
    "AWPV2PersistentTurnObserver": "AWP V2 Persistent Turn Observer",
    "AWPV2AcceptedTextOutput": "AWP V2 Accepted Text Output",
    "AWPV2TurnResultProbe": "AWP V2 Turn Result Probe",
    "AWPV2ContinuationTurnExecution": "AWP V2 Continuation Turn Execution",
    # P-Persistent
    "AWPV2SessionRuntimeLoad": "AWP V2 Session Runtime Load",
    "AWPV2PersistentBootstrap": "AWP V2 Persistent Bootstrap",
    "AWPV2PersistentFirstTurn": "AWP V2 Persistent First Turn",
    "AWPV2PersistentContinuationTurn": "AWP V2 Persistent Continuation Turn",
    # P1: Real Continue (world-advance)
    "AWPV2ContinueTurnP1": "AWP V2 Continue Turn (World Advance)",
    # Writer V2 (explicit C1 pipeline)
    "AWPV2WriterGenerate": "AWP V2 Writer 生成",
    # Novel Mode
    "AWPV2NovelProjectCreate": "AWP V2 小说项目创建",
    "AWPV2NovelVolumePlan": "AWP V2 小说卷计划",
    "AWPV2NovelChapterPlan": "AWP V2 小说章节规划",
    "AWPV2NovelChapterWrite": "AWP V2 小说章节写作",
    "AWPV2NovelChapterRevise": "AWP V2 小说章节修订",
    "AWPV2NovelLedgerView": "AWP V2 小说账本查看",
    "AWPV2NovelExport": "AWP V2 小说导出",
    "AWPV2NovelBatchWrite": "AWP V2 小说批量生成",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
