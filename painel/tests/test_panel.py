"""Testes do painel sem API, tokens ou dados de clientes reais."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PANEL_SESSION_SECRET", "local-apenas-para-testes")
os.environ.setdefault("PANEL_PASSWORD_HASH", "hash-so-para-testes")
import app as studio


class TestPainel(unittest.TestCase):
    def setUp(self):
        self.app = studio.app
        self.app.config["TESTING"] = True
        self.app.secret_key = "chave-unicamente-de-teste"
        self.client = self.app.test_client()
        self.posts = [
            {"id": "001", "title": "Contator", "hook": "O que e?",
             "body": "Comando", "caption": "Legenda sobre contator", "approved": False},
            {"id": "002", "title": "Disjuntor x fusivel", "hook": "Qual a diferenca?",
             "body": "Protecao", "caption": "Legenda de disjuntores", "approved": True},
        ]
        self.state = {
            "published": [{"id": "002", "local_date": "2026-11-11"}],
            "externally_scheduled": [{"id": "001", "date": "2026-11-12"}],
        }

    def authorize(self):
        with self.client.session_transaction() as session:
            session["admin"] = True
            session["csrf"] = "teste-csrf"

    def test_sem_login_redireciona(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.location)

    def test_tela_login(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'type="password"', response.data)

    def test_galeria_e_status(self):
        self.authorize()
        with patch.object(studio, "repo_json", side_effect=[self.posts, self.state]):
            response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Biblioteca de artes", response.data)
        self.assertIn(b"Disjuntor x fusivel", response.data)
        self.assertIn(b"Agendado na Meta", response.data)

    def test_detalhe_mostra_legenda_e_bloqueio_para_publicado(self):
        self.authorize()
        with patch.object(studio, "repo_json", side_effect=[self.posts, self.state]):
            response = self.client.get("/post/002")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Legenda de disjuntores", response.data)
        self.assertIn(b'class="status published"', response.data)

    def test_status_nao_pode_ser_editado_sem_csrf(self):
        self.authorize()
        response = self.client.post("/post/002/save", data={
            "caption": "Outra legenda", "decision": "approve", "csrf": "errado"
        })
        self.assertEqual(response.status_code, 400)

    def test_saude_geral(self):
        self.assertTrue(self.client.get("/health").json["ok"])


if __name__ == "__main__":
    unittest.main()
