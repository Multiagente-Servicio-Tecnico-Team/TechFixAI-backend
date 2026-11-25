"""Pure ticket preparation; no engine, external service or commercial writes."""
from copy import deepcopy
import inspect

import pytest

from app.agents.decentralized.state import invalidate_request
from app.agents.decentralized.ticket_operations import (
    generate_ticket_code, prepare_pending_ticket_operation as prepare,
    validate_pending_ticket_operation as validate,
)
from app.database.decentralized_repository import DecentralizedRepository, RetryConflict


def operation(state=None, **changes):
    kwargs = dict(authenticated_customer_id=1, intent="REPAIR", title=" Laptop ",
                  failure_description=" No enciende ", code="TCK-TEST")
    return prepare(state if state is not None else {"customer_id": 1, "request_revision": 0},
                   **{**kwargs, **changes})


@pytest.mark.parametrize("intent", ["REPAIR", "SUPPORT", "SALE", "PC_BUILD", "WARRANTY_CLAIM"])
def test_payload_matches_repository_signature_and_no_confirmation(intent):
    patch = operation(intent=intent)
    payload = patch["pending_ticket_operation"]["payload"]
    assert set(payload) == set(inspect.signature(DecentralizedRepository.create_ticket).parameters) - {"self"}
    assert payload["request_type"] == intent
    assert payload["title"] == "Laptop" and payload["failure_description"] == "No enciende"
    assert set(patch) == {"pending_ticket_operation"}


def test_retry_is_identical_detached_and_does_not_mutate_state():
    state = {"customer_id": 1, "request_revision": 0, **operation()}
    before = deepcopy(state)
    patch = operation(state, code=None)
    assert patch == operation()
    patch["pending_ticket_operation"]["payload"]["title"] = "changed"
    assert state == before


@pytest.mark.parametrize("changes", [dict(title="Otro"), dict(failure_description="Otro"),
                                     dict(intent="SALE"), dict(code="NEW"), dict(authenticated_customer_id=2)])
def test_conflict_never_replaces_operation(changes):
    state = {"customer_id": 1, "request_revision": 0, **operation()}
    with pytest.raises(RetryConflict):
        operation(state, **changes)


@pytest.mark.parametrize("changes", [dict(title=" "), dict(title="x" * 201),
    dict(failure_description=""), dict(code="x" * 21), dict(code=None),
    dict(authenticated_customer_id=True), dict(authenticated_customer_id=0),
    dict(authenticated_customer_id=2**63), dict(intent="UNKNOWN")])
def test_invalid_data(changes):
    with pytest.raises(ValueError):
        operation(**changes)


@pytest.mark.parametrize("revision", [None, True, -1, "0"])
def test_invalid_revision(revision):
    with pytest.raises(ValueError):
        operation({"request_revision": revision})


@pytest.mark.parametrize("intent", ["INFO_QUERY", "WARRANTY_STATUS_CHECK", "REFUND"])
def test_nonpersistent_intents_do_not_prepare_or_discard(intent):
    assert operation(intent=intent) == {}
    with pytest.raises(RetryConflict):
        operation({"request_revision": 0, **operation()}, intent=intent)


@pytest.mark.parametrize("field,value", [("ticket_id", 1), ("ticket_code", "TCK-SAVED"), ("ticket_status", "NEW")])
def test_confirmed_ticket_not_recreated(field, value):
    with pytest.raises(RetryConflict):
        operation({"request_revision": 0, field: value})


def test_stale_revision_and_request_invalidation_are_explicit_conflicts():
    state = {"request_revision": 1, **operation()}
    with pytest.raises(RetryConflict):
        operation(state)
    for new_request in (False, True):
        with pytest.raises(RetryConflict):
            invalidate_request(state, new_request=new_request)


@pytest.mark.parametrize("damage", ["extra", "missing", "spaces", "bool_customer", "sql_intent"])
def test_stored_operation_validation(damage):
    pending = operation()["pending_ticket_operation"]
    if damage == "extra":
        pending["payload"]["status"] = "NEW"
    elif damage == "missing":
        del pending["payload"]["title"]
    elif damage == "spaces":
        pending["payload"]["title"] = " Laptop "
    elif damage == "bool_customer":
        pending["payload"]["customer_id"] = True
    else:
        pending["payload"]["request_type"] = "REFUND"
    with pytest.raises(ValueError):
        validate(pending, authenticated_customer_id=1, request_revision=0)


def test_code_generation_and_independent_requests():
    codes = [generate_ticket_code() for _ in range(10)]
    assert all(len(code) == 20 and code.startswith("TCK-") for code in codes)
    assert len(set(codes)) == len(codes)
    assert operation(code=codes[0]) != operation(code=codes[1])
