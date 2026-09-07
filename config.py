"""
Configurações centrais do projeto: IDs, ranges e arquivos de credenciais.
"""
import os
from dotenv import load_dotenv

load_dotenv()


def _get_env(key: str, required: bool = True, default: str | None = None) -> str:
    """Lê variável de ambiente com validação explícita."""
    value = os.environ.get(key, default)
    if required and not value:
        raise EnvironmentError(
            f"Variável de ambiente obrigatória não definida: '{key}'"
        )
    return value


# ---------- Autenticação OAuth (buscarDividendos.py) ----------
SCOPES: list[str] = ["https://www.googleapis.com/auth/spreadsheets"]
CLIENT_SECRET_FILE: str = "Client_secret.json"
TOKEN_FILE: str = "token.json"

# ---------- Autenticação Service Account (cotacoes.py) ----------
SERVICE_ACCOUNT_FILE: str = "service_account.json"
SERVICE_ACCOUNT_SCOPES: list[str] = ["https://www.googleapis.com/auth/spreadsheets"]

# ---------- Planilha principal (única para todo o projeto) ----------
SPREADSHEET_ID: str = _get_env("SPREADSHEET_ID")

# ---------- Abas / Ranges - Carteira / Dividendos ----------
CARTEIRA_RANGE: str = "CARTEIRA!A1:A20"
LANCAMENTOS_RANGE: str = "LANÇAMENTOS YELD!A5:O"
MOVIMENTACAO_RANGE: str = "MOVIMENTAÇÕES!A5:D"
NOME_ABA_LANCAMENTOS: str = "LANÇAMENTOS YELD"
TICKERS_IGNORADOS: set[str] = set()

# ---------- Abas / Ranges - Cotações ----------
ABA_COTACOES: str = "COTAÇÕES B3"

# ---------- Scraper (Investidor10) ----------
SCRAPER_HEADERS: dict[str, str] = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}
SCRAPER_CONNECT_TIMEOUT: int = 5
SCRAPER_READ_TIMEOUT: int = 20
SCRAPER_DELAY_MIN: float = 1.5
SCRAPER_DELAY_MAX: float = 3.0

# ---------- Requisições HTTP (APIs externas: brapi, fundamentus) ----------
HTTP_HEADERS: dict[str, str] = {"User-Agent": "Mozilla/5.0"}
