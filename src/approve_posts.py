"""Aprovação individual de conteúdo após revisão humana (sem postar automaticamente)."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
posts_file=ROOT/'content/posts.json'
state_file=ROOT/'content/state.json'

def approve(ids):
    posts=json.loads(posts_file.read_text(encoding='utf-8'))
    state=json.loads(state_file.read_text(encoding='utf-8'))
    reserved={p['id'] for p in state.get('externally_scheduled',[])}
    found={p['id'] for p in posts}
    for pid in ids:
        if pid not in found:
            raise ValueError(f'Post desconhecido: {pid}')
        if pid in reserved:
            raise ValueError(f'Post {pid} já está agendado manualmente; não aprove novamente.')
        media_file=ROOT/'docs'/'posts'/f'{pid}.jpg'
        if not media_file.exists():
            raise ValueError(f'Arte ausente: {media_file.name}')
    for p in posts:
        if p['id'] in ids:
            p['approved']=True
    posts_file.write_text(json.dumps(posts,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Aprovados:',', '.join(ids))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Marcar posts revisados como aprovados')
    parser.add_argument('ids',nargs='+',help='IDs dos posts, ex.: 002 003')
    args=parser.parse_args()
    approve(args.ids)
