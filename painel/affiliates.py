"""Regras de negocio da Central de Afiliados, sem dependencia de APIs externas.

A ligacao com marketplaces nao gera links automaticamente: somente armazena
links oficiais fornecidos pelo titular e prepara rascunhos para revisao humana.
"""
from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

MARKETPLACES = {
    "mercadolivre": {"name": "Mercado Livre", "hosts": ("meli.la", "mercadolivre.com.br", "mercadolibre.com.br")},
    "shopee": {"name": "Shopee", "hosts": ("shopee.com.br", "shopee.com", "shope.ee", "s.shopee.com.br")},
    "amazon": {"name": "Amazon", "hosts": ("amazon.com.br", "amzn.to")},
    "tiktok": {"name": "TikTok Shop", "hosts": ("tiktok.com", "shop.tiktok.com")},
}
CATEGORIES = [
    "Arduino e eletrônica",
    "CLP e automação",
    "Sensores industriais",
    "Livros e cursos",
    "Organização e estudo",
    "Componentes elétricos",
]
DISCLOSURES = ("#publicidade", "#pub", "link de afiliado", "publicidade:")
IDEAS = [
    ("Arduino para iniciantes", "Arduino e eletrônica", "Apresentar materiais de estudo e primeiros projetos conceituais."),
    ("Livro de comandos elétricos", "Livros e cursos", "Indicar materiais didáticos e explicar para quem são adequados."),
    ("Sensores indutivos", "Sensores industriais", "Explicar aplicações e especificações antes de recomendar."),
    ("Curso introdutório de CLP", "CLP e automação", "Mostrar o que se aprende em lógica de automação."),
    ("Organização de bancada", "Organização e estudo", "Recomendar acessórios de estudo e organização."),
    ("Livro de automação industrial", "Livros e cursos", "Associar indicações a conteúdos educativos do perfil."),
]


def marketplace_name(slug):
    return MARKETPLACES.get(slug, {}).get("name", slug)


def validate_affiliate_url(raw, marketplace):
    if marketplace not in MARKETPLACES:
        raise ValueError("Escolha um marketplace da lista.")
    if not isinstance(raw, str):
        raise ValueError("Link de afiliado invalido.")
    link = raw.strip()
    if not 12 <= len(link) <= 1200 or any(c.isspace() for c in link):
        raise ValueError("Informe um link HTTPS valido, sem espacos.")
    try:
        parsed = urlsplit(link)
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Endereço de afiliado invalido.") from exc
    if (parsed.scheme != "https" or not host or parsed.username or parsed.password
            or port not in (None, 443) or "\\" in link):
        raise ValueError("Somente links HTTPS de marketplaces oficiais sao permitidos.")
    allowed = MARKETPLACES[marketplace]["hosts"]
    if not any(host == domain or host.endswith("." + domain) for domain in allowed):
        raise ValueError("O link nao pertence ao marketplace escolhido.")
    return link


def clean_string(value, label, max_len, min_len=0):
    if not isinstance(value, str):
        raise ValueError(f"{label} invalido.")
    value = value.strip()
    if not min_len <= len(value) <= max_len:
        raise ValueError(f"{label}: utilize de {min_len} a {max_len} caracteres.")
    return value


def draft_caption(name, category):
    name = clean_string(name, "Nome do produto", 150, 6)
    category = clean_string(category, "Categoria", 90, 3)
    return (
        "⚡ Indicação do Universo Elétrico!\n\n"
        f"Conheça: {name}.\n\n"
        f"Para quem se interessa por {category.lower()}, vale conferir as "
        "características e comparar as opções disponíveis. Antes de comprar, "
        "verifique todos os itens incluídos, as especificações e a compatibilidade "
        "com seu objetivo de estudo.\n\n"
        "🔗 Link de afiliado disponível na nossa vitrine.\n\n"
        "#Publicidade #LinkDeAfiliado #UniversoEletrico #AutomacaoIndustrial"
    )


def normalize_product(raw):
    if not isinstance(raw, dict):
        raise ValueError("Dados de produto invalidos.")
    marketplace = clean_string(raw.get("marketplace", ""), "Marketplace", 30, 3)
    name = clean_string(raw.get("name", ""), "Nome do produto", 150, 6)
    category = clean_string(raw.get("category", ""), "Categoria", 90, 3)
    link = validate_affiliate_url(raw.get("affiliate_url", ""), marketplace)
    description = clean_string(raw.get("description", ""), "Descrição", 700)
    caption = clean_string(raw.get("caption", ""), "Legenda", 2000, 10)
    return {
        "name": name,
        "marketplace": marketplace,
        "category": category,
        "affiliate_url": link,
        "description": description,
        "caption": caption,
    }


def require_disclosure(caption):
    text = caption.casefold()
    if not any(marker in text for marker in DISCLOSURES):
        raise ValueError("Inclua #Publicidade ou 'link de afiliado' na legenda antes de aprovar.")


def new_id(products):
    current = [int(p["id"][1:]) for p in products
               if re.fullmatch(r"A\d{3,5}", str(p.get("id", "")))]
    return "A" + str(max(current, default=0) + 1).zfill(3)


def timestamp():
    return datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat(timespec="seconds")
