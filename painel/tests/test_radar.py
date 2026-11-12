"""Radar de produtos: seleção editorial, links seguros, API oficial opcional."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PANEL_SESSION_SECRET", "segredo-apenas-teste")
os.environ.setdefault("PANEL_PASSWORD_HASH", "hash-apenas-teste")

import app as studio
from research import editorial_ideas, search_url, search_official_catalog, catalogue_interest


class TestRadar(unittest.TestCase):
    def setUp(self):
        studio.app.config["TESTING"] = True
        studio.app.secret_key = "segredo-local"
        self.client = studio.app.test_client()
        self.products = [{"name": "Kit Uno Para Arduino Iniciante Premium Com Material Didático Completo"}]
        self.posts = [{"title": "Sensor indutivo", "approved": True},
                      {"title": "Inversor de frequência", "approved": True},
                      {"title": "CLP", "approved": True}]

    def authorize(self):
        with self.client.session_transaction() as s:
            s["admin"] = True
            s["csrf"] = "csrf-teste"

    def test_radar_exige_login(self):
        result = self.client.get("/radar")
        self.assertEqual(result.status_code, 302)
        self.assertIn("/login", result.location)

    def test_radar_funciona_sem_token_de_api(self):
        self.authorize()
        with patch.dict(os.environ, {"MELI_ACCESS_TOKEN": ""}), \
             patch.object(studio, "repo_json", side_effect=[
                 {"products": self.products}, self.posts
             ]), \
             patch.object(studio, "search_official_catalog") as search:
            result = self.client.get("/radar")
        self.assertEqual(result.status_code, 200)
        self.assertIn(b"Radar de Produtos", result.data)
        self.assertIn(b"Pesquisar no Mercado Livre", result.data)
        self.assertIn(b"integra", result.data)
        search.assert_not_called()

    def test_radar_bloqueia_chamada_sem_token_quando_buscar(self):
        self.authorize()
        with patch.dict(os.environ, {"MELI_ACCESS_TOKEN": ""}), \
             patch.object(studio, "repo_json", side_effect=[
                 {"products": self.products}, self.posts
             ]), patch.object(studio, "search_official_catalog") as search:
            r = self.client.get("/radar?q=arduino")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"desativada", r.data)
        search.assert_not_called()

    def test_radar_com_token_consulta_api_uma_vez(self):
        self.authorize()
        with patch.dict(os.environ, {"MELI_ACCESS_TOKEN": "token-falso"}), \
             patch.object(studio, "repo_json", side_effect=[
                 {"products": self.products}, self.posts
             ]), patch.object(studio, "search_official_catalog", return_value=[
                 {"title": "Kit Didatico Arduino", "id": "MLB123456", "relevant": True}
             ]) as search:
            r = self.client.get("/radar?q=arduino")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Kit Didatico Arduino", r.data)
        search.assert_called_once_with("arduino", "token-falso")

    def test_radar_com_api_negada_nao_vaza_token(self):
        self.authorize()
        with patch.dict(os.environ, {"MELI_ACCESS_TOKEN": "segredo-secreto"}), \
             patch.object(studio, "repo_json", side_effect=[
                 {"products": self.products}, self.posts
             ]), patch.object(studio, "search_official_catalog", side_effect=RuntimeError("A API negou")):
            r = self.client.get("/radar?q=arduino")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"A API negou", r.data)
        self.assertNotIn(b"segredo-secreto", r.data)

    def test_sugestoes_priorizam_temas_da_fila(self):
        result = editorial_ideas(self.products, self.posts, limit=12)
        self.assertTrue(result)
        self.assertIn("sensor", result[0]["query"].lower())
        self.assertGreaterEqual(result[0]["score"], result[-1]["score"])

    def test_link_de_pesquisa_mantem_host_fixo(self):
        self.assertTrue(search_url("livro automação", "mercadolivre").startswith(
            "https://lista.mercadolivre.com.br/"))
        self.assertIn("keyword=", search_url("kit Arduino", "shopee"))
        self.assertIn("k=", search_url("kit Arduino", "amazon"))
        with self.assertRaises(ValueError):
            search_url("livro de Arduino", "website-qualquer")

    def test_nao_inventa_preco_estoque_ou_comissao(self):
        items = editorial_ideas(self.products, self.posts)
        for item in items:
            self.assertNotIn("price", item)
            self.assertNotIn("rating", item)
            self.assertNotIn("affiliate_url", item)

    def test_pesquisa_api_oficial_com_resposta_simulada(self):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"results": [
            {"id": "MLB123", "name": "Arduino Uno Didatico", "status": "active"},
            {"id": "MLB456", "name": "Livro sobre CLP", "status": "active"},
            {"id": "MLB456", "name": "Duplicado", "status": "active"},
            {"id": "INVALID", "name": "Outro", "status": "active"}
        ]}
        http = MagicMock()
        http.get.return_value = response
        results = search_official_catalog("arduino", "token-privado", http=http)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(x["relevant"] for x in results))
        req = http.get.call_args
        self.assertEqual(req.args[0], "https://api.mercadolibre.com/products/search")
        self.assertEqual(req.kwargs["params"]["site_id"], "MLB")
        self.assertEqual(req.kwargs["timeout"], 10)
        self.assertIn("Bearer token-privado", req.kwargs["headers"]["Authorization"])

    def test_pesquisa_api_nao_faz_chamada_sem_token(self):
        client = MagicMock()
        self.assertEqual(search_official_catalog("arduino", "", http=client), [])
        client.get.assert_not_called()

    def test_pesquisa_api_403_explicado(self):
        client = MagicMock()
        client.get.return_value.status_code = 403
        with self.assertRaisesRegex(RuntimeError, "negou"):
            search_official_catalog("arduino", "token", http=client)

    def test_sem_termo_valido_nao_chama_api(self):
        client = MagicMock()
        with self.assertRaises(ValueError):
            search_official_catalog("https://site.com", "token", http=client)
        client.get.assert_not_called()

    def test_prefill_apos_radar(self):
        self.authorize()
        with patch.object(studio, "repo_json", return_value={"products": []}):
            r = self.client.get("/afiliados?name=Livro%20de%20comandos%20eletricos&category=Livros%20e%20cursos")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'value="Livro de comandos eletricos"', r.data)

if __name__ == "__main__":
    unittest.main()
