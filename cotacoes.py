"""
cotacoes.py
Atualiza preços-teto (Bazin, Graham, Barsi) na planilha de cotações.
Fontes: Investidor10 -> StatusInvest -> yfinance -> Fundamentus (fallback final, só B3).
"""
import time
import math
import io
import random
import pandas as pd
import requests
import yfinance as yf

import gspread
from auth import autenticar_service_account
from config import SPREADSHEET_ID, ABA_COTACOES, HTTP_HEADERS
from segmentos import get_segmento, TICKERS_US
from metodos_precificacao import (
    preco_bazin, preco_graham, preco_barsi,
    dy_minimo_por_tipo, dy_minimo_por_segmento,
)
from investidor10 import buscar_investidor10
from statusinvest import buscar_statusinvest

# ------------------- Sessão customizada (evita bloqueio do Yahoo) -------------------

def criar_sessao_yfinance() -> requests.Session:
    """Cria uma sessão com headers de navegador real, reduzindo chance de bloqueio."""
    sessao = requests.Session()
    sessao.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
    })
    return sessao


SESSAO_YF = criar_sessao_yfinance()


# ------------------- Utilitários -------------------

def limpar_valor(v):
    if v is None:
        return ""
    if isinstance(v, float) and math.isnan(v):
        return ""
    return v


def formatar_ticker(ticker: str) -> str:
    ticker = ticker.strip().upper()
    return ticker if ticker in TICKERS_US else ticker + ".SA"

def limpar_prefixo_ticker(ticker: str) -> str:
    """Remove prefixos de bolsa (ex: BVMF:) que algumas planilhas trazem."""
    ticker = ticker.strip().upper()
    if ":" in ticker:
        ticker = ticker.split(":")[-1]
    return ticker


def classificar_tipo(ticker: str) -> str:
    if ticker in TICKERS_US:
        return "ETF/REIT (US)"
    if len(ticker) >= 5 and ticker[-2:] == "11":
        return "FII"
    return "Ação"


def coletar_dividendos_anuais_yf(divs: pd.Series, anos: int = 5) -> list[float]:
    """Agrega a série de dividendos do yfinance em totais por ano (últimos N anos)."""
    if divs is None or divs.empty:
        return []

    df = divs.reset_index()
    df.columns = ["data", "valor"]
    df["ano"] = df["data"].dt.year

    ano_atual = df["ano"].max()
    anos_desejados = range(ano_atual - anos + 1, ano_atual + 1)

    totais_por_ano = df.groupby("ano")["valor"].sum()
    return [round(float(totais_por_ano.get(a, 0.0)), 4) for a in anos_desejados]


# ------------------- Montagem do resultado -------------------

def montar_resultado(tipo, segmento, dy_percent, dy_12m, dividendos_12m, dividendos_5anos, lpa, vpa, fonte):
    """Centraliza o cálculo dos preços-teto para qualquer fonte de dados."""
    dy_min_barsi = dy_minimo_por_segmento(segmento, tipo)

    fonte_bazin = dividendos_5anos if dividendos_5anos else dividendos_12m
    p_bazin = preco_bazin(fonte_bazin)
    p_barsi = preco_barsi(dividendos_12m, dy_min_barsi)
    p_graham = preco_graham(lpa, vpa) if tipo == "Ação" else None

    return {
        "dividend_yield": round(dy_percent, 4) if dy_percent else 0,
        "dy_12m": round(dy_12m, 4) if dy_12m else 0,
        "tipo": tipo,
        "segmento": segmento,
        "barsi": p_barsi,
        "graham": p_graham,
        "bazin": p_bazin,
        "fonte": fonte,
    }


def _resultado_de_fonte_web(dados: dict, tipo: str, ticker_original: str, fonte: str):
    """Padroniza a conversão de um retorno (Investidor10/StatusInvest) em resultado final."""
    segmento = dados.get("segmento") or get_segmento(ticker_original, "N/A")
    dy_percent = dados["dividend_yield"]
    dividendos_12m = dados["dividendos_12m"]
    preco = dados["preco_atual"]
    dy_12m = dividendos_12m / preco if preco else 0

    return montar_resultado(
        tipo, segmento, dy_percent, dy_12m,
        dividendos_12m, [], dados["lpa"], dados["vpa"], fonte
    )


# ------------------- Fallback final: Fundamentus -------------------

def buscar_fundamentus(ticker_original: str):
    """Fallback final quando todas as outras fontes falham (só cobre B3, não US)."""
    ticker = ticker_original.strip().upper()
    url = f"https://www.fundamentus.com.br/detalhes.php?papel={ticker}"

    try:
        resp = requests.get(url, headers=HTTP_HEADERS, timeout=10)
        resp.raise_for_status()

        tabelas = pd.read_html(io.StringIO(resp.text), decimal=",", thousands=".")
        if not tabelas:
            print(f"    -> [DEBUG] Nenhuma tabela encontrada para {ticker_original}")
            return None

        dados_raw = {}
        for tabela in tabelas:
            for _, row in tabela.iterrows():
                for j in range(0, len(row) - 1, 2):
                    chave = str(row[j]).strip()
                    valor = row[j + 1]
                    dados_raw[chave] = valor

        def parse_num(v):
            try:
                if isinstance(v, str):
                    v = v.replace("%", "").replace(".", "").replace(",", ".")
                return float(v)
            except (ValueError, TypeError):
                return None

        preco_atual = parse_num(dados_raw.get("Cotação"))
        dy = parse_num(dados_raw.get("Div. Yield"))
        lpa = parse_num(dados_raw.get("LPA"))
        vpa = parse_num(dados_raw.get("VPA"))

        if preco_atual is None:
            print(f"    -> [DEBUG] 'Cotação' não encontrada. Chaves disponíveis: {list(dados_raw.keys())[:15]}")
            return None

        dy_percent = (dy / 100) if dy else 0
        dividendos_12m = dy_percent * preco_atual

        return {
            "preco_atual": preco_atual,
            "dividend_yield": dy_percent,
            "dividendos_12m": dividendos_12m,
            "lpa": lpa,
            "vpa": vpa,
        }
    except Exception as e:
        print(f"    -> Erro Fundamentus para {ticker_original}: {e}")
        return None


# ------------------- Busca principal (Investidor10 -> StatusInvest -> yfinance -> Fundamentus) -------------------

def buscar_dados(ticker_original: str, tentativas=3):
    tipo = classificar_tipo(ticker_original)
    eh_ticker_us = ticker_original.strip().upper() in TICKERS_US

    if not eh_ticker_us:
        # ---------- 1ª fonte: Investidor10 ----------
        dados_i10 = buscar_investidor10(ticker_original)
        if dados_i10:
            return _resultado_de_fonte_web(dados_i10, tipo, ticker_original, "investidor10")
        print(f"  -> Investidor10 falhou para {ticker_original}, tentando StatusInvest...")

        # ---------- 2ª fonte: StatusInvest ----------
        dados_si = buscar_statusinvest(ticker_original)
        if dados_si:
            return _resultado_de_fonte_web(dados_si, tipo, ticker_original, "statusinvest")
        print(f"  -> StatusInvest falhou para {ticker_original}, tentando yfinance...")

    # ---------- 3ª fonte: yfinance ----------
    ticker_yf = formatar_ticker(ticker_original)

    for tentativa in range(1, tentativas + 1):
        try:
            ativo = yf.Ticker(ticker_yf, session=SESSAO_YF)
            hist = ativo.history(period="1y")

            if hist.empty:
                raise ValueError("histórico vazio no yfinance")

            preco_atual = hist["Close"].iloc[-1]
            info = ativo.info

            dy_raw = info.get("dividendYield", 0) or 0
            dy_percent = dy_raw / 100

            divs = ativo.dividends
            dividendos_12m = divs[-252:].sum() if not divs.empty else 0
            dividendos_5anos = coletar_dividendos_anuais_yf(divs, anos=5)

            lpa = info.get("trailingEps")
            vpa = info.get("bookValue")
            segmento = get_segmento(ticker_original, info.get("sector", "N/A"))
            dy_12m = dividendos_12m / preco_atual if preco_atual else 0

            return montar_resultado(
                tipo, segmento, dy_percent, dy_12m,
                dividendos_12m, dividendos_5anos, lpa, vpa, "yfinance"
            )

        except Exception as e:
            print(f"  -> Erro yfinance tentativa {tentativa} para {ticker_original}: {e}")
            if tentativa < tentativas:
                time.sleep(5 * tentativa + random.uniform(1, 3))

    if eh_ticker_us:
        print(f"  -> {ticker_original} é ticker US, sem fallback disponível.")
        return None

    # ---------- 4ª fonte: Fundamentus ----------
    print(f"  -> Tentando fallback Fundamentus para {ticker_original}...")
    time.sleep(1)
    dados_fund = buscar_fundamentus(ticker_original)

    if dados_fund is None:
        print(f"  -> Fundamentus também falhou para {ticker_original}.")
        return None

    segmento = get_segmento(ticker_original, "N/A")
    dy_percent = dados_fund["dividend_yield"]
    dividendos_12m = dados_fund["dividendos_12m"]
    dy_12m = dividendos_12m / dados_fund["preco_atual"] if dados_fund["preco_atual"] else 0

    return montar_resultado(
        tipo, segmento, dy_percent, dy_12m,
        dividendos_12m, [], dados_fund["lpa"], dados_fund["vpa"], "fundamentus"
    )


# ------------------- Main -------------------

def main():
    creds = autenticar_service_account()
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet(ABA_COTACOES)

    tickers_raw = sheet.col_values(1)[1:]
    tickers = [limpar_prefixo_ticker(t) for t in tickers_raw if t]

    batch_data = []
    resumo_fontes = {
        "investidor10": 0,
        "statusinvest": 0,
        "yfinance": 0,
        "fundamentus": 0,
        "falhas": 0,
    }

    for i, ticker in enumerate(tickers, start=2):
        print(f"Buscando {ticker}...")
        dados = buscar_dados(ticker)
        ...

if __name__ == "__main__":
    main()