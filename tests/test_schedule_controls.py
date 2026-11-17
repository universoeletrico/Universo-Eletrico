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
        late = self.now.replace(hour=16, minute=18)
        self.assertIsNone(agenda.due_slot(self.config, late))

    def test_recuperacao_apos_atraso_do_github(self):
        config = {"timezone": "America/Sao_Paulo", "enabled": True,
                  "days": list(range(7)), "times": ["19:17"],
                  "date_overrides": {"2026-11-16": ["21:00"]}}
        tz = ZoneInfo("America/Sao_Paulo")
        # A execucao perdida de 21h nao deve impedir a tentativa as 22h.
        self.assertEqual(agenda.due_slot(config, datetime(2026, 11, 16, 22, 36, tzinfo=tz)), "21:00")
        self.assertEqual(agenda.due_slot(config, datetime(2026, 11, 17, 22, 0, tzinfo=tz)), "19:17")
        self.assertIsNone(agenda.due_slot(config, datetime(2026, 11, 17, 23, 18, tzinfo=tz)))
        self.assertIsNone(agenda.due_slot(config, datetime(2026, 11, 18, 1, 0, tzinfo=tz)))

    def test_em_multiplos_horarios_prestigia_slot_mais_recente(self):
        tz = ZoneInfo("America/Sao_Paulo")
        self.assertEqual(agenda.due_slot(self.config, datetime(2026, 11, 13, 19, 20, tzinfo=tz)), "19:17")


    def test_agenda_apenas_no_dia_autorizado(self):
        config = {**self.config, "only_date": "2026-11-16", "days": [0],
                  "times": ["19:17"]}
        horario = datetime(2026, 11, 16, 19, 25,
                           tzinfo=ZoneInfo("America/Sao_Paulo"))
        self.assertEqual(agenda.due_slot(config, horario), "19:17")
        self.assertIsNone(agenda.due_slot(config, horario.replace(day=23)))
        self.assertEqual(len(agenda.upcoming(config, horario, days_ahead=14)), 1)

    def test_rejeita_data_invalida(self):
        with self.assertRaises(ValueError):
            agenda.validate_schedule({**self.config, "only_date": "2026-02-30"})

    def test_agenda_dois_dias_sem_repetir_nas_semanas_seguintes(self):
        config = {**self.config, "only_dates": ["2026-11-16", "2026-11-17"],
                  "days": [0, 1], "times": ["21:00"]}
        tz = ZoneInfo("America/Sao_Paulo")
        monday = datetime(2026, 11, 16, 21, 10, tzinfo=tz)
        tuesday = datetime(2026, 11, 17, 21, 10, tzinfo=tz)
        next_monday = datetime(2026, 11, 23, 21, 10, tzinfo=tz)
        self.assertEqual(agenda.due_slot(config, monday), "21:00")
        self.assertEqual(agenda.due_slot(config, tuesday), "21:00")
        self.assertIsNone(agenda.due_slot(config, next_monday))
        self.assertEqual(len(agenda.upcoming(config, monday, days_ahead=14)), 2)

    def test_agenda_rejeita_lista_de_datas_invalidas(self):
        for dates in (["2026-02-30"], [], ["2026-11-16", "2026-11-16"], [14]):
            with self.subTest(dates=dates):
                with self.assertRaises(ValueError):
                    agenda.validate_schedule({**self.config, "only_dates": dates})
        with self.assertRaises(ValueError):
            agenda.validate_schedule({**self.config, "only_date": "2026-11-16",
                                      "only_dates": ["2026-11-17"]})

    def test_rotina_diaria_1917_com_excecao_hoje_2100(self):
        config = {"timezone": "America/Sao_Paulo", "enabled": True,
                  "days": list(range(7)), "times": ["19:17"],
                  "date_overrides": {"2026-11-16": ["21:00"]}}
        tz = ZoneInfo("America/Sao_Paulo")
        hoje = datetime(2026, 11, 16, 21, 12, tzinfo=tz)
        amanha = datetime(2026, 11, 17, 19, 22, tzinfo=tz)
        self.assertEqual(agenda.due_slot(config, hoje), "21:00")
        self.assertIsNone(agenda.due_slot(config, hoje.replace(hour=19, minute=20)))
        self.assertEqual(agenda.due_slot(config, amanha), "19:17")
        self.assertEqual(agenda.due_slot(config, amanha.replace(day=18)), "19:17")
        rows = agenda.upcoming(config, hoje, days_ahead=3)
        self.assertEqual([r["times"] for r in rows],
                         [["21:00"], ["19:17"], ["19:17"]])

    def test_rejeita_multiplas_postagens_em_excecao(self):
        with self.assertRaises(ValueError):
            agenda.validate_schedule({**self.config, "date_overrides":
                                      {"2026-11-16": ["19:17", "21:00"]}})

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
