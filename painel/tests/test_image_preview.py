"""Prévia das artes do Studio: sem CDN e sem publicar nada."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PANEL_SESSION_SECRET", "apenas-teste-local")
os.environ.setdefault("PANEL_PASSWORD_HASH", "hash-ficticio")
import app as studio


class TestImagePreview(unittest.TestCase):
    def setUp(self):
        studio.app.config["TESTING"] = True
        studio.app.secret_key = "senha-apenas-teste"
        self.client = studio.app.test_client()

    def authorize(self):
        with self.client.session_transaction() as session:
            session["admin"] = True
            session["csrf"] = "csrf-teste"

    def test_preview_requires_login(self):
        response = self.client.get("/preview/004.jpg")
        self.assertEqual(response.status_code, 302)

    def test_preview_reads_current_file_and_prevents_cache(self):
        self.authorize()
        with patch.object(studio, "github_binary", return_value=(b"imagem-atual", "sha-exemplo")) as get:
            response = self.client.get("/preview/004.jpg")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, b"imagem-atual")
            self.assertEqual(response.mimetype, "image/jpeg")
            self.assertIn("no-store", response.headers["Cache-Control"])
            get.assert_called_once_with("docs/posts/004.jpg")

    def test_gallery_links_to_studio_preview(self):
        post = {"id": "004", "title": "CLP", "approved": False}
        with studio.app.test_request_context("/"), \
             patch.object(studio, "repo_json", side_effect=[[post], {"published": [], "externally_scheduled": []}]):
            rows = studio.posts_with_status()
        self.assertEqual(rows[0]["image_url"], "/preview/004.jpg")


if __name__ == "__main__":
    unittest.main()
