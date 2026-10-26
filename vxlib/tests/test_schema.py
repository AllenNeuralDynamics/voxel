import pytest
from vxlib.schema import check_identifier, duplicate_keys


def test_duplicate_keys_reports_each_shared_key_with_its_scopes_in_order():
    scopes = {
        "local": {"camera": 1, "stage": 2},
        "node:a": {"camera": 3, "laser": 4},
        "node:b": {"laser": 5, "camera": 6},
    }

    assert duplicate_keys(scopes) == {"camera": ["local", "node:a", "node:b"], "laser": ["node:a", "node:b"]}
    assert duplicate_keys({"a": {"x": 1}, "b": {"y": 2}}) == {}


def test_check_identifier_allows_only_letters_digits_underscore_and_hyphen():
    assert check_identifier("gfp_488-a", "Profile id") == "gfp_488-a"
    for value in ["gfp 488", "gfp.488", "gfp/rfp", "..", "gfp_é", ""]:
        with pytest.raises(ValueError, match="may use only letters, digits, '_' and '-'"):
            check_identifier(value, "Profile id")
