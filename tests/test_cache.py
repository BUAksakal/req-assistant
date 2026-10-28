from reqlens.cache import fingerprint, lookup, store


def test_lookup_returns_what_was_stored(tmp_path):
    db = tmp_path / "test.db"
    assert lookup("conflict:abc:AEB-001", db) is None

    store("conflict:abc:AEB-001", "no conflict", db)
    assert lookup("conflict:abc:AEB-001", db) == "no conflict"


def test_fingerprint_changes_when_the_document_changes():
    assert fingerprint("AEB-001|10 km/h") == fingerprint("AEB-001|10 km/h")
    assert fingerprint("AEB-001|10 km/h") != fingerprint("AEB-001|15 km/h")
