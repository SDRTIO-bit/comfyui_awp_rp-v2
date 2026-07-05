from awp_rp_runtime_v2.nodes.continue_turn_execution_node import _continue_seed


def test_continue_seed_is_stable_when_request_identity_is_provided():
    first = _continue_seed("sess1", request_id="req1", turn_id="", run_id="")
    second = _continue_seed("sess1", request_id="req1", turn_id="", run_id="")

    assert first == second


def test_continue_seed_is_unique_without_request_identity():
    first = _continue_seed("sess1", request_id="", turn_id="", run_id="", entropy="a")
    second = _continue_seed("sess1", request_id="", turn_id="", run_id="", entropy="b")

    assert first != second
