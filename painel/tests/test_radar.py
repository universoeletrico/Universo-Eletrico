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
from research import editorial_ideas, search_url, search_official_catalog, catalogue_interest, catalogue_category


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
        with patch.dict(os.environ, {"GITHUB_WRITE_TOKEN": "token-teste"}), \
             patch.object(studio.meli_oauth, "configured", return_value=False), \
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
        self.assertIn(b"Conecte primeiro", r.data)
        search.assert_not_called()

    def test_radar_com_token_consulta_api_uma_vez(self):
        self.authorize()
        with patch.object(studio.meli_oauth, "configured", return_value=True), \
             patch.object(studio.meli_oauth, "connection_status", return_value={"connected": True}), \
             patch.object(studio.meli_oauth, "valid_access_token", return_value="token-falso"), \
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
        with patch.object(studio.meli_oauth, "configured", return_value=True), \
             patch.object(studio.meli_oauth, "connection_status", return_value={"connected": True}), \
             patch.object(studio.meli_oauth, "valid_access_token", return_value="segredo-secreto"), \
             patch.object(studio, "repo_json", side_effect=[
                 {"products": self.products}, self.posts
             ]), patch.object(studio, "search_official_catalog", side_effect=RuntimeError("A API negou")):
            r = self.client.get("/radar?q=arduino")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"A API negou", r.data)
        self.assertNotIn(b"segredo-secreto", r.data)


    def test_categoria_de_catalogo_coerente_com_titulo(self):
        expected = {
            "Livro de automação industrial": "Livros e cursos",
            "Sensor Indutivo PNP": "Sensores industriais",
            "CLP Siemens Compacto": "CLP e automação",
            "Kit Arduino Uno": "Arduino e eletrônica",
            "Organizador de cabos": "Organização e estudo",
            "Disjuntor bifásico": "Componentes elétricos",
        }
        for title, category in expected.items():
            self.assertEqual(catalogue_category(title), category)

    def test_selecionar_nao_cria_campanha_nem_publica(self):
        self.authorize()
        observed = []
        def fake_save(change, group="products"):
            self.assertEqual(group, "radar_selections")
            items = []
            result = change(items)
            observed.extend(items)
            return result
        with patch.object(studio, "save_affiliate_change", side_effect=fake_save) as save:
            r = self.client.post("/radar/selecionar", data={
                "csrf": "csrf-teste", "catalog_id": "MLB123456",
                "name": "Sensor industrial PNP", "q": "sensor"
            })
        self.assertEqual(r.status_code, 302)
        self.assertIn("q=sensor", r.location)
        save.assert_called_once()
        self.assertEqual(observed[0]["catalog_id"], "MLB123456")
        self.assertEqual(observed[0]["category"], "Sensores industriais")
        self.assertNotIn("status", observed[0])
        self.assertNotIn("affiliate_url", observed[0])

    def test_radar_selecao_rejeita_duplicado(self):
        self.authorize()
        prior = [{"catalog_id": "MLB123", "name": "CLP Inicial",
                  "category": "CLP e automação"}]
        def fake_save(change, group="products"):
            return change(prior)
        with patch.object(studio, "save_affiliate_change", side_effect=fake_save):
            r = self.client.post("/radar/selecionar", data={
                "csrf": "csrf-teste", "catalog_id": "MLB123",
                "name": "CLP Inicial"
            }, follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(len(prior), 1)
        with self.client.session_transaction() as s:
            messages = s.get("_flashes", [])
        self.assertTrue(any("já está" in message for _, message in messages))

    def test_radar_selecao_exige_csrf_e_id_oficial(self):
        self.authorize()
        with patch.object(studio, "save_affiliate_change") as save:
            missing_csrf = self.client.post("/radar/selecionar", data={
                "csrf": "invalido", "catalog_id": "MLB123", "name": "Sensor PNP"
            })
            invalid_id = self.client.post("/radar/selecionar", data={
                "csrf": "csrf-teste", "catalog_id": "INVALID",
                "name": "Sensor PNP"
            })
        self.assertEqual(missing_csrf.status_code, 400)
        self.assertEqual(invalid_id.status_code, 302)
        save.assert_not_called()

    def test_lista_retorna_sem_campanhas_aprovadas(self):
        self.authorize()
        entry = {"catalog_id": "MLB123", "name": "Sensor industrial PNP",
                 "category": "Sensores industriais", "selected_at": "2026-11-13"}
        with patch.dict(os.environ, {"GITHUB_WRITE_TOKEN": "token-teste"}), \
             patch.object(studio.meli_oauth, "configured", return_value=False), \
             patch.object(studio, "repo_json", side_effect=[
                {"products": self.products, "radar_selections": [entry]}, self.posts
             ]):
            r = self.client.get("/radar")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Sensor industrial PNP", r.data)
        self.assertIn(b"MINHA LISTA DE PESQUISA", r.data.upper())
        self.assertIn(b"radar/remover", r.data)
        self.assertIn(b"catalog_id=MLB123", r.data)

    def test_remocao_nao_muda_produtos_aprovados(self):
        self.authorize()
        selections = [{"catalog_id": "MLB123", "name": "Sensor",
                       "category": "Sensores industriais"}]
        products = [{"id": "A001", "status": "approved"}]
        def fake_save(change, group="products"):
            self.assertEqual(group, "radar_selections")
            return change(selections)
        with patch.object(studio, "save_affiliate_change", side_effect=fake_save):
            r = self.client.post("/radar/remover", data={
                "csrf": "csrf-teste", "catalog_id": "MLB123"
            })
        self.assertEqual(r.status_code, 302)
        self.assertEqual(selections, [])
        self.assertEqual(products[0]["status"], "approved")

    def test_radar_preenche_origem_no_rascunho(self):
        self.authorize()
        with patch.object(studio, "repo_json", return_value={"products": []}):
            r = self.client.get(
                "/afiliados?name=Sensor%20industrial%20PNP"
                "&category=Sensores%20industriais&catalog_id=MLB12345")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"MLB12345", r.data)
        self.assertIn(b"Produto vindo do Radar", r.data)

    def test_sugestoes_priorizam_temas_da_fila(self):
        result = editorial_ideas(self.products, self.posts, limit=12)
        self.assertTrue(result)
        self.assertGreaterEqual(result[0]["score"], 4)
        self.assertTrue(any("sensor" in item["query"].lower() for item in result[:6]))
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
