"""Garante que aprovações usam o arquivo atualizado do GitHub, não o CDN."""
import base64
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("PANEL_SESSION_SECRET", "teste")
os.environ.setdefault("PANEL_PASSWORD_HASH", "teste")
import app as studio


class TestCurrentRepoStatus(unittest.TestCase):
    def setUp(self):
        studio.invalidate("content/posts.json")

    def test_reads_current_approved_values_from_github_api(self):
        posts = [{"id": "004", "approved": True}, {"id": "005", "approved": True}]
        response = Mock()
        response.json.return_value = {
            "content": base64.b64encode(json.dumps(posts).encode("utf-8")).decode("ascii")
        }
        response.raise_for_status.return_value = None
        with patch.object(studio.requests, "get", return_value=response) as get:
            result = studio.repo_json("content/posts.json")
        self.assertEqual(result, posts)
        self.assertIn("/contents/content/posts.json", get.call_args.args[0])
        self.assertEqual(get.call_args.kwargs.get("params"), {"ref": "main"})


if __name__ == "__main__":
    unittest.main()
