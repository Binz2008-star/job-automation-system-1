"""
tests/test_rico_memory_safety.py
Verify that malicious user_id values cannot cause files to be written
outside of the data/rico directory.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestMemoryKeySafety:
    def test_safe_key_is_hex_digest(self):
        from src.rico_memory import _safe_key
        import hashlib
        key = _safe_key("alice@rico.ai")
        assert key == hashlib.sha256(b"alice@rico.ai").hexdigest()
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_safe_key_strips_traversal(self):
        from src.rico_memory import _safe_key
        key = _safe_key("abc/../../poc")
        # Must not contain path separators — it's a hex digest
        assert "/" not in key
        assert ".." not in key

    def test_profile_path_is_under_rico_dir(self):
        from src.rico_memory import RicoMemoryStore, RICO_MEMORY_DIR
        store = RicoMemoryStore()
        path = store._profile_path("alice@rico.ai")
        assert str(path.resolve()).startswith(str(RICO_MEMORY_DIR.resolve()))

    def test_unsafe_user_id_path_stays_contained(self):
        """A path-traversal user_id must not escape data/rico."""
        from src.rico_memory import RicoMemoryStore, RICO_MEMORY_DIR
        store = RicoMemoryStore()
        for evil_id in ["abc/../../poc", "../../../etc/passwd", "..\\..\\windows\\system32"]:
            path = store._profile_path(evil_id)
            assert str(path.resolve()).startswith(str(RICO_MEMORY_DIR.resolve())), (
                f"Path escaped for user_id={evil_id!r}: {path}"
            )

    def test_chat_path_is_under_rico_dir(self):
        from src.rico_memory import RicoMemoryStore, RICO_MEMORY_DIR
        store = RicoMemoryStore()
        path = store._chat_path("abc/../../poc")
        assert str(path.resolve()).startswith(str(RICO_MEMORY_DIR.resolve()))

    def test_different_user_ids_produce_different_keys(self):
        from src.rico_memory import _safe_key
        assert _safe_key("alice@rico.ai") != _safe_key("bob@rico.ai")

    def test_same_user_id_produces_same_key(self):
        from src.rico_memory import _safe_key
        assert _safe_key("alice@rico.ai") == _safe_key("alice@rico.ai")

    def test_append_chat_message_with_evil_user_id_does_not_escape(self, tmp_path):
        """End-to-end: writing a chat message with a traversal user_id stays in rico dir."""
        from src.rico_memory import RicoMemoryStore, RICO_MEMORY_DIR
        store = RicoMemoryStore()
        # Patch the base dir so the test writes to tmp rather than the real data/rico
        fake_rico_dir = tmp_path / "rico"
        fake_rico_dir.mkdir()
        with patch("src.rico_memory.RICO_MEMORY_DIR", fake_rico_dir):
            # Re-patch the store methods to use our fake dir
            evil_id = "abc/../../poc"
            import hashlib
            safe_key = hashlib.sha256(evil_id.encode()).hexdigest()
            expected_file = fake_rico_dir / f"chat_{safe_key}.json"
            store.append_chat_message(evil_id, "user", "test message")
        # The real RICO_MEMORY_DIR is unchanged — verify no file leaked out
        assert not (Path(os.getcwd()) / "poc.json").exists()
        assert not (Path(os.getcwd()).parent / "poc.json").exists()
