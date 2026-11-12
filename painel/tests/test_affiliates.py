"""Testes da Central de Afiliados: sem chamadas reais a marketplaces ou GitHub."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PANEL_SESSION_SECRET", "segredo-unicamente-para-teste")
os.environ.setdefault("PANEL_PASSWORD_HASH", "hash-de-teste")

import app as studio
from affiliates import draft_caption, new_id, normalize_product, require_disclosure, validate_affiliate_url


class TestAffiliates(unittest.TestCase):
    def setUp(self):
        studio.app.config["TESTING"] = True
        studio.app.secret_key = "chave-de-teste"
        self.client = studio.app.test_client()
        self.product = {
            "id": "A001",
            "name": "Kit Uno Para Arduino Iniciante Premium Com Material Didático Completo",
            "marketplace": "mercadolivre",
            "category": "Arduino e eletrônica",
            "affiliate_url": "https://meli.la/2jbidad",
            "description": "Confira as informações do anúncio antes de comprar.",
            "caption": "Veja este kit para estudar Arduino. #Publicidade #LinkDeAfiliado",
            "status": "draft",
            "created_at": "2026-11-12",
            "updated_at": "2026-11-12",
        }

    def authorize(self):
        with self.client.session_transaction() as sess:
            sess["admin"] = True
            sess["csrf"] = "csrf-valido"

    def test_nao_acessa_catalogo_sem_login(self):
        self.assertIn("/login", self.client.get("/afiliados").location)

    def test_catalogo_mostra_produto_inicial(self):
        self.authorize()
        with patch.object(studio, "repo_json", return_value={"products": [self.product]}):
            response = self.client.get("/afiliados")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Kit Uno Para Arduino", response.data)

    def test_detalhe_mostra_legenda_e_link(self):
        self.authorize()
        with patch.object(studio, "repo_json", return_value={"products": [self.product]}):
            response = self.client.get("/afiliados/A001")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"meli.la/2jbidad", response.data)
        self.assertIn(b"Salvar", response.data)

    def test_vitrine_nao_expoe_produto_sem_aprovacao(self):
        with patch.object(studio, "repo_json", return_value={"products": [self.product]}):
            response = self.client.get("/vitrine")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Novas indica", response.data)
        self.assertNotIn(b"meli.la/2jbidad", response.data)

    def test_vitrine_mostra_somente_aprovados(self):
        approved = {**self.product, "status": "approved"}
        with patch.object(studio, "repo_json", return_value={
            "products": [approved, {**self.product, "id": "A002", "status": "rejected",
                                    "affiliate_url": "https://meli.la/naopublicar"}]
        }):
            response = self.client.get("/vitrine")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"meli.la/2jbidad", response.data)
        self.assertNotIn(b"meli.la/naopublicar", response.data)
        self.assertIn(b"Publicidade", response.data)

    def test_link_apenas_https_e_dominio_correto(self):
        self.assertEqual(validate_affiliate_url("https://meli.la/2jbidad", "mercadolivre"),
                         "https://meli.la/2jbidad")
        for bad in ["http://meli.la/2jbidad", "https://evil.com", "https://meli.la.evil.com/foo",
                    "https://meli.la@evil.com/abc", "https://127.0.0.1/foo"]:
            with self.assertRaises(ValueError, msg=bad):
                validate_affiliate_url(bad, "mercadolivre")
        with self.assertRaises(ValueError):
            validate_affiliate_url("https://meli.la/2jbidad", "amazon")

    def test_multiplo_marketplace(self):
        choices = {
            "mercadolivre": "https://www.mercadolivre.com.br/item",
            "shopee": "https://shopee.com.br/item",
            "amazon": "https://amzn.to/exemplo",
            "tiktok": "https://www.tiktok.com/shop",
        }
        for market, link in choices.items():
            self.assertEqual(validate_affiliate_url(link, market), link)

    def test_legenda_publicitaria_necessaria(self):
        with self.assertRaises(ValueError):
            require_disclosure("Uma recomendação sem identificação")
        require_disclosure("Confira o produto. #Publicidade")
        self.assertIn("#Publicidade", draft_caption("Livro Técnico Completo", "Livros e cursos"))

    def test_id_criado_sem_repetir(self):
        self.assertEqual(new_id([{"id": "A001"}, {"id": "A002"}]), "A003")

    def test_cadastro_usa_rascunho(self):
        self.authorize()
        with patch.object(studio, "save_affiliate_change", return_value="A002") as save:
            response = self.client.post("/afiliados", data={
                "csrf": "csrf-valido", "name": "Livro sobre Automação Industrial",
                "marketplace": "amazon", "category": "Livros e cursos",
                "affiliate_url": "https://amzn.to/exemplo", "description": "Conferir o anúncio"
            })
        self.assertEqual(response.status_code, 302)
        self.assertIn("/afiliados/A002", response.location)
        save.assert_called_once()

    def test_cadastro_rejeita_link_de_outro_site(self):
        self.authorize()
        with patch.object(studio, "save_affiliate_change") as save:
            response = self.client.post("/afiliados", data={
                "csrf": "csrf-valido", "name": "Livro de automação",
                "marketplace": "mercadolivre", "category": "Livros e cursos",
                "affiliate_url": "https://site-malicioso.com/abc", "description": ""
            })
        self.assertEqual(response.status_code, 302)
        save.assert_not_called()

    def test_nao_permita_aprovar_sem_confirmar(self):
        self.authorize()
        with patch.object(studio, "save_affiliate_change") as save:
            response = self.client.post("/afiliados/A001", data={
                "csrf": "csrf-valido", "action": "approve"
            })
        self.assertEqual(response.status_code, 302)
        save.assert_not_called()

    def test_csrf_protege_cadastro(self):
        self.authorize()
        response = self.client.post("/afiliados", data={
            "csrf": "errado", "name": "Livro Técnico",
            "marketplace": "amazon", "affiliate_url": "https://amzn.to/teste",
        })
        self.assertEqual(response.status_code, 400)

    def test_salvar_alteracoes_reabre_revisao(self):
        self.authorize()
        approved = {**self.product, "status": "approved"}
        def fake_change(fn):
            result = fn([approved])
            self.assertEqual(approved["status"], "draft")
            return result
        with patch.object(studio, "save_affiliate_change", side_effect=fake_change):
            response = self.client.post("/afiliados/A001", data={
                "csrf": "csrf-valido", "action": "save",
                "name": approved["name"], "marketplace": approved["marketplace"],
                "category": approved["category"], "affiliate_url": approved["affiliate_url"],
                "description": approved["description"], "caption": approved["caption"]
            })
        self.assertEqual(response.status_code, 302)

    def test_aprovar_muda_apenas_status_nao_publica(self):
        self.authorize()
        record = dict(self.product)
        def fake_change(fn):
            value = fn([record])
            self.assertEqual(record["status"], "approved")
            return value
        with patch.object(studio, "save_affiliate_change", side_effect=fake_change):
            response = self.client.post("/afiliados/A001", data={
                "csrf": "csrf-valido", "action": "approve", "reviewed": "yes"
            })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(record["status"], "approved")

    def test_salvar_faz_um_commit_com_sha(self):
        fake_catalog = {"version": 1, "products": [dict(self.product)]}
        response = MagicMock()
        response.status_code = 200
        with patch.object(studio, "github_file", return_value=(fake_catalog, "sha-atual")), \
             patch.object(studio, "github_headers", return_value={}), \
             patch.object(studio.requests, "put", return_value=response) as put, \
             patch.object(studio, "invalidate") as invalid:
            studio.save_affiliate_change(lambda products: products[0].update({"status": "approved"}))
        self.assertEqual(put.call_count, 1)
        self.assertEqual(put.call_args.kwargs["json"]["sha"], "sha-atual")
        invalid.assert_called_once_with("content/affiliate_products.json")


if __name__ == "__main__":
    unittest.main()
