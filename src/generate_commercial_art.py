"""Artes comerciais originais do Universo Elétrico, 1080x1350 px.

Não utiliza imagens de terceiros nem representa fielmente um anúncio.
Dados comerciais mutáveis (preço, estoque, vendas) ficam fora da arte.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "content" / "commercial_campaigns.json"
OUT = ROOT / "docs" / "posts"
FONT_NORMAL = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
NAVY = "#06172C"
PANEL = "#0D2A49"
YELLOW = "#FFD43B"
WHITE = "#F9FBFF"
MUTED = "#AFC7D8"
CYAN = "#5AE2D3"


def font(size, bold=False):
    try:
        return ImageFont.truetype(FONT_BOLD if bold else FONT_NORMAL, size)
    except OSError:
        return ImageFont.load_default()


def wrap(draw, value, width, text_font):
    lines = []
    current = ""
    for word in value.split():
        trial = (current + " " + word).strip()
        if draw.textbbox((0, 0), trial, font=text_font)[2] <= width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def glyph(d, id, cx, cy):
    """Ícones gráficos estilizados: não equivalem a fotografias dos modelos."""
    line = CYAN
    if id == "C001":
        d.rounded_rectangle((cx-140,cy-172,cx+140,cy+170),radius=22,fill="#1F4362",outline=line,width=6)
        for col in (-88,0,88):
            d.rectangle((cx+col-21,cy-203,cx+col+21,cy-165),fill=YELLOW)
            d.rectangle((cx+col-21,cy+165,cx+col+21,cy+199),fill=YELLOW)
        d.rounded_rectangle((cx-103,cy-119,cx+103,cy+30),radius=15,outline=MUTED,width=5)
        d.text((cx-65,cy-84),"KM",fill=WHITE,font=font(72,True))
        d.line((cx-90,cy+78,cx+90,cy+78),fill=YELLOW,width=7)
        d.line((cx-90,cy+112,cx+90,cy+112),fill=YELLOW,width=7)
    elif id == "C002":
        d.ellipse((cx-185,cy-184,cx+185,cy+186),fill="#152F50",outline=CYAN,width=9)
        d.rounded_rectangle((cx-151,cy-72,cx+151,cy+68),radius=21,fill="#041D24",outline="#28665B",width=5)
        d.text((cx-118,cy-48),"V  A",font=font(70,True),fill=YELLOW)
        d.line((cx-130,cy+115,cx+130,cy+115),fill=MUTED,width=5)
    elif id == "C003":
        d.rounded_rectangle((cx-184,cy-73,cx+128,cy+75),radius=52,fill="#778C9F",outline=WHITE,width=5)
        for dx in range(-150,90,23):
            d.line((cx+dx,cy-70,cx+dx+25,cy+74),fill="#253C55",width=4)
        d.rectangle((cx+110,cy-42,cx+170,cy+42),fill="#0F283E",outline=CYAN,width=5)
        d.arc((cx+124,cy-120,cx+265,cy+122),-76,76,fill=YELLOW,width=9)
        d.arc((cx+133,cy-171,cx+318,cy+173),-70,70,fill=CYAN,width=5)
    elif id == "C004":
        d.rounded_rectangle((cx-145,cy-192,cx+145,cy+192),radius=23,fill="#1B4162",outline=CYAN,width=7)
        d.ellipse((cx-92,cy-112,cx+92,cy+72),outline=WHITE,width=8)
        d.line((cx,cy-21,cx,cy-78),fill=YELLOW,width=12)
        d.line((cx,cy-21,cx+57,cy+16),fill=YELLOW,width=12)
        for i in range(3):
            d.line((cx-91,cy+103+i*27,cx+92,cy+103+i*27),fill=MUTED,width=5)
    elif id == "C005":
        d.rounded_rectangle((cx-166,cy-197,cx+166,cy+192),radius=28,fill="#26445E",outline=CYAN,width=7)
        d.rounded_rectangle((cx-119,cy-148,cx+119,cy-17),radius=13,fill="#071F2C")
        pts=[]
        for i in range(55):
            xx=cx-97+i*3.5
            yy=cy-86-30*math.sin(i*math.pi/12)
            pts.append((xx,yy))
        d.line(pts,fill=YELLOW,width=5)
        for i in range(3):
            d.rounded_rectangle((cx-114+i*78,cy+49,cx-66+i*78,cy+95),radius=8,fill="#385F74",outline=WHITE,width=3)
        d.text((cx-102,cy+132),"Hz",fill=WHITE,font=font(38,True))
    else:
        d.line([(cx-248,cy+105),(cx-155,cy+111),(cx-86,cy+65),(cx-10,cy+74)],fill="#768DA2",width=25,joint="curve")
        d.rounded_rectangle((cx-18,cy-74,cx+170,cy+104),radius=31,fill="#293F57",outline=CYAN,width=6)
        d.rounded_rectangle((cx+125,cy-54,cx+211,cy+84),radius=22,fill="#7A90A4",outline=WHITE,width=4)
        for ox,oy in ((150,-17),(185,-17),(150,48),(185,48)):
            d.ellipse((cx+ox-9,cy+oy-9,cx+ox+9,cy+oy+9),fill=YELLOW)
        d.ellipse((cx+18,cy+10,cx+48,cy+40),fill=YELLOW)


def make_art(entry):
    width, height = 1080, 1350
    im = Image.new("RGB", (width,height), NAVY)
    d = ImageDraw.Draw(im)
    d.rectangle((0,0,width,18),fill=YELLOW)
    for n in range(18):
        xx=(n*88)%1080
        d.line((xx,72,xx+145,255),fill="#102C4B",width=2)
    d.rounded_rectangle((48,54,1032,1298),radius=32,outline="#244F72",width=3)
    d.text((86,85),"UNIVERSO ELÉTRICO",font=font(36,True),fill=WHITE)
    d.text((86,146),"SELEÇÃO DE AUTOMAÇÃO INDUSTRIAL",font=font(21,True),fill=CYAN)
    d.line((86,194,996,194),fill="#315773",width=4)
    d.rounded_rectangle((74,233,1006,728),radius=26,fill=PANEL)
    glyph(d,entry["id"],540,484)
    title = entry["visual_title"]
    title_font=font(69,True)
    lines=wrap(d,title,886,title_font)
    if len(lines)>3:
        title_font=font(57,True)
        lines=wrap(d,title,888,title_font)
    yy=750
    for line in lines[:3]:
        d.text((86,yy),line,font=title_font,fill=WHITE)
        yy+=89
    yy=max(yy+20,985)
    d.rounded_rectangle((86,yy,994,yy+98),radius=17,fill="#174861")
    subt_font=font(30,True)
    subtitle=entry["visual_subtitle"]
    for i,line in enumerate(wrap(d,subtitle,850,subt_font)[:2]):
        d.text((112,yy+17+37*i),line,font=subt_font,fill=WHITE)
    d.text((86,1144),"CONHEÇA NA NOSSA VITRINE",font=font(31,True),fill=YELLOW)
    d.text((86,1202),"#Publicidade  •  Link de afiliado",font=font(23),fill=MUTED)
    d.text((86,1252),"Arte ilustrativa  •  Confira o anúncio real",font=font(18),fill="#91B1C6")
    OUT.mkdir(parents=True,exist_ok=True)
    path=OUT/f'{entry["id"]}.jpg'
    im.save(path,format="JPEG",quality=88,optimize=True)
    return path


def main():
    data=json.loads(FILE.read_text(encoding="utf-8"))
    campaigns=data.get("campaigns",[])
    for entry in campaigns:
        if entry["id"].startswith("C") and len(entry["id"]) == 4:
            path=make_art(entry)
            print(path.relative_to(ROOT))

if __name__ == "__main__":
    main()
