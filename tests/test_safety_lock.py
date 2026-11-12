import importlib.util
import unittest
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'src' / 'publish_daily.py'
spec = importlib.util.spec_from_file_location('publish_daily', SCRIPT)
pub = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pub)


class TestSafetyLock(unittest.TestCase):
    def test_pending_blocks_selection(self):
        posts = [{'id': '002', 'approved': True}]
        state = {'pending': {'id': '002', 'local_date': '2026-11-13'}}
        post, msg = pub.select_next(posts, state, '2026-11-14')
        self.assertIsNone(post)
        self.assertIn('reservada', msg)

    def test_no_publication_without_reservation(self):
        now = datetime(2026, 11, 13, 19, 17, tzinfo=ZoneInfo('America/Sao_Paulo'))
        with patch.object(pub, 'load_json', side_effect=[
            [{'id': '002', 'approved': True}],
            {'not_before_date': '2026-11-13', 'published': []}
        ]), patch.dict(pub.os.environ, {'PUBLISH_ENABLED': 'true'}):
            self.assertIsNone(pub.run(publish=True, now=now))

    def test_reserved_old_date_fails_closed(self):
        now = datetime(2026, 11, 14, 19, 17, tzinfo=ZoneInfo('America/Sao_Paulo'))
        with patch.object(pub, 'load_json', side_effect=[
            [{'id': '002', 'approved': True}],
            {'pending': {'id': '002', 'local_date': '2026-11-13'}}
        ]), patch.dict(pub.os.environ, {'PUBLISH_ENABLED': 'true'}):
            with self.assertRaisesRegex(RuntimeError, 'outra data'):
                pub.run(publish=True, now=now)

    def test_reserve_requires_explicit_enable(self):
        now = datetime(2026, 11, 13, 19, 17, tzinfo=ZoneInfo('America/Sao_Paulo'))
        with patch.object(pub, 'load_json', side_effect=[
            [{'id': '002', 'approved': True}],
            {'not_before_date': '2026-11-13', 'published': []}
        ]), patch.dict(pub.os.environ, {'PUBLISH_ENABLED': 'false'}):
            with self.assertRaisesRegex(RuntimeError, 'PUBLISH_ENABLED'):
                pub.run(reserve=True, now=now)

    def test_failed_meta_publish_preserves_pending(self):
        now = datetime(2026, 11, 13, 19, 17, tzinfo=ZoneInfo('America/Sao_Paulo'))
        state = {'pending': {'id': '002', 'local_date': '2026-11-13'},
                 'not_before_date': '2026-11-13', 'published': []}
        with (
            patch.object(pub, 'load_json', side_effect=[
                [{'id': '002', 'approved': True, 'caption': 'Teste'}], state
            ]),
            patch.object(pub, 'publish_image', side_effect=RuntimeError('falha')),
            patch.object(pub, 'save_state') as save,
            patch.dict(pub.os.environ, {
                'PUBLISH_ENABLED': 'true',
                'INSTAGRAM_ACCESS_TOKEN': 'token_falso',
                'INSTAGRAM_USER_ID': '123456',
                'PUBLIC_MEDIA_BASE_URL': 'https://example.com'
            })
        ):
            with self.assertRaisesRegex(RuntimeError, 'falha'):
                pub.run(publish=True, now=now, session=object())
            self.assertEqual(state['pending']['id'], '002')
            save.assert_not_called()

if __name__ == '__main__':
    unittest.main()
