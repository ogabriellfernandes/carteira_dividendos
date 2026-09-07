"""
Módulo central de autenticação com Google APIs.
"""
import logging
import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from google_auth_oauthlib.flow import InstalledAppFlow

from config import (
    CLIENT_SECRET_FILE,
    SCOPES,
    SERVICE_ACCOUNT_FILE,
    SERVICE_ACCOUNT_SCOPES,
    TOKEN_FILE,
)

logger = logging.getLogger(__name__)


def autenticar_oauth() -> Credentials:
    """
    Autentica via fluxo OAuth interativo (requer navegador).
    ⚠️ Não utilizável em ambientes headless (ex.: GitHub Actions).
    """
    creds: Credentials | None = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Token expirado. Renovando via refresh_token.")
            creds.refresh(Request())
        else:
            if not os.path.exists(CLIENT_SECRET_FILE):
                raise FileNotFoundError(
                    f"Arquivo de credenciais OAuth não encontrado: '{CLIENT_SECRET_FILE}'"
                )
            logger.info("Iniciando fluxo OAuth interativo (abrirá navegador).")
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
        logger.info("Token salvo em '%s'.", TOKEN_FILE)

    return creds


def autenticar_service_account() -> ServiceAccountCredentials:
    """
    Retorna credenciais de Service Account, compatíveis com
    googleapiclient.discovery.build() e gspread.authorize().

    Ideal para automação (GitHub Actions, cron, etc.) — não requer interação humana.
    """
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        raise FileNotFoundError(
            f"Arquivo de Service Account não encontrado: '{SERVICE_ACCOUNT_FILE}'. "
            "No GitHub Actions, verifique se o passo de criação do arquivo "
            "a partir do Secret foi executado antes deste."
        )

    try:
        return ServiceAccountCredentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SERVICE_ACCOUNT_SCOPES
        )
    except ValueError as e:
        raise ValueError(
            f"Erro ao carregar Service Account: {e}. "
            "Verifique se o JSON do Secret está íntegro (sem quebras de linha corrompidas)."
        ) from e
