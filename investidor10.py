"""investidor10.py — Fonte primária de dados fundamentalistas (ações e FIIs)."""
import requests
from bs4 import BeautifulSoup
from config import HTTP_HEADERS


def parse_num_br(v: str):
    """Converte string no formato brasileiro (R$ 37,57 / 7,96% / 1.234,56) para float."""
    if not v:
        return None
    v = v.strip().replace("R$", "").replace("%", "").strip()
    v = v.replace(".", "").replace(",", ".")
    try:
        return float(v)
    except ValueError:
        return None


def _extrair_segmento(soup: BeautifulSoup):
    """Tenta localizar o segmento/setor no HTML. Retorna None se não encontrar."""
    tentativas = [
        soup.select_one('span[title="Setor"]'),
        soup.select_one('span[title="Segmento"]'),
        soup.select_one(".setor"),
        soup.select_one(".segment"),
    ]
    for tag in tentativas:
        if tag:
            texto = tag.get_text(strip=True)
            if texto and texto.upper() not in ("SETOR", "SEGMENTO"):
                return texto

    # fallback: procura o próximo <span> irmão do elemento com title="Setor"
    setor_label = soup.find(attrs={"title": "Setor"})
    if setor_label:
        proximo = setor_label.find_next("span")
        if proximo:
            return proximo.get_text(strip=True)

    return None


def buscar_investidor10(ticker_original: str):
    """Extrai indicadores fundamentalistas do Investidor10 via HTML puro."""
    ticker = ticker_original.strip().upper()

    urls_possiveis = [
        f"https://investidor10.com.br/acoes/{ticker.lower()}/",
        f"https://investidor10.com.br/fiis/{ticker.lower()}/",
    ]

    resp = None
    for url in urls_possiveis:
        try:
            r = requests.get(url, headers=HTTP_HEADERS, timeout=10)
            if r.status_code == 200 and "_card" in r.text:
                resp = r
                break
        except Exception:
            continue

    if resp is None:
        print(f"    -> Investidor10: não encontrou página válida para {ticker_original}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # Usa apenas a PRIMEIRA seção de cards (o HTML tem duplicata mobile/desktop)
    secao = soup.select_one("#cards-ticker")
    cards = secao.select("div._card") if secao else soup.select("div._card")

    indicadores = {}
    for card in cards:
        header_span = card.select_one("._card-header span[title]")
        if not header_span:
            continue

        titulo = header_span["title"].strip().upper()

        body = card.select_one("._card-body")
        if not body:
            continue

        # O valor pode estar em span.value (Cotação) ou span simples (P/L, DY, etc)
        valor_span = body.select_one("span.value") or body.select_one("span")
        if valor_span:
            valor = valor_span.get_text(strip=True)
            if valor:  # evita sobrescrever com valores vazios de cards duplicados
                indicadores[titulo] = valor

    if not indicadores:
        print(f"    -> [DEBUG] Nenhum _card encontrado para {ticker_original}")
        return None

    preco_atual = parse_num_br(indicadores.get("COTAÇÃO"))
    dy = parse_num_br(indicadores.get("DY"))
    pl = parse_num_br(indicadores.get("P/L"))
    pvp = parse_num_br(indicadores.get("P/VP"))
    lpa = parse_num_br(indicadores.get("LPA"))
    vpa = parse_num_br(indicadores.get("VPA") or indicadores.get("VP"))

    if preco_atual is None:
        print(f"    -> [DEBUG] Chaves encontradas: {list(indicadores.keys())}")
        return None

    dy_percent = (dy / 100) if dy else 0
    dividendos_12m = dy_percent * preco_atual

    return {
        "preco_atual": preco_atual,
        "dividend_yield": dy_percent,
        "dividendos_12m": dividendos_12m,
        "lpa": lpa,
        "vpa": vpa,
        "pl": pl,
        "pvp": pvp,
        "segmento": _extrair_segmento(soup),
    }
