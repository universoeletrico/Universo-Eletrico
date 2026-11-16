"""Teste offline de rotas de imagem: nenhuma chamada real ao GitHub ou Meta."""
import io
import unittest
from unittest.mock import patch

from PIL import Image

from painel import app as studio


def png():
    buf = io.BytesIO()
    Image.new("RGB", (1080, 1350), "#143b62").save(buf, "PNG")
    buf.seek(0)
    return buf


class ImageRoutesTest(unittest.TestCase):
    def setUp(self):
        studio.app.config["TESTING"] = True
        studio.app.secret_key = "chave-de-teste-nao-prod"
        self.client = studio.app.test_client()
        self.guard = patch.object(studio, "configured", return_value=True)
        self.guard.start()
        self.addCleanup(self.guard.stop)

    def login(self):
        with self.client.session_transaction() as sess:
            sess["admin"] = True
            sess["csrf"] = "token-teste"

    def test_unauthorized_upload_redirects_login(self):
        response = self.client.post("/post/003/imagem/enviar",
                                    data={"csrf": "token-teste"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.location)

    def test_upload_saves_only_review_version(self):
        self.login()
        with patch.object(studio, "editable_post", return_value={"id": "003", "caption": "Legenda", "approved": True}), \\
             patch.object(studio, "save_to_github") as draft, \\
             patch.object(studio, "staged_image", return_value=None), \\
             patch.object(studio, "github_save_binary") as save:
            response = self.client.post("/post/003/imagem/enviar",
                                        data={"csrf": "token-teste", "image": (png(), "post.png")},
                                        content_type="multipart/form-data")
            self.assertEqual(response.status_code, 302)
            draft.assert_called_once_with("003", "Legenda", False)
            self.assertEqual(save.call_args.args[0], "docs/review/003.jpg")
            self.assertNotIn("docs/posts/", save.call_args.args[0])

    def test_discard_only_review_version(self):
        self.login()
        with patch.object(studio, "editable_post", return_value={"id": "003"}), \\
             patch.object(studio, "staged_image", return_value=(b"jpeg", "candidate-sha")), \\
             patch.object(studio, "github_delete_binary") as delete:
            response = self.client.post("/post/003/imagem/descartar", data={"csrf": "token-teste"})
            self.assertEqual(response.status_code, 302)
            delete.assert_called_once_with("docs/review/003.jpg", "candidate-sha")

    def test_approve_backups_and_keeps_draft(self):
        self.login()
        def original(path):
            return None if path.startswith("docs/backups/") else (b"old-jpeg", "older-sha")
        with patch.object(studio, "editable_post", return_value={"id": "003", "approved": True, "caption": "Texto"}), \\
             patch.object(studio, "staged_image", return_value=(b"new-jpeg", "new-sha")), \\
             patch.object(studio, "github_binary", side_effect=original), \\
             patch.object(studio, "save_to_github") as draft, \\
             patch.object(studio, "github_save_binary") as save, \\
             patch.object(studio, "github_delete_binary") as delete:
            response = self.client.post("/post/003/imagem/aprovar", data={"csrf": "token-teste"})
            self.assertEqual(response.status_code, 302)
            paths = [call.args[0] for call in save.call_args_list]
            self.assertEqual(paths[0], "docs/backups/003-older-sha.jpg")
            self.assertEqual(paths[1], "docs/posts/003.jpg")
            draft.assert_called_once_with("003", "Texto", False)
            delete.assert_called_once_with("docs/review/003.jpg", "new-sha")


if __name__ == "__main__":
    unittest.main()
