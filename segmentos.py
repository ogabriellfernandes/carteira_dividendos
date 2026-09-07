# segmentos.py
"""Dicionário de segmentos por ticker (fallback quando yfinance não retorna corretamente)."""

SEGMENTOS = {
    "TAEE11": "Energia Elétrica",
    "BBSE3": "Seguros",
    "CXSE3": "Seguros",
    "BBAS3": "Bancos",
    "CMIG4": "Energia Elétrica",
    "PETR4": "Petróleo e Gás",
    "KLBN11": "Papel e Celulose",
    "ABEV3": "Bebidas",
    "VALE3": "Mineração",
    "UNIP6": "Químico",
    "GGBR3": "Siderurgia",
    "WEGE3": "Bens Industriais",
    "ITSA4": "Holding Financeira",
    "ABCB4": "Bancos",
    "LJQQ3": "Varejo",
    "AGRO3": "Agronegócio",
    "MXRF11": "FII Papel",
    "VGHF11": "FII Papel",
    "KFOF11": "FII Fundo de Fundos",
    "SNAG11": "FII Agro",
    "JURO11": "FII Papel",
    "KDIF11": "FII Papel",
    "IFRA11": "FII Infraestrutura",
    "GARE11": "FII Tijolo",
    "XPML11": "FII Shopping",
    "BTLG11": "FII Logística",
    "TFLO": "Renda Fixa (US)",
    "JEPI": "ETF Dividendos (US)",
    "JEPQ": "ETF Dividendos (US)",
    "O": "REIT Varejo (US)",
    "HGLG11": "FII Logística",
    "XPLG11": "FII Logística",
    "TRXF11": "FII Tijolo",
    "PATL11": "FII Papel",
    "KNCR11": "FII Papel",
    "SANB11": "Bancos",
    "CURY3": "Construção Civil",
    "MCRE11": "FII Papel",
    "BTHF11": "FII Papel",
    "CMIN3": "Mineração",
    "SAPR11": "Saneamento",
    "GGRC11": "FII Tijolo",
    "SNEL11": "Energia Elétrica",
    "SAPR4": "Saneamento",
    "CSMG3": "Saneamento",
    "BMGB4": "Bancos",
    "GRND3": "Vestuário",
    "IVV": "ETF S&P 500 (US)",
}

# Tickers americanos que não recebem sufixo .SA no yfinance
TICKERS_US = {"TFLO", "JEPI", "JEPQ", "O", "IVV"}


def get_segmento(ticker: str, fallback: str = "N/A") -> str:
    return SEGMENTOS.get(ticker.strip().upper(), fallback)
