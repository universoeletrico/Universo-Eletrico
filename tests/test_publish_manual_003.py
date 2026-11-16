"""Testes offline de reserva manual sem chamadas ao Instagram."""
import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo
from src import publish_manual_003 as manual


class TestReserveManual003(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "docs/posts").mkdir(parents=True)
        (self.root / "docs/posts/003.jpg").write_bytes(b"imagem")
        (self.root / "content").mkdir()
        self.posts = self.root / "content/posts.json"
        self.state = self.root / "content/state.json"
        self.posts.write_text(json.dumps([{"id": "003", "approved": True,
                                           "caption": "Legenda", "media_type": "IMAGE"}]))
        self.state.write_text(json.dumps({"not_before_date": "2026-11-13", "published": [],
                                          "externally_scheduled": []}))
        self.env = patch.dict(os.environ, {"MANUAL_POST_ID": "003", "PUBLISH_ENABLED": "true"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.patches = [
            patch.object(manual, "ROOT", self.root),
            patch.object(manual, "POSTS_FILE", self.posts),
            patch.object(manual, "STATE_FILE", self.state),
            patch.object(manual, "save_state", side_effect=lambda obj: self.state.write_text(json.dumps(obj)))
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        self.now = datetime(2026, 11, 15, 22, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))

    def test_reserve_exactly_003(self):
        manual.reserve_manual_003(self.now)
        state = json.loads(self.state.read_text())
        self.assertEqual(state["pending"]["id"], "003")
        self.assertEqual(state["published"], [])

    def test_duplicate_pending_blocks(self):
        state = json.loads(self.state.read_text())
        state["pending"] = {"id": "004"}
        self.state.write_text(json.dumps(state))
        with self.assertRaises(RuntimeError):
            manual.reserve_manual_003(self.now)

    def test_duplicate_published_blocks(self):
        state = json.loads(self.state.read_text())
        state["published"] = [{"id": "003", "local_date": "2026-11-14"}]
        self.state.write_text(json.dumps(state))
        with self.assertRaises(RuntimeError):
            manual.reserve_manual_003(self.now)

    def test_unapproved_blocks(self):
        self.posts.write_text(json.dumps([{"id": "003", "approved": False, "caption": "Texto"}]))
        with self.assertRaises(RuntimeError):
            manual.reserve_manual_003(self.now)


if __name__ == "__main__":
    unittest.main()
