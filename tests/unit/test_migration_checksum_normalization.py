from app.database.migrations import _migration_checksum


def test_migration_checksum_is_stable_across_crlf_and_lf():
    source = b"-- migration\nSELECT 1;\n"
    crlf_source = source.replace(b"\n", b"\r\n")
    assert _migration_checksum(source) == _migration_checksum(crlf_source)
