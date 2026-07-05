from __future__ import annotations

from awp_rp_runtime_v2.contracts.card_definition import (
    CardDefinition,
    CardDefinitionStatus,
)
from awp_rp_runtime_v2.contracts.card_session_binding import (
    CardSessionBinding,
    CardSessionBindingStatus,
)
from awp_rp_runtime_v2.contracts.card_session_bootstrap_receipt import (
    CardSessionBootstrapReceipt,
)
from awp_rp_runtime_v2.contracts.opening_record import OpeningRecord
from awp_rp_runtime_v2.contracts.turn_record import TurnRecord
from awp_rp_runtime_v2.contracts.worldbook_binding import WorldbookBinding


def make_card_definition(logical_card_id: str = "card-1") -> CardDefinition:
    return CardDefinition(
        logical_card_id=logical_card_id,
        card_version=1,
        source_id=f"src-{logical_card_id}",
        source_hash=f"hash-{logical_card_id}",
        name=f"Name {logical_card_id}",
        display_name=f"Display {logical_card_id}",
        status=CardDefinitionStatus.READY,
        greetings=[
            {
                "greeting_id": "g0",
                "label": "Default",
                "content": "Hello.",
                "safe_display_content": "Hello.",
                "content_hash": "hash-g0",
                "index": 0,
                "is_default": True,
            }
        ],
    )


def make_binding(
    session_id: str = "s1",
    logical_card_id: str = "card-1",
) -> CardSessionBinding:
    return CardSessionBinding(
        session_id=session_id,
        logical_card_id=logical_card_id,
        card_version=1,
        source_hash=f"hash-{logical_card_id}",
        card_definition_ref=f"{logical_card_id}:1",
        selected_greeting_id="g0",
        worldbook_binding_id=f"wb-{session_id}",
        opening_record_id=f"op-{session_id}",
        status=CardSessionBindingStatus.READY,
    )


def make_turn_record(
    session_id: str = "s1",
    card_id: str = "card-1",
    turn_id: str = "t1",
    turn_index: int = 1,
    player_input: str = "Hello",
    writer_output: str = "World",
) -> TurnRecord:
    return TurnRecord(
        turn_id=turn_id,
        trace_id=f"trace-{turn_id}",
        card_id=card_id,
        session_id=session_id,
        turn_index=turn_index,
        player_input=player_input,
        writer_output=writer_output,
    )


def make_opening_record(
    session_id: str = "s1",
    logical_card_id: str = "card-1",
    content: str = "Hello.",
) -> OpeningRecord:
    return OpeningRecord(
        opening_record_id=f"op-{session_id}",
        session_id=session_id,
        logical_card_id=logical_card_id,
        card_version=1,
        greeting_id="g0",
        safe_display_content=content,
    )


def make_worldbook_binding(
    session_id: str = "s1",
    logical_card_id: str = "card-1",
) -> WorldbookBinding:
    return WorldbookBinding(
        worldbook_binding_id=f"wb-{session_id}",
        session_id=session_id,
        logical_card_id=logical_card_id,
        card_version=1,
        source_hash=f"hash-{logical_card_id}",
    )


def make_bootstrap_receipt(
    session_id: str = "s1",
    logical_card_id: str = "card-1",
) -> CardSessionBootstrapReceipt:
    return CardSessionBootstrapReceipt(
        receipt_id=f"receipt-{session_id}",
        request_id=f"request-{session_id}",
        session_id=session_id,
        logical_card_id=logical_card_id,
        card_version=1,
        source_hash=f"hash-{logical_card_id}",
        greeting_id="g0",
        opening_record_id=f"op-{session_id}",
        worldbook_binding_id=f"wb-{session_id}",
        commit_status="committed",
    )
