"""Testes offline do caminho de publicacao da Meta, sem credenciais reais."""
import importlib.util
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

SCRIPT = Path(__file__).resolve().parents[1] / "src" / "publish_daily.py"
spec = importlib.util.spec_from_file_location("publish_daily_mocked", SCRIPT)
pub = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pub)


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status

    def json(self):
        return self.payload


class FakeMetaSession:
    def __init__(self, *, fail_on_publish=False):
        self.calls = []
        self.fail_on_publish = fail_on_publish

    def post(self, url, data, headers, timeout):
        self.calls.append(("POST", url, dict(data)))
        assert headers["Authorization"] == "Bearer token_falso"
        if url.endswith("/media_publish"):
            if self.fail_on_publish:
                return FakeResponse({"error": {"message": "Falha simulada", "code": 100}}, 400)
            return FakeResponse({"id": "media_999"})
        if url.endswith("/media"):
            return FakeResponse({"id": "container_123"})
        raise AssertionError("POST nao esperado: " + url)

    def get(self, url, params, headers, timeout):
        self.calls.append(("GET", url, dict(params)))
        assert headers["Authorization"] == "Bearer token_falso"
        if url.endswith("/container_123"):
            return FakeResponse({"status_code": "FINISHED"})
        raise AssertionError("GET nao esperado: " + url)


class TestMetaOffline(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 13, 19, 17, tzinfo=ZoneInfo("America/Sao_Paulo"))
        self.post = {
            "id": "002", "title": "Disjuntor x fusivel", "hook": "Protecao",
            "body": "Conceitos", "caption": "Teste aprovado", "approved": True
        }
        self.env = {
            "PUBLISH_ENABLED": "true",
            "INSTAGRAM_ACCESS_TOKEN": "token_falso",
            "INSTAGRAM_USER_ID": "123456",
            "PUBLIC_MEDIA_BASE_URL": "https://exemplo.github.io/projeto",
            "GRAPH_API_VERSION": "v27.0",
        }

    def test_publicacao_simulada_usa_reserva_e_registra_resultado(self):
        state = {
            "not_before_date": "2026-11-13", "published": [],
            "pending": {"id": "002", "local_date": "2026-11-13"},
        }
        fake = FakeMetaSession()
        with patch.object(pub, "load_json", side_effect=[[self.post], state]), \
             patch.object(pub, "save_state") as save_state, \
             patch.dict(pub.os.environ, self.env):
            returned = pub.run(publish=True, now=self.now, session=fake)

        self.assertEqual(returned["id"], "002")
        self.assertEqual([call[0] for call in fake.calls], ["POST", "GET", "POST"])
        self.assertTrue(fake.calls[0][1].endswith("/123456/media"))
        self.assertTrue(fake.calls[2][1].endswith("/123456/media_publish"))
        self.assertTrue(fake.calls[0][2]["image_url"].endswith("/posts/002.jpg"))
        self.assertNotIn("pending", state)
        self.assertEqual(state["published"][0]["media_id"], "media_999")
        save_state.assert_called_once_with(state)

    def test_falha_simulada_da_meta_preserva_reserva(self):
        state = {
            "not_before_date": "2026-11-13", "published": [],
            "pending": {"id": "002", "local_date": "2026-11-13"},
        }
        fake = FakeMetaSession(fail_on_publish=True)
        with patch.object(pub, "load_json", side_effect=[[self.post], state]), \
             patch.object(pub, "save_state") as save_state, \
             patch.dict(pub.os.environ, self.env):
            with self.assertRaisesRegex(RuntimeError, "Falha simulada"):
                pub.run(publish=True, now=self.now, session=fake)

        self.assertEqual(state["pending"]["id"], "002")
        self.assertFalse(state["published"])
        save_state.assert_not_called()
        selected, msg = pub.select_next([self.post], state, "2026-11-14")
        self.assertIsNone(selected)
        self.assertIn("reservada", msg)

    def test_publicacao_real_bloqueada_por_padrao(self):
        state = {"pending": {"id": "002", "local_date": "2026-11-13"}}
        fake = FakeMetaSession()
        with patch.object(pub, "load_json", side_effect=[[self.post], state]), \
             patch.dict(pub.os.environ, {"PUBLISH_ENABLED": "false"}):
            with self.assertRaisesRegex(RuntimeError, "desativada"):
                pub.run(publish=True, now=self.now, session=fake)
        self.assertEqual(fake.calls, [])


if __name__ == "__main__":
    unittest.main()
