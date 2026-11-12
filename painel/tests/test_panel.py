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

    def test_agenda_exibe_dias_e_horarios(self):
        self.authorize()
        cfg = {"timezone": "America/Sao_Paulo", "enabled": True,
               "days": [0, 2, 4], "times": ["12:17", "19:17"]}
        with patch.object(studio, "repo_json", return_value=cfg):
            response = self.client.get("/agenda")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Program", response.data)
        self.assertIn(b"19:17", response.data)

    def test_agenda_pode_salvar_sem_token_em_modo_simulado(self):
        self.authorize()
        with patch.object(studio, "save_schedule_to_github") as salvar:
            response = self.client.post("/agenda", data={
                "csrf": "teste-csrf",
                "enabled": "on", "days": ["0", "2", "4"],
                "quantidade": "2", "time1": "12:17", "time2": "19:17"
            })
        self.assertEqual(response.status_code, 302)
        salvar.assert_called_once()
        cfg = salvar.call_args.args[0]
        self.assertEqual(cfg["days"], [0, 2, 4])
        self.assertEqual(cfg["times"], ["12:17", "19:17"])

    def test_agenda_rejeita_horarios_iguais(self):
        self.authorize()
        with patch.object(studio, "save_schedule_to_github") as salvar:
            response = self.client.post("/agenda", data={
                "csrf": "teste-csrf", "enabled": "on", "days": ["0"],
                "quantidade": "2", "time1": "19:17", "time2": "19:17"
            })
        self.assertEqual(response.status_code, 302)
        salvar.assert_not_called()

    def test_saude_geral(self):
        self.assertTrue(self.client.get("/health").json["ok"])


if __name__ == "__main__":
    unittest.main()
