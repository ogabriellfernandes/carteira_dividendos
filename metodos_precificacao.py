"""Métodos de precificação: Bazin, Graham e Barsi."""

import math


def preco_bazin(dividendos_12m: float) -> float | None:
    """Método de Décio Bazin: sempre 6% fixo, independente do tipo de ativo."""
    if not dividendos_12m or dividendos_12m <= 0:
        return None
    return round(dividendos_12m / 0.06, 2)


def preco_graham(lpa: float, vpa: float) -> float | None:
    """
    Fórmula de Benjamin Graham: Preço Justo = sqrt(22.5 * LPA * VPA)
    Só é válida para ações (não FIIs).
    """
    if not lpa or not vpa or lpa <= 0 or vpa <= 0:
        return None
    return round(math.sqrt(22.5 * lpa * vpa), 2)


def preco_barsi(dividendos_12m: float, dy_minimo: float = 0.06) -> float | None:
    """Método de Luiz Barsi: Preço Teto = Dividendos 12M / DY mínimo desejado."""
    if not dividendos_12m or dividendos_12m <= 0 or not dy_minimo:
        return None
    return round(dividendos_12m / dy_minimo, 2)


def dy_minimo_por_tipo(tipo: str) -> float:
    """Mantido por compatibilidade (fallback simples)."""
    tipo = tipo.upper()
    if "FII" in tipo:
        return 0.08
    if "REIT" in tipo or "ETF" in tipo:
        return 0.05
    return 0.06


def dy_minimo_por_segmento(segmento: str, tipo: str) -> float:
    """
    DY mínimo do método Barsi, variando por segmento — mapeado
    diretamente aos segmentos definidos em segmentos.py.
    """
    tipo_upper = (tipo or "").upper()

    if "FII" in tipo_upper:
        mapa_fii = {
            "fii papel": 0.09,
            "fii tijolo": 0.08,
            "fii logística": 0.08,
            "fii shopping": 0.08,
            "fii infraestrutura": 0.075,
            "fii agro": 0.08,
            "fii fundo de fundos": 0.08,
        }
        return mapa_fii.get((segmento or "").lower(), 0.08)

    if "REIT" in tipo_upper or "ETF" in tipo_upper:
        mapa_us = {
            "renda fixa (us)": 0.05,
            "etf dividendos (us)": 0.05,
            "reit varejo (us)": 0.05,
            "etf s&p 500 (us)": 0.03,
        }
        return mapa_us.get((segmento or "").lower(), 0.05)

    mapa_acoes = {
        "energia elétrica": 0.065,
        "seguros": 0.06,
        "bancos": 0.06,
        "holding financeira": 0.06,
        "petróleo e gás": 0.055,
        "papel e celulose": 0.05,
        "bebidas": 0.045,
        "mineração": 0.05,
        "químico": 0.05,
        "siderurgia": 0.05,
        "bens industriais": 0.04,
        "varejo": 0.04,
        "agronegócio": 0.05,
        "construção civil": 0.045,
        "saneamento": 0.065,
        "vestuário": 0.04,
    }

    return mapa_acoes.get((segmento or "").lower(), 0.06)
