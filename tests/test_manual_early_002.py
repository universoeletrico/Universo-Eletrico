"""Testes do modo manual unico: nao acessam Meta nem publicam."""
import importlib.util
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

SCRIPT = Path(__file__).resolve().parents[1] / 'src' / 'publish_daily.py'
spec = importlib.util.spec_from_file_location('publish_daily_early', SCRIPT)
pub = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pub)


class TestManualEarly(unittest.TestCase):
    def setUp(self):
        self.posts = [
            {'id': '001', 'approved': False},
            {'id': '002', 'approved': True},
        ]
        self.state = {
            'not_before_date': '2026-11-13',
            'published': [],
            'externally_scheduled': [{'id': '001', 'date': '2026-11-12'}],
        }
        self.now = datetime(2026, 11, 11, 23, 30, tzinfo=ZoneInfo('America/Sao_Paulo'))

    def test_default_does_not_allow_early_publication(self):
        with patch.object(pub, 'load_json', side_effect=[self.posts, self.state]), \
             patch.dict(pub.os.environ, {'PUBLISH_ENABLED': 'false', 'MANUAL_TEST_POST_ID': ''}):
            self.assertIsNone(pub.run(publish=False, now=self.now))

    def test_manual_reserves_only_post_002_on_11(self):
        with patch.object(pub, 'load_json', side_effect=[self.posts, self.state]), \
             patch.object(pub, 'save_state') as saved, \
             patch.dict(pub.os.environ, {'PUBLISH_ENABLED': 'true', 'MANUAL_TEST_POST_ID': '002'}):
            p = pub.reserve_for_day(self.now)
        self.assertEqual(p['id'], '002')
        self.assertEqual(self.state['pending']['id'], '002')
        saved.assert_called_once()

    def test_manual_early_does_not_apply_to_nov12(self):
        other = datetime(2026, 11, 12, 12, 0, tzinfo=ZoneInfo('America/Sao_Paulo'))
        with patch.object(pub, 'load_json', side_effect=[self.posts, self.state]), \
             patch.dict(pub.os.environ, {'PUBLISH_ENABLED': 'true', 'MANUAL_TEST_POST_ID': '002'}):
            self.assertIsNone(pub.reserve_for_day(other))

    def test_wrong_post_id_never_allowed(self):
        self.assertFalse(pub.manual_early_test_allowed('2026-11-11', '001'))
        self.assertFalse(pub.manual_early_test_allowed('2026-11-12', '002'))

    def test_early_publish_still_requires_same_day_reservation(self):
        with patch.object(pub, 'load_json', side_effect=[self.posts, self.state]), \
             patch.dict(pub.os.environ, {'PUBLISH_ENABLED': 'true', 'MANUAL_TEST_POST_ID': '002'}):
            self.assertIsNone(pub.run(publish=True, now=self.now, session=object()))


if __name__ == '__main__':
    unittest.main()
