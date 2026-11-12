"""Radar de produtos: pautas editoriais e pesquisa autorizada do catálogo Mercado Livre.

As pautas locais são sugestões de pesquisa, não anúncios verificados.
Os itens obtidos na API oficial são produtos de CATÁLOGO, não ofertas,
não possuem necessariamente preço/comissão/link de afiliado.
"""
from __future__ import annotations
from urllib.parse import quote, urlencode
import re
import unicodedata
import requests

TOPICS = [
    ("Kit de estudos para Arduino", "Arduino e eletrônica",
     "Arduino", "Entenda para quem um kit introdutório é adequado.", "arduino iniciante kit"),
    ("Livro de comandos elétricos", "Livros e cursos",
     "Comandos elétricos", "Explique o que estudar antes de escolher um livro técnico.", "livro comandos elétricos"),
    ("Livro de automação industrial", "Livros e cursos",
     "Automação industrial", "Sugira leituras introdutórias e compare os temas apresentados.", "livro automação industrial"),
    ("Livro sobre CLP e lógica ladder", "Livros e cursos",
     "CLP", "Mostre o que um iniciante pode aprender sobre programação industrial.", "livro clp programação ladder"),
    ("Kit didático de eletrônica básica", "Arduino e eletrônica",
     "Eletrônica", "Fale sobre conceitos iniciais de eletrônica e projetos educativos.", "kit didatico eletronica"),
    ("Módulo para prototipagem Arduino", "Arduino e eletrônica",
     "Arduino", "Explique a diferença entre prototipagem e instalação industrial.", "arduino shield prototipagem"),
    ("Organizador de componentes", "Organização e estudo",
     "Organização", "Demonstre métodos de organização da bancada de estudos.", "organizador componentes eletronicos"),
    ("Etiqueta de identificação de cabos", "Organização e estudo",
     "Identificação", "Explique por que identificar cabos e circuitos facilita manutenção.", "etiqueta identificacao cabos"),
    ("Livro de sensores industriais", "Livros e cursos",
     "Sensores", "Explique tipos de sensores antes de recomendar material de estudo.", "livro sensores industriais"),
    ("Sensor indutivo para estudo", "Sensores industriais",
     "Sensor indutivo", "Explique detecção de metais e diferenças de especificações.", "sensor indutivo industrial"),
    ("Sensor capacitivo para estudo", "Sensores industriais",
     "Sensor capacitivo", "Fale sobre princípios de detecção e aplicações gerais.", "sensor capacitivo industrial"),
    ("Livro sobre motores elétricos", "Livros e cursos",
     "Motor trifásico", "Apresente conceitos e aplicações dos motores industriais.", "livro motores eletricos"),
    ("Material didático de inversor de frequência", "Livros e cursos",
     "Inversor de frequência", "Explique o princípio de controle de velocidade.", "livro inversor de frequencia"),
    ("Organização de bancada de eletrônica", "Organização e estudo",
     "Bancada", "Recomende acessórios de organização para estudos técnicos.", "organizador bancada eletrônica"),
    ("Manual de eletricidade básica", "Livros e cursos",
     "Eletricidade", "Explore princípios fundamentais de eletricidade.", "livro eletricidade basica"),
    ("Material didático de redes industriais", "Livros e cursos",
     "PROFINET", "Apresente conceitos de comunicação industrial.", "livro redes industriais profinet"),
]

SEARCH_HOSTS = {
    "mercadolivre": "https://lista.mercadolivre.com.br/",
    "shopee": "https://shopee.com.br/search?",
    "amazon": "https://www.amazon.com.br/s?",
}
RELATED_TERMS = ("arduino", "eletric", "eletrôn", "eletron", "motor", "autom",
                 "clp", "ladder", "sensor", "inversor", "cabo", "comando",
                 "profinet", "modbus", "robótica", "robotica", "fonte", "controle",
                 "industrial", "rele", "relé", "didat", "bancada")


def normalize(text):
    value = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in value if not unicodedata.combining(char))


def catalogue_interest(title):
    low = normalize(title)
    return any(term in low for term in ("arduino", "eletric", "eletron", "motor",
                "autom", "clp", "ladder", "sensor", "inversor", "cabo",
                "comando", "profinet", "modbus", "robot", "fonte", "didat", "bancada"))


def search_url(query, marketplace="mercadolivre"):
    if not isinstance(query, str) or len(query.strip()) < 3 or len(query) > 100:
        raise ValueError("Termo de pesquisa invalido.")
    keyword = query.strip()
    if marketplace == "mercadolivre":
        return SEARCH_HOSTS[marketplace] + quote(keyword, safe="")
    if marketplace == "shopee":
        return SEARCH_HOSTS[marketplace] + urlencode({"keyword": keyword})
    if marketplace == "amazon":
        return SEARCH_HOSTS[marketplace] + urlencode({"k": keyword})
    raise ValueError("Marketplace nao disponivel para pesquisa.")


def editorial_ideas(products, educational_posts, limit=12):
    """Gera fila de pautas por relevancia dos temas e evita repeticao de afiliados.
    Não afirma estoque, nota, comissão nem existência de um anúncio específico.
    """
    names = [normalize(str(p.get("name", ""))) for p in products]
    themes = " ".join(normalize(str(p.get("title", ""))) for p in educational_posts
                      if p.get("approved"))
    results = []
    for idx, (name, category, tag, angle, query) in enumerate(TOPICS):
        title_low = normalize(name)
        if any(title_low == existing or title_low in existing for existing in names):
            continue
        scored = 1
        if normalize(tag) in themes:
            scored += 3
        if any(t in normalize(query) for t in ("livro", "didatico", "organizador", "etiqueta")):
            scored += 1
        results.append({"title": name, "category": category, "topic": tag,
                        "angle": angle, "query": query, "score": scored,
                        "search_url": search_url(query), "original_index": idx})
    results.sort(key=lambda x: (-x["score"], x["original_index"]))
    return results[:limit]


def search_official_catalog(keyword, token, http=None):
    """Pesquisa produto de catalogo com token da aplicacao, nunca anuncio nem afiliacao.

    Referencia oficial: GET https://api.mercadolibre.com/products/search
    com site_id=MLB, status=active, q.
    """
    if not isinstance(keyword, str) or not re.fullmatch(r"[\wÀ-ÿ\s+\-]{3,70}", keyword.strip()):
        raise ValueError("Pesquise com palavras simples de 3 a 70 caracteres.")
    if not token:
        return []
    client = http or requests
    response = client.get(
        "https://api.mercadolibre.com/products/search",
        params={"status": "active", "site_id": "MLB", "q": keyword.strip(), "limit": 12},
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/json"},
        timeout=10,
    )
    if response.status_code in (401, 403):
        raise RuntimeError("A API do Mercado Livre negou a consulta. Confira as permissões da aplicação.")
    if response.status_code == 429:
        raise RuntimeError("Limite temporário da API atingido. Tente novamente mais tarde.")
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise ValueError("Formato inesperado da resposta do catálogo oficial.")
    items, seen = [], set()
    for item in data["results"][:12]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("name") or item.get("title") or "").strip()
        pid = str(item.get("id") or "").strip()
        if not title or not re.fullmatch(r"MLB\d+", pid) or pid in seen:
            continue
        seen.add(pid)
        items.append({"id": pid, "title": title[:140], "relevant": catalogue_interest(title),
                      "status": str(item.get("status") or "")})
    items.sort(key=lambda x: (not x["relevant"], x["title"]))
    return items
