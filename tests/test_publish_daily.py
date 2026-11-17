import importlib.util
import json
import unittest
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

SCRIPT = Path(__file__).resolve().parents[1] / 'src' / 'publish_daily.py'
spec = importlib.util.spec_from_file_location('publish_daily', SCRIPT)
pub = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pub)


class TestPublisher(unittest.TestCase):
    def test_select_next(self):
        posts=[{'id':'001','approved':True}, {'id':'002','approved':True}]
        p,err=pub.select_next(posts,{'published':[{'id':'001','local_date':'2026-11-07'}]},'2026-11-08')
        self.assertEqual(p['id'],'002'); self.assertIsNone(err)

    def test_post_fixado_prevalece_sobre_campanha(self):
        posts = [{'id':'004','approved':True},
                 {'id':'C001','approved':True,'kind':'commercial'}]
        state = {'published':[{'id':'003','local_date':'2026-11-15'}]}
        post, reason = pub.select_next(
            posts, state, '2026-11-16', preferred_id='004')
        self.assertEqual(post['id'], '004')
        self.assertIsNone(reason)
        post, reason = pub.select_next(
            posts, state, '2026-11-16', preferred_id='005')
        self.assertIsNone(post)
        self.assertIn('fixado', reason)

    def test_no_double_post_same_day(self):
        p,err=pub.select_next([{'id':'002','approved':True}],{'published':[{'id':'000','local_date':'2026-11-13'}]},'2026-11-13')
        self.assertIsNone(p);self.assertIn('Já foi publicado',err)

    def test_only_approved(self):
        p,_=pub.select_next([{'id':'002','approved':False},{'id':'003','approved':True}],{'published':[]},'2026-11-14')
        self.assertEqual(p['id'],'003')

    def test_reserve_external(self):
        ps=[{'id':'001','approved':True},{'id':'002','approved':True}]
        st={'externally_scheduled':[{'id':'001','date':'2026-11-12'}]}
        p,_=pub.select_next(ps,st,'2026-11-13')
        self.assertEqual(p['id'],'002')

    def test_do_not_double_post_scheduled_day(self):
        ps=[{'id':'002','approved':True}]
        st={'externally_scheduled':[{'id':'001','date':'2026-11-12'}]}
        p,err=pub.select_next(ps,st,'2026-11-12')
        self.assertIsNone(p);self.assertIn('manualmente',err)

    def test_do_not_publish_before_start_date(self):
        p,err=pub.select_next([{'id':'002','approved':True}],{'not_before_date':'2026-11-13'},'2026-11-12')
        self.assertIsNone(p);self.assertIn('2026-11-13',err)

    def test_media_url(self):
        u=pub.media_url_for({'id':'012'},'https://exemplo.github.io/universo-eletrico')
        self.assertEqual(u,'https://exemplo.github.io/universo-eletrico/posts/012.jpg')

    def test_reject_non_https(self):
        with self.assertRaises(ValueError):pub.media_url_for({'id':'012'},'http://meusite.com')

    def test_all_images_present(self):
        root=Path(__file__).resolve().parents[1]
        # O catálogo educativo cresce ao criar novos posts no painel.
        # Verificar IDs únicos e JPG de cada item sem fixar um número de artes.
        posts=json.loads((root/'content'/'posts.json').read_text(encoding='utf-8'))
        self.assertGreaterEqual(len(posts),1)
        self.assertEqual(len({p['id'] for p in posts}),len(posts))
        for p in posts:
            self.assertTrue((root/'docs'/'posts'/f"{p['id']}.jpg").exists())

    
    def test_mode_safe_when_unapproved(self):
        posts = [{'id': '002', 'approved': False}]
        state = {
            'not_before_date': '2026-11-13',
            'published': [],
            'externally_scheduled': []
        }
        post, reason = pub.select_next(
            posts, state, '2026-11-13'
        )
        self.assertIsNone(post)
        self.assertIn('aprovados', reason)


    def test_no_publication_today(self):
        self.assertIsNone(pub.run(publish=False,now=datetime(2026,11,12,19,0,tzinfo=ZoneInfo('America/Sao_Paulo'))))

if __name__=='__main__':unittest.main()
