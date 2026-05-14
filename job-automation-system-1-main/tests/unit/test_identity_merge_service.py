"""tests/unit/test_identity_merge_service.py

Unit tests for pure profile merge logic (no DB required).
"""
import pytest

from src.services.identity_merge_service import (
    is_empty_value,
    merge_profile_data,
    normalize_jsonb,
)


class TestIsEmptyValue:
    def test_none_is_empty(self):
        assert is_empty_value(None) is True

    def test_empty_string_is_empty(self):
        assert is_empty_value("") is True

    def test_empty_list_is_empty(self):
        assert is_empty_value([]) is True

    def test_empty_dict_is_empty(self):
        assert is_empty_value({}) is True

    def test_zero_is_not_empty(self):
        assert is_empty_value(0) is False

    def test_false_is_not_empty(self):
        assert is_empty_value(False) is False

    def test_populated_list_is_not_empty(self):
        assert is_empty_value(["a"]) is False


class TestNormalizeJsonb:
    def test_none_returns_empty_dict(self):
        assert normalize_jsonb(None) == {}

    def test_dict_preserved(self):
        assert normalize_jsonb({"a": 1}) == {"a": 1}

    def test_json_string_parsed(self):
        assert normalize_jsonb('{"a": 1}') == {"a": 1}

    def test_bad_json_returns_empty(self):
        assert normalize_jsonb("not json") == {}

    def test_list_json_returns_empty(self):
        # lists are not dicts → empty
        assert normalize_jsonb("[1, 2]") == {}

    def test_int_returns_empty(self):
        assert normalize_jsonb(42) == {}


class TestMergeProfileData:
    def test_auth_wins_scalar(self):
        auth = {"years_experience": 12.0}
        guest = {"years_experience": 10.0}
        result = merge_profile_data(auth, guest)
        assert result["years_experience"] == 12.0

    def test_fills_missing_auth_value(self):
        auth = {}
        guest = {"preferred_cities": ["Dubai"]}
        result = merge_profile_data(auth, guest)
        assert result["preferred_cities"] == ["Dubai"]

    def test_merges_lists_with_dedupe(self):
        auth = {"skills": ["audit", "compliance"]}
        guest = {"skills": ["hse", "audit"]}
        result = merge_profile_data(auth, guest)
        assert result["skills"] == ["audit", "compliance", "hse"]

    def test_ignores_empty_guest_values(self):
        auth = {"skills": ["python"]}
        guest = {"skills": []}
        result = merge_profile_data(auth, guest)
        assert result["skills"] == ["python"]

    def test_ignores_non_mergeable_keys(self):
        auth = {}
        guest = {"raw_cv_text": "secret", "debug_mode": True}
        result = merge_profile_data(auth, guest)
        assert "raw_cv_text" not in result
        assert "debug_mode" not in result

    def test_auth_empty_list_filled_by_guest(self):
        auth = {"skills": []}
        guest = {"skills": ["python"]}
        result = merge_profile_data(auth, guest)
        assert result["skills"] == ["python"]

    def test_case_insensitive_list_dedupe(self):
        auth = {"skills": ["Python", "SQL"]}
        guest = {"skills": ["python", "java"]}
        result = merge_profile_data(auth, guest)
        assert result["skills"] == ["Python", "SQL", "java"]

    def test_does_not_mutate_inputs(self):
        auth = {"skills": ["a"]}
        guest = {"skills": ["b"]}
        result = merge_profile_data(auth, guest)
        assert auth == {"skills": ["a"]}
        assert guest == {"skills": ["b"]}
        assert result == {"skills": ["a", "b"]}

    def test_preserves_unrelated_auth_keys(self):
        auth = {"name": "Robin", "skills": ["a"]}
        guest = {"skills": ["b"]}
        result = merge_profile_data(auth, guest)
        assert result["name"] == "Robin"
        assert result["skills"] == ["a", "b"]
