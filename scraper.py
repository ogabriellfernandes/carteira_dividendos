"""
scraper.py
Coleta proventos (dividendos/rendimentos) do Investidor10 para uma lista
de tickers (Ações, FIIs e ETFs Globais), com conversão USD -> BRL quando
aplicável.
"""
from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import (
    SCRAPER_HEADERS as HEADERS,
    SCRAPER_CONNECT_TIMEOUT as CONNECT_TIMEOUT,
    SCRAPER_READ_TIMEOUT as READ_TIMEOUT,
    SCRAPER_DELAY_MIN as DELAY_MIN,
    SCRAPER_DELAY_MAX as DELAY_MAX,
)

# ===================== LOGGING =====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("scraper.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ===================== CONSTANTES DE NEGÓCIO =====================
CATEGORIAS = [
    ("acoes", "Ações"),
    ("fiis", "FII"),
    ("etfs-global", "ETF Global"),
]
FORMATOS_DATA = ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"]
COTACAO_URL = "https://economia.awesomeapi.com.br/last/USD-BRL"
BASE_URL = "https://investidor10.com.br"

# ===================== CACHE DE COTAÇÃO =====================
CACHE_COTACAO_PATH = Path("cotacao_cache.json")
CACHE_COTACAO_TTL_HORAS = 12


@dataclass
class ProventoBruto:
    """Representa um provento extraído do site, ainda em formato de dict-friendly."""
    data_com: str
    data_pagamento: str
    ativo: str
    valor: str
    descricao: str
    tipo: str
    valor_usd: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "data_com": self.data_com,
            "data_pagamento": self.data_pagamento,
            "ativo": self.ativo,
            "valor": self.valor,
            "descricao": self.descricao,
            "tipo": self.tipo,
            "valor_usd": self.valor_usd,
        }


def _criar_sessao() -> requests.Session:
    """Cria uma sessão HTTP reutilizável com retry automático para erros transitórios."""
    sessao = requests.Session()
    sessao.headers.update(HEADERS)

    retry = Retry(
        total=3,
        backoff_factor=2,  # 2s, 4s, 8s...
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    sessao.mount("https://", adapter)
    sessao.mount("http://", adapter)

    return sessao


def normalizar_data(data_str: str) -> Optional[str]:
    """Garante que a data esteja no formato dd/mm/yyyy. Retorna None se não reconhecida."""
    data_str = data_str.strip()

    for fmt in FORMATOS_DATA:
        try:
            return datetime.strptime(data_str, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue

    log.warning("Data em formato desconhecido, ignorada: '%s'", data_str)
    return None


def normalizar_valor_usd(valor_str: str) -> Optional[float]:
    """Converte string de valor em dólar (com vírgula decimal, ex: '0,1634') para float."""
    v = valor_str.replace("US$", "").replace("$", "").strip().replace(",", ".")
    try:
        return float(v)
    except ValueError:
        return None


def _buscar_pagina(
    sessao: requests.Session, ticker: str, tentativas: int = 3
) -> tuple[Optional[str], Optional[str]]:
    """
    Tenta achar o ativo em /acoes/, /fiis/ e /etfs-global/ (ex: TFLO, ativos internacionais).
    Retorna (html, tipo) ou (None, None).
    """
    ticker = ticker.strip().lower()

    for categoria, tipo in CATEGORIAS:
        url = f"{BASE_URL}/{categoria}/{ticker}/"

        for tentativa in range(1, tentativas + 1):
            try:
                resp = sessao.get(url, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))

                if resp.status_code == 200 and "dividendos" in resp.text.lower():
                    return resp.text, tipo
                break  # status != 200 ou sem "dividendos" -> tenta próxima categoria

            except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError) as e:
                log.warning(
                    "Tentativa %d/%d falhou para '%s' (%s): %s",
                    tentativa, tentativas, ticker, categoria, e,
                )
                if tentativa < tentativas:
                    time.sleep(3 * tentativa)
                else:
                    log.error("'%s' (%s) esgotou tentativas.", ticker, categoria)

            except requests.exceptions.RequestException as e:
                log.error("Erro inesperado ao buscar '%s' (%s): %s", ticker, categoria, e)
                break

    return None, None


def _extrair_proventos(
    html: str, ticker: str, tipo: str, cotacao_usd: Optional[float] = None
) -> list[ProventoBruto]:
    """Faz o parsing da tabela de histórico de dividendos do Investidor10."""
    soup = BeautifulSoup(html, "html.parser")
    tabela = soup.find("table", {"id": "table-dividends-history"})

    if not tabela:
        log.warning("Tabela de dividendos não encontrada para '%s'.", ticker)
        return []

    tbody = tabela.find("tbody")
    if not tbody:
        log.warning("Tabela sem <tbody> para '%s'.", ticker)
        return []

    proventos: list[ProventoBruto] = []

    for linha in tbody.find_all("tr"):
        colunas = [c.get_text(strip=True) for c in linha.find_all("td")]
        if len(colunas) < 4:
            continue

        descricao, data_com_raw, data_pagamento_raw, valor = colunas[:4]

        data_com = normalizar_data(data_com_raw)
        if not data_com:
            continue

        data_pagamento = normalizar_data(data_pagamento_raw) or ""

        if not valor or valor.strip() in ("-", "N/A", ""):
            log.warning("Valor inválido/ausente para '%s' em %s: '%s'", ticker, data_com, valor)
            continue

        valor_usd_original = None

        if tipo == "ETF Global" and cotacao_usd:
            valor_num = normalizar_valor_usd(valor)
            if valor_num is not None:
                valor_usd_original = valor_num
                valor = str(round(valor_num * cotacao_usd, 4))

        proventos.append(ProventoBruto(
            data_com=data_com,
            data_pagamento=data_pagamento,
            ativo=ticker.upper(),
            valor=valor,
            descricao=descricao,
            tipo=tipo,
            valor_usd=valor_usd_original,
        ))

    return proventos


# ===================== COTAÇÃO USD/BRL (com cache/fallback) =====================

def _ler_cache_cotacao() -> Optional[float]:
    """Lê cotação salva em cache, se ainda válida (dentro do TTL)."""
    if not CACHE_COTACAO_PATH.exists():
        return None
    try:
        dados = json.loads(CACHE_COTACAO_PATH.read_text(encoding="utf-8"))
        salvo_em = datetime.fromisoformat(dados["salvo_em"])
        if datetime.now() - salvo_em > timedelta(hours=CACHE_COTACAO_TTL_HORAS):
            return None
        return float(dados["valor"])
    except Exception as e:
        log.warning("Cache de cotação inválido/corrompido: %s", e)
        return None


def _salvar_cache_cotacao(valor: float) -> None:
    """Persiste a cotação obtida com sucesso, para uso como fallback futuro."""
    try:
        CACHE_COTACAO_PATH.write_text(
            json.dumps({"valor": valor, "salvo_em": datetime.now().isoformat()}),
            encoding="utf-8",
        )
    except Exception as e:
        log.warning("Falha ao salvar cache de cotação: %s", e)


def _buscar_cotacao_usd_brl(sessao: requests.Session) -> Optional[float]:
    """
    Busca a cotação atual USD -> BRL via AwesomeAPI (gratuita, sem chave).
    Em caso de falha (ex: 429), usa cache local recente como fallback.
    """
    try:
        resp = sessao.get(COTACAO_URL, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
        resp.raise_for_status()
        valor = float(resp.json()["USDBRL"]["bid"])
        _salvar_cache_cotacao(valor)
        return valor
    except Exception as e:
        log.error("Falha ao buscar cotação USD/BRL: %s", e)
        cache = _ler_cache_cotacao()
        if cache:
            log.warning("Usando cotação em cache (R$ %.4f) como fallback.", cache)
            return cache
        return None


def obter_cotacao_dolar(cotacao_existente: Optional[float] = None) -> Optional[float]:
    """
    Wrapper público de cotação USD -> BRL.
    Se `cotacao_existente` for fornecida (já obtida em outro ponto do fluxo,
    ex: dentro de `buscar_proventos`), apenas a retorna — evitando uma
    segunda requisição à API e reduzindo risco de 429.
    """
    if cotacao_existente is not None:
        return cotacao_existente

    sessao = _criar_sessao()
    try:
        return _buscar_cotacao_usd_brl(sessao)
    finally:
        sessao.close()


def buscar_proventos(
    tickers: list[str], meses_retroativos: int = 6
) -> tuple[list[dict], Optional[float]]:
    """
    Recebe lista de tickers e retorna (proventos, cotacao_usd_utilizada).
    Reutiliza uma única sessão HTTP e aplica delay entre requisições
    para reduzir risco de bloqueio pelo site.
    """
    resultado: list[dict] = []
    data_limite = datetime.now() - timedelta(days=30 * meses_retroativos)
    sessao = _criar_sessao()

    cotacao_usd = _buscar_cotacao_usd_brl(sessao)
    if cotacao_usd:
        log.info("Cotação USD/BRL utilizada: R$ %.4f", cotacao_usd)
    else:
        log.warning("Cotação USD/BRL indisponível — valores de ETFs globais ficarão em dólar.")

    total = len(tickers)

    try:
        for i, ticker in enumerate(tickers, start=1):
            if not ticker:
                continue

            html, tipo = _buscar_pagina(sessao, ticker)
            if not html:
                log.warning("Ativo '%s' não encontrado no Investidor10.", ticker)
                continue

            proventos = _extrair_proventos(html, ticker, tipo, cotacao_usd)

            proventos_filtrados = []
            for p in proventos:
                try:
                    data_com_dt = datetime.strptime(p.data_com, "%d/%m/%Y")
                except ValueError:
                    continue
                if data_com_dt >= data_limite:
                    proventos_filtrados.append(p.to_dict())

            resultado.extend(proventos_filtrados)
            log.info(
                "'%s' -> %d provento(s) recente(s)/futuro(s).",
                ticker.upper(), len(proventos_filtrados),
            )

            if i < total:
                time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    finally:
        sessao.close()

    return resultado, cotacao_usd


if __name__ == "__main__":
    # Teste rápido isolado, sem depender do Google Sheets
    proventos, cotacao = buscar_proventos(["btlg11", "petr4"])
    for d in proventos:
        print(d)
    print(f"Cotação usada: {cotacao}")
