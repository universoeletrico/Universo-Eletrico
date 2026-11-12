"""Testes offline da agenda editavel. Nenhuma chamada para Meta."""
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("schedule_rules_test", ROOT / "src/schedule_rules.py")
agenda = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agenda)
specp = importlib.util.spec_from_file_location("publish_agenda_test", ROOT / "src/publish_daily.py")
pub = importlib.util.module_from_spec(specp)
specp.loader.exec_module(pub)


class TestAgenda(unittest.TestCase):
    def setUp(self):
        self.config = {"timezone": "America/Sao_Paulo", "enabled": True,
                       "days": [0, 1, 2, 3, 4, 5, 6], "times": ["12:17", "19:17"]}
        self.now = datetime(2026, 11, 13, 12, 28, tzinfo=ZoneInfo("America/Sao_Paulo"))

    def test_formato_e_ordem(self):
        config = agenda.validate_schedule({**self.config, "times": ["19:17", "12:17"]})
        self.assertEqual(config["times"], ["12:17", "19:17"])

    def test_rejeita_quatro_postagens(self):
        with self.assertRaises(ValueError):
            agenda.validate_schedule({**self.config, "times": ["01:00", "04:00", "08:00", "20:00"]})

    def test_rejeita_menos_uma_hora(self):
        with self.assertRaises(ValueError):
            agenda.validate_schedule({**self.config, "times": ["12:17", "12:37"]})

    def test_rejeita_dias_invalidos(self):
        with self.assertRaises(ValueError):
            agenda.validate_schedule({**self.config, "days": [8]})

    def test_agenda_pausada_nao_libera(self):
        self.assertIsNone(agenda.due_slot({**self.config, "enabled": False}, self.now))

    def test_dia_nao_permitido(self):
        self.assertIsNone(agenda.due_slot({**self.config, "days": [0]}, self.now))

    def test_slot_na_janela(self):
        self.assertEqual(agenda.due_slot(self.config, self.now), "12:17")

    def test_slot_antes_do_horario_nao_vale(self):
        early = self.now.replace(hour=12, minute=15)
        self.assertIsNone(agenda.due_slot(self.config, early))

    def test_slot_expirado_nao_vale(self):
        late = self.now.replace(hour=13, minute=2)
        self.assertIsNone(agenda.due_slot(self.config, late))

    def test_uma_arte_por_slot(self):
        posts = [{"id": "003", "approved": True}]
        state = {"published": [{"id": "001", "local_date": "2026-11-13", "slot": "12:17"}]}
        p, reason = pub.select_next(posts, state, "2026-11-13", max_per_day=2, slot="12:17")
        self.assertIsNone(p)
        self.assertIn("horario", reason)
        p, reason = pub.select_next(posts, state, "2026-11-13", max_per_day=2, slot="19:17")
        self.assertEqual(p["id"], "003")

    def test_publicacao_sem_slot_bloqueia_repeticao(self):
        state = {"published": [{"id": "002", "local_date": "2026-11-13"}]}
        p, _ = pub.select_next([{"id": "003", "approved": True}], state, "2026-11-13", max_per_day=3, slot="19:17")
        self.assertIsNone(p)

    def test_dia_agendado_externamente_bloqueia(self):
        state = {"externally_scheduled": [{"id": "001", "date": "2026-11-13"}]}
        p, reason = pub.select_next([{"id": "003", "approved": True}], state, "2026-11-13", max_per_day=3, slot="19:17")
        self.assertIsNone(p)
        self.assertIn("programada", reason)

    def test_check_schedule_sem_publicacao(self):
        with patch.object(pub, "read_schedule", return_value=self.config), \
             patch.object(pub, "load_json", side_effect=[
                 [{"id": "003", "approved": True}],
                 {"published": [], "not_before_date": "2026-11-13"}
             ]):
            self.assertEqual(pub.check_schedule(self.now), "12:17")


if __name__ == "__main__":
    unittest.main()
