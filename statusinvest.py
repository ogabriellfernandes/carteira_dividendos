"""statusinvest.py — Fonte alternativa de dados fundamentalistas (ações e FIIs)."""
import requests
from bs4 import BeautifulSoup
from config import HTTP_HEADERS


def parse_num_br(v: str):
    """Converte string no formato brasileiro (37,57 / 7,96% / 1.234,56) para float."""
    if not v:
        return None
    v = v.strip().replace("R$", "").replace("%", "").strip()
    v = v.replace(".", "").replace(",", ".")
    try:
        return float(v)
    except ValueError:
        return None


def _extrair_indicadores(soup: BeautifulSoup) -> dict:
    """
    StatusInvest usa blocos com <h3 class="title"> + <strong/div class="value">.
    Cobrimos as variações mais comuns de estrutura do site.
    """
    indicadores = {}

    # Padrão 1: div.info > h3.title (título) + strong.value (valor)
    for bloco in soup.select("div.info"):
        titulo_tag = bloco.select_one("h3.title") or bloco.select_one(".title")
        valor_tag = bloco.select_one("strong.value") or bloco.select_one(".value")
        if titulo_tag and valor_tag:
            titulo = titulo_tag.get_text(strip=True).upper()
            valor = valor_tag.get_text(strip=True)
            if titulo and valor:
                indicadores[titulo] = valor

    # Padrão 2 (fallback): elementos com atributo title diretamente
    if not indicadores:
        for tag in soup.select("[title]"):
            titulo = tag.get("title", "").strip().upper()
            if not titulo:
                continue
            valor_tag = tag.select_one(".value") or tag.find_next(class_="value")
            if valor_tag:
                valor = valor_tag.get_text(strip=True)
                if valor:
                    indicadores[titulo] = valor

    return indicadores


def _extrair_segmento(soup: BeautifulSoup):
    """Tenta localizar o setor/segmento no HTML do StatusInvest."""
    tentativas = [
        soup.select_one(".sector-name"),
        soup.select_one("[title='Setor']"),
        soup.select_one("[title='Segmento']"),
    ]
    for tag in tentativas:
        if tag:
            texto = tag.get_text(strip=True)
            if texto:
                return texto
    return None


def buscar_statusinvest(ticker_original: str):
    """Extrai indicadores fundamentalistas do StatusInvest via HTML puro."""
    ticker = ticker_original.strip().upper()

    urls_possiveis = [
        f"https://statusinvest.com.br/acoes/{ticker.lower()}",
        f"https://statusinvest.com.br/fundos-imobiliarios/{ticker.lower()}",
    ]

    resp = None
    for url in urls_possiveis:
        try:
            r = requests.get(url, headers=HTTP_HEADERS, timeout=10)
            if r.status_code == 200 and ("value" in r.text or "title" in r.text):
                resp = r
                break
        except Exception:
            continue

    if resp is None:
        print(f"    -> StatusInvest: não encontrou página válida para {ticker_original}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    indicadores = _extrair_indicadores(soup)

    if not indicadores:
        print(f"    -> [DEBUG] Nenhum indicador encontrado para {ticker_original}")
        return None

    preco_atual = parse_num_br(
        indicadores.get("COTAÇÃO") or indicadores.get("PREÇO") or indicadores.get("VALOR ATUAL")
    )
    dy = parse_num_br(indicadores.get("DY") or indicadores.get("DIVIDEND YIELD"))
    pl = parse_num_br(indicadores.get("P/L"))
    pvp = parse_num_br(indicadores.get("P/VP"))
    lpa = parse_num_br(indicadores.get("LPA"))
    vpa = parse_num_br(indicadores.get("VPA") or indicadores.get("VP"))

    if preco_atual is None:
        print(f"    -> [DEBUG] Chaves encontradas: {list(indicadores.keys())[:20]}")
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
