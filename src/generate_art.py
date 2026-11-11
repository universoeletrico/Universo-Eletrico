"""Gera artes 1080x1350, sem dependência de serviços externos."""
from __future__ import annotations
import json, math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
NAVY = '#071B3B'
NAVY2 = '#0D3158'
YELLOW = '#FFD21A'
WHITE = '#FFFFFF'
SOFT = '#CAD6E3'
FONT_REG = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONT_BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'


def font(size, bold=False):
    try:
        return ImageFont.truetype(FONT_BOLD if bold else FONT_REG, size)
    except OSError:
        return ImageFont.load_default()


def wrap(draw, text, maxw, font_obj):
    lines=[]; current=''
    for word in text.split():
        trial=(current+' '+word).strip()
        if draw.textbbox((0,0),trial,font=font_obj)[2] <= maxw:
            current=trial
        else:
            if current: lines.append(current)
            current=word
    if current: lines.append(current)
    return lines


def bolt(draw, cx, cy, scale=1, color=YELLOW):
    coords=[(-18,-100),(35,-100),(0,-18),(50,-18),(-35,105),(-5,13),(-56,13)]
    pts=[(int(cx+x*scale),int(cy+y*scale)) for x,y in coords]
    draw.polygon(pts,fill=color)


def make_post(post):
    W,H=1080,1350
    im=Image.new('RGB',(W,H),NAVY)
    d=ImageDraw.Draw(im)
    # topo com detalhes industriais
    d.rectangle((0,0,W,18),fill=YELLOW)
    d.ellipse((680,175,1330,825),outline=NAVY2,width=48)
    d.ellipse((810,235,1180,605),outline='#173D66',width=4)
    for k in range(5):
        y=110+k*55;d.line((810,y,1010,y),fill='#244C70',width=3)
        d.ellipse((1003,y-8,1019,y+8),fill=YELLOW)
    d.text((72,67),'UNIVERSO ELÉTRICO',font=font(30,True),fill=WHITE)
    d.text((72,117),'ELÉTRICA  •  AUTOMAÇÃO INDUSTRIAL',font=font(23),fill=SOFT)
    # Sem numeração na arte para manter o feed limpo e atemporal.
    d.ellipse((900,205,1012,317),outline=YELLOW,width=5)
    bolt(d,956,261,0.35)
    title_font=font(68,True)
    lines=wrap(d,post['hook'],820,title_font)
    if len(lines)>3:
        title_font=font(59,True);lines=wrap(d,post['hook'],830,title_font)
    y=322
    for line in lines:
        d.text((68,y),line,font=title_font,fill=WHITE,stroke_width=0)
        y+=87
    # separador
    d.rounded_rectangle((68,720,1012,726),radius=3,fill=YELLOW)
    d.text((68,771),'ENTENDA EM 30 SEGUNDOS',font=font(28,True),fill=YELLOW)
    body_font=font(43)
    body_lines=wrap(d,post['body'],925,body_font)
    if len(body_lines)>5:
        body_font=font(38);body_lines=wrap(d,post['body'],925,body_font)
    y=835
    for line in body_lines:
        d.text((68,y),line,font=body_font,fill=WHITE)
        y+=61
    d.rectangle((0,1210,1080,1350),fill=NAVY2)
    d.rounded_rectangle((68,1241,900,1310),radius=17,outline=YELLOW,width=2)
    d.text((91,1259),'SALVE  •  COMPARTILHE  •  APRENDA',font=font(24,True),fill=WHITE)
    out=ROOT/'docs'/'posts'/f'{post["id"]}.jpg'
    im.save(out,'JPEG',quality=89,optimize=True)
    return out


def make_avatar():
    # Apenas recorte e redimensionamento da marca existente para a foto de perfil.
    img=Image.open(ROOT/'assets'/'logo-original.png').convert('RGB')
    W,H=img.size
    img=ImageOps.fit(img,(1024,1024),method=Image.Resampling.LANCZOS)
    img.save(ROOT/'assets'/'foto-perfil.jpg',quality=93)


def make_preview(posts):
    thumbsize=(256,320)
    canvas=Image.new('RGB',(3*256+4*16,3*320+4*16),'#E8EFF4')
    for ix,p in enumerate(posts[:9]):
        im=Image.open(ROOT/'docs'/'posts'/f'{p["id"]}.jpg')
        im.thumbnail(thumbsize)
        x=16+(ix%3)*(256+16);y=16+(ix//3)*(320+16)
        canvas.paste(im,(x,y))
    canvas.save(ROOT/'assets'/'grade-primeiros-9-posts.jpg',quality=88)

if __name__=='__main__':
    posts=json.loads((ROOT/'content'/'posts.json').read_text(encoding='utf-8'))
    for p in posts:make_post(p)
    make_avatar();make_preview(posts)
    (ROOT/'docs'/'index.html').write_text('''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Universo Elétrico - Arquivos públicos</title><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="font-family:system-ui;background:#071B3B;color:white;margin:2rem"><h1>Universo Elétrico ⚡</h1><p>Arquivos das publicações educativas.</p><p>Conheça os conteúdos no Instagram.</p></body></html>''',encoding='utf-8')
    print('Artes prontas:',len(posts))
