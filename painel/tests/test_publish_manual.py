"""Teste do botão de publicação manual: nenhum teste chama Meta ou Actions reais."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("PANEL_SESSION_SECRET", "teste")
os.environ.setdefault("PANEL_PASSWORD_HASH", "teste")
import app as studio


class TestManualPublishButton(unittest.TestCase):
    def setUp(self):
        studio.app.config["TESTING"] = True
        studio.app.secret_key = "apenas-testes"
        self.client = studio.app.test_client()
        with self.client.session_transaction() as session:
            session["admin"] = True
            session["csrf"] = "csrf-valido"

    def test_cannot_publish_without_explicit_confirmation(self):
        with patch.object(studio.requests, "post") as send:
            response = self.client.post("/post/003/publicar-agora",
                                        data={"csrf": "csrf-valido", "confirmacao": "SIM"})
            self.assertEqual(response.status_code, 302)
            send.assert_not_called()

    def test_only_post_003_has_manual_endpoint(self):
        response = self.client.post("/post/004/publicar-agora",
                                    data={"csrf": "csrf-valido", "confirmacao": "PUBLICAR-003"})
        self.assertEqual(response.status_code, 404)

    def test_csrf_blocks_manual_publish(self):
        with patch.object(studio.requests, "post") as send:
            response = self.client.post("/post/003/publicar-agora",
                                        data={"csrf": "errado", "confirmacao": "PUBLICAR-003"})
            self.assertEqual(response.status_code, 400)
            send.assert_not_called()

    def test_approved_post_dispatches_only_after_confirmation(self):
        response = Mock(status_code=204)
        response.raise_for_status.return_value = None
        with patch.object(studio, "editable_post", return_value={"id": "003", "approved": True, "caption": "Texto"}), \
             patch.object(studio, "staged_image", return_value=None), \
             patch.object(studio, "github_file", return_value=({"published": [], "externally_scheduled": []}, "sha")), \
             patch.object(studio, "github_headers", return_value={}), \
             patch.object(studio.requests, "post", return_value=response) as send:
            result = self.client.post("/post/003/publicar-agora",
                                      data={"csrf": "csrf-valido", "confirmacao": "PUBLICAR-003"})
            self.assertEqual(result.status_code, 302)
            self.assertEqual(send.call_count, 1)
            self.assertIn("/actions/workflows/publicar_003_painel.yml/dispatches", send.call_args.args[0])
            self.assertEqual(send.call_args.kwargs["json"]["inputs"]["confirmacao"], "PUBLICAR-003")

    def test_published_post_is_blocked(self):
        with patch.object(studio, "editable_post", side_effect=ValueError("Publicado")), \
             patch.object(studio.requests, "post") as send:
            result = self.client.post("/post/003/publicar-agora",
                                      data={"csrf": "csrf-valido", "confirmacao": "PUBLICAR-003"})
            self.assertEqual(result.status_code, 302)
            send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
