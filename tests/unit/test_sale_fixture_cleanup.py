import pytest

from sql.operations.cleanup_sale_test_fixture import _positive_ids, load_manifest


def test_cleanup_manifest_has_exact_reviewed_sale_fixture():
    from sql.operations.cleanup_sale_test_fixture import DEFAULT_MANIFEST

    manifest = load_manifest(DEFAULT_MANIFEST)

    assert manifest["database"] == "multiagentedb"
    assert manifest["tickets"] == [3, 4, 7, 8, 9, 10, 11, 12]
    assert manifest["children"]["payments"] == [2, 3, 5, 6]


def test_cleanup_manifest_id_validator_rejects_unreviewed_ticket_set():
    with pytest.raises(ValueError, match="exactamente 8"):
        _positive_ids([3, 4, 7, 8, 9, 10, 11, 999, 12], "tickets", expected_count=8)
