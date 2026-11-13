"""Campanhas comerciais e fila intercalada, sem chamadas reais externas."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PANEL = Path(__file__).resolve().parents[1]
PROJECT = PANEL.parent
sys.path[:0] = [str(PANEL), str(PROJECT)]
os.environ.setdefault("PANEL_SESSION_SECRET", "somente-testes")
os.environ.setdefault("PANEL_PASSWORD_HASH", "somente-testes")

import app as studio
from src import publish_daily as pub


class TestCampaigns(unittest.TestCase):
    def setUp(self):
        studio.app.config["TESTING"] = True
        studio.app.secret_key = "chave-de-testes"
        self.client = studio.app.test_client()
        self.row = {
            "id": "C001",
            "name": "Contator HS Automação 12A 220V",
            "category": "Componentes elétricos",
            "description": "Para aprender sobre comandos.",
            "caption": "Uma indicação de automação. #Publicidade #LinkDeAfiliado",
            "status": "waiting_link",
            "affiliate_url": "",
            "sales_signal": "+5 mil vendidos exibidos",
            "source_url": "https://lista.mercadolivre.com.br/contator",
        }

    def authorize(self):
        with self.client.session_transaction() as s:
            s["admin"] = True
            s["csrf"] = "csrf-teste"

    def test_campanhas_exigem_login(self):
        r = self.client.get("/campanhas")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.location)

    def test_campanhas_esperam_link(self):
        self.authorize()
        with patch.object(studio, "repo_json", side_effect=[
            {"campaigns": [dict(self.row)]}, {"published": []}
        ]), patch.dict(os.environ, {"GITHUB_WRITE_TOKEN": "somente-teste"}):
            r = self.client.get("/campanhas")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Campanhas prontas", r.data)
        self.assertIn(b"Colocar na fila de postagens", r.data)
        self.assertIn(b"C001.jpg", r.data)
        self.assertIn(b"Aguardando seu link", r.data)

    def test_colar_link_e_autorizar_ativa_campanha(self):
        self.authorize()
        observed = []
        def save(change):
            rows = [dict(self.row)]
            value = change(rows)
            observed.extend(rows)
            return value
        with patch.object(studio, "save_commercial_change", side_effect=save) as fn:
            r = self.client.post("/campanhas/C001/ativar", data={
                "csrf": "csrf-teste", "affiliate_url": "https://meli.la/xyz123"
            })
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.location, "/campanhas")
        fn.assert_called_once()
        self.assertEqual(observed[0]["status"], "queued")
        self.assertEqual(observed[0]["affiliate_url"], "https://meli.la/xyz123")
        self.assertIn("approved_at", observed[0])

    def test_nao_ativa_sem_link_ou_com_dominio_falso(self):
        self.authorize()
        with patch.object(studio, "save_commercial_change") as fn:
            self.client.post("/campanhas/C001/ativar", data={
                "csrf": "csrf-teste", "affiliate_url": ""
            })
            self.client.post("/campanhas/C001/ativar", data={
                "csrf": "csrf-teste", "affiliate_url": "https://sitefalso.com/produto"
            })
            self.client.post("/campanhas/C001/ativar", data={
                "csrf": "csrf-teste", "affiliate_url": "https://meli.la@exemplo.org/abc"
            })
        fn.assert_not_called()

    def test_csrf_e_id_protegidos(self):
        self.authorize()
        r = self.client.post("/campanhas/C001/ativar", data={
            "csrf": "errado", "affiliate_url": "https://meli.la/xyz123"
        })
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/campanhas/../ativar", data={
            "csrf": "csrf-teste", "affiliate_url": "https://meli.la/xyz123"
        })
        self.assertIn(r.status_code, (404, 405))

    def test_nao_reativa_campanha_ja_na_fila(self):
        self.authorize()
        row = {**self.row, "status": "queued",
               "affiliate_url": "https://meli.la/xyz123"}
        def save(change):
            return change([row])
        with patch.object(studio, "save_commercial_change", side_effect=save):
            r = self.client.post("/campanhas/C001/ativar", data={
                "csrf": "csrf-teste", "affiliate_url": "https://meli.la/outro123"
            })
        self.assertEqual(r.status_code, 302)
        self.assertEqual(row["affiliate_url"], "https://meli.la/xyz123")

    def test_vitrine_mostra_apenas_links_liberados(self):
        waiting = dict(self.row)
        queued = {**self.row, "id": "C002", "name": "Relé Temporizador COEL",
                  "status": "queued", "affiliate_url": "https://meli.la/coel123"}
        with patch.object(studio, "repo_json", side_effect=[
            {"products": []}, {"campaigns": [waiting, queued]}
        ]):
            r = self.client.get("/vitrine")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Rel", r.data)
        self.assertIn(b"https://meli.la/coel123", r.data)
        self.assertNotIn(b"Contator HS", r.data)

    def test_pausa_bloqueada_se_post_ja_reservado(self):
        self.authorize()
        with patch.object(studio, "github_file", return_value=(
            {"published": [], "pending": {"id": "C001"}}, "sha-teste"
        )), patch.object(studio, "save_commercial_change") as save:
            r = self.client.post("/campanhas/C001/pausar",
                                 data={"csrf": "csrf-teste"})
        self.assertEqual(r.status_code, 302)
        save.assert_not_called()


class TestCommercialPublisher(unittest.TestCase):
    def test_alterna_educacional_e_venda(self):
        posts = [
            {"id": "003", "kind": "educational", "approved": True},
            {"id": "004", "approved": True},
            {"id": "C001", "kind": "commercial", "approved": True},
            {"id": "C002", "kind": "commercial", "approved": True}
        ]
        state = {"published": []}
        p, _ = pub.select_next(posts, state, "2026-11-14")
        self.assertEqual(p["id"], "003")
        state["published"] = [{"id": "003", "local_date": "2026-11-13"}]
        p, _ = pub.select_next(posts, state, "2026-11-14")
        self.assertEqual(p["id"], "C001")
        state["published"].append({"id": "C001", "local_date": "2026-11-13"})
        p, _ = pub.select_next(posts, state, "2026-11-14")
        self.assertEqual(p["id"], "004")

    def test_sem_campanha_aprovada_permanece_educativo(self):
        posts = [{"id": "001", "approved": True}, {"id": "C001", "kind": "commercial",
                                                    "approved": False}]
        p, _ = pub.select_next(posts, {"published": []}, "2026-11-14")
        self.assertEqual(p["id"], "001")

    def test_sem_link_nao_entra_na_fila_do_robo(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "docs" / "posts").mkdir(parents=True)
            (root / "docs" / "posts" / "C001.jpg").write_bytes(b"teste")
            path = root / "commercial_campaigns.json"
            data = {"campaigns": [
                {"id": "C001", "status": "waiting_link", "affiliate_url": "",
                 "name": "Contator", "hook": "Produto", "body": "Detalhes",
                 "caption": "#Publicidade"}
            ]}
            path.write_text(json.dumps(data), encoding="utf-8")
            with patch.object(pub, "ROOT", root), \
                 patch.object(pub, "CAMPAIGNS_FILE", path):
                self.assertEqual(pub.ready_commercial_posts(), [])
                data["campaigns"][0]["status"] = "queued"
                path.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaises(ValueError):
                    pub.ready_commercial_posts()
                data["campaigns"][0]["affiliate_url"] = "https://meli.la/xyz123"
                path.write_text(json.dumps(data), encoding="utf-8")
                posts = pub.ready_commercial_posts()
                self.assertEqual(len(posts), 1)
                self.assertTrue(posts[0]["approved"])
                (root / "docs" / "posts" / "C001.jpg").unlink()
                self.assertEqual(pub.ready_commercial_posts(), [])


if __name__ == "__main__":
    unittest.main()
