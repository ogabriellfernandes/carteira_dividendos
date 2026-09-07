"""
buscarDividendos.py
Orquestra: leitura de carteira -> scraping de proventos -> diff contra
lançamentos existentes -> atualização/inserção no Google Sheets.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from auth import autenticar_service_account
from config import (
    SPREADSHEET_ID,
    CARTEIRA_RANGE,
    LANCAMENTOS_RANGE,
    MOVIMENTACAO_RANGE,
    NOME_ABA_LANCAMENTOS,
    TICKERS_IGNORADOS,
)
from scraper import buscar_proventos, normalizar_data

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ===================== CONSTANTES =====================
LINHA_INICIAL_LANCAMENTOS = 5
COLUNA_VALOR = "D"
COLUNA_VALOR_USD = "O"
COLUNAS_ESCRITA = "A:F"  # data_com, data_pagamento, ativo, valor, descricao, tipo


@dataclass
class Provento:
    """Representa um provento normalizado, com tipagem explícita."""
    data_com: str
    data_pagamento: str
    ativo: str
    valor: str
    descricao: str
    tipo: str
    valor_usd: Optional[float] = None

    @classmethod
    def from_dict(cls, d: dict) -> "Provento":
        return cls(
            data_com=normalizar_data(d.get("data_com", "")) or d.get("data_com", ""),
            data_pagamento=normalizar_data(d.get("data_pagamento", "")) or d.get("data_pagamento", ""),
            ativo=d.get("ativo", "").strip().upper(),
            valor=d.get("valor", ""),
            descricao=d.get("descricao", "").strip(),
            tipo=d.get("tipo", "").strip(),
            valor_usd=d.get("valor_usd"),
        )

    @property
    def chave(self) -> tuple:
        return (self.data_com, self.data_pagamento, self.ativo, self.descricao, self.tipo)

    @property
    def valor_float(self) -> Optional[float]:
        return normalizar_valor(self.valor)


@dataclass
class Atualizacao:
    linha: int
    ativo: str
    valor_antigo: str
    valor_novo: Optional[float]
    valor_usd: Optional[float] = None


def normalizar_valor(valor_str: str | None) -> Optional[float]:
    if not valor_str:
        return None
    valor_limpo = valor_str.replace("R$", "").strip().replace(",", ".")
    try:
        return round(float(valor_limpo), 4)
    except ValueError:
        return None


def _formatar_data_celula(valor) -> str:
    if not valor:
        return ""
    valor_str = str(valor).strip()
    if not valor_str:
        return ""
    return normalizar_data(valor_str) or valor_str


def ler_tickers(service) -> list[str]:
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range=CARTEIRA_RANGE
    ).execute()
    valores = result.get("values", [])

    return [
        linha[0].strip().upper()
        for linha in valores
        if linha and linha[0].strip().upper() not in TICKERS_IGNORADOS and linha[0].strip()
    ]


def ler_lancamentos_existentes(service) -> dict[tuple, dict]:
    """Retorna { chave: {"linha": int, "valor": str} }."""
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range=LANCAMENTOS_RANGE
    ).execute()
    valores = result.get("values", [])

    existentes = {}
    for i, linha in enumerate(valores):
        if len(linha) < 6:
            continue

        chave = (
            _formatar_data_celula(linha[0]),
            _formatar_data_celula(linha[1]),
            linha[2].strip().upper(),
            linha[4].strip(),
            linha[5].strip(),
        )
        existentes[chave] = {
            "linha": LINHA_INICIAL_LANCAMENTOS + i,
            "valor": linha[3],
        }

    return existentes


def separar_novos_e_atualizacoes(
    proventos: list[Provento], existentes: dict[tuple, dict]
) -> tuple[list[Provento], list[Atualizacao]]:
    novos: list[Provento] = []
    atualizacoes: list[Atualizacao] = []

    for p in proventos:
        existente = existentes.get(p.chave)

        if existente is None:
            novos.append(p)
            continue

        valor_novo = p.valor_float
        if existente["valor"] != valor_novo:
            atualizacoes.append(Atualizacao(
                linha=existente["linha"],
                ativo=p.ativo,
                valor_antigo=existente["valor"],
                valor_novo=valor_novo,
                valor_usd=p.valor_usd,
            ))

    return novos, atualizacoes


def _monta_range_usd(linha: int) -> dict:
    return {"range": f"{NOME_ABA_LANCAMENTOS}!{COLUNA_VALOR_USD}{linha}", "values": [[None]]}


def aplicar_atualizacoes(service, atualizacoes: list[Atualizacao]) -> None:
    """Atualiza valor (coluna D) e, quando houver, valor em dólar (coluna O)."""
    if not atualizacoes:
        log.info("Nenhum provento existente precisou de atualização de valor.")
        return

    dados_batch = []
    qtd_usd = 0

    for att in atualizacoes:
        dados_batch.append({
            "range": f"{NOME_ABA_LANCAMENTOS}!{COLUNA_VALOR}{att.linha}",
            "values": [[att.valor_novo]],
        })

        if att.valor_usd is not None:
            dados_batch.append({
                "range": f"{NOME_ABA_LANCAMENTOS}!{COLUNA_VALOR_USD}{att.linha}",
                "values": [[round(att.valor_usd, 6)]],
            })
            qtd_usd += 1

        log.info(
            "ATUALIZADO: %s linha %d -> %s => %s",
            att.ativo, att.linha, att.valor_antigo, att.valor_novo,
        )

    service.spreadsheets().values().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={"valueInputOption": "USER_ENTERED", "data": dados_batch},
    ).execute()

    log.info("%d provento(s) atualizado(s) por mudança de valor.", len(atualizacoes))
    if qtd_usd:
        log.info("%d valor(es) em dólar atualizado(s) na coluna %s.", qtd_usd, COLUNA_VALOR_USD)


def carregar_datas_compra(service) -> dict[str, datetime]:
    """
    Lê MOVIMENTAÇÕES e retorna { 'TICKER': data_inicio_posicao_atual },
    rastreando saldo (Compra soma / Venda subtrai) para achar quando a
    posição ATUAL foi aberta (saldo saiu de 0 para positivo).
    """
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range=MOVIMENTACAO_RANGE
    ).execute()
    linhas = result.get("values", [])

    movimentos = []
    for linha in linhas:
        if len(linha) < 4:
            continue

        tipo_operacao = linha[1].strip().upper()
        if tipo_operacao not in ("COMPRA", "VENDA"):
            continue

        try:
            data = datetime.strptime(linha[0].strip(), "%d/%m/%Y")
            qtd = float(linha[3].strip().replace(",", "."))
        except ValueError:
            continue

        movimentos.append((data, tipo_operacao, linha[2].strip().upper(), qtd))

    movimentos.sort(key=lambda m: m[0])

    saldo: dict[str, float] = {}
    data_inicio_atual: dict[str, datetime] = {}

    for data, tipo, ticker, qtd in movimentos:
        saldo_anterior = saldo.get(ticker, 0)
        saldo[ticker] = saldo_anterior + qtd if tipo == "COMPRA" else saldo_anterior - qtd

        if saldo_anterior <= 0 and saldo[ticker] > 0:
            data_inicio_atual[ticker] = data

    return data_inicio_atual


def filtrar_proventos_por_data_compra(
    proventos: list[Provento], datas_compra: dict[str, datetime]
) -> list[Provento]:
    validos = []

    for p in proventos:
        data_compra = datas_compra.get(p.ativo)
        if data_compra is None:
            validos.append(p)
            continue

        try:
            data_com = datetime.strptime(p.data_com, "%d/%m/%Y")
        except ValueError:
            validos.append(p)
            continue

        if data_com >= data_compra:
            validos.append(p)
        else:
            log.info(
                "IGNORADO: %s - data_com %s anterior à compra (%s)",
                p.ativo, p.data_com, data_compra.strftime("%d/%m/%Y"),
            )

    return validos


def obter_sheet_id(service, nome_aba: str) -> Optional[int]:
    metadata = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    for aba in metadata["sheets"]:
        if aba["properties"]["title"] == nome_aba:
            return aba["properties"]["sheetId"]
    return None


def escrever_proventos(service, proventos: list[Provento]) -> None:
    """Insere os novos proventos na linha 5, empurrando os demais para baixo."""
    if not proventos:
        log.info("Nenhum lançamento novo para adicionar.")
        return

    qtd = len(proventos)
    sheet_id = obter_sheet_id(service, NOME_ABA_LANCAMENTOS)
    if sheet_id is None:
        log.error("Aba '%s' não encontrada.", NOME_ABA_LANCAMENTOS)
        return

    # Insere linhas vazias antes de escrever (evita sobrescrever dados existentes)
    service.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={"requests": [{
            "insertDimension": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "ROWS",
                    "startIndex": LINHA_INICIAL_LANCAMENTOS - 1,
                    "endIndex": LINHA_INICIAL_LANCAMENTOS - 1 + qtd,
                },
                "inheritFromBefore": False,
            }
        }]},
    ).execute()

    valores = [
        [p.data_com, p.data_pagamento, p.ativo, p.valor_float, p.descricao, p.tipo]
        for p in proventos
    ]

    linha_final = LINHA_INICIAL_LANCAMENTOS - 1 + qtd
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{NOME_ABA_LANCAMENTOS}!A{LINHA_INICIAL_LANCAMENTOS}:F{linha_final}",
        valueInputOption="USER_ENTERED",
        body={"values": valores},
    ).execute()

    log.info("%d novo(s) lançamento(s) adicionado(s) na linha %d, empurrando os demais.",
              qtd, LINHA_INICIAL_LANCAMENTOS)

    _gravar_valores_usd(service, proventos, linha_inicial=LINHA_INICIAL_LANCAMENTOS)


def _gravar_valores_usd(service, proventos: list[Provento], linha_inicial: int) -> None:
    """Escreve o valor original em dólar na coluna O, só para quem tiver valor_usd."""
    dados_batch = [
        {
            "range": f"{NOME_ABA_LANCAMENTOS}!{COLUNA_VALOR_USD}{linha_inicial + i}",
            "values": [[round(p.valor_usd, 6)]],
        }
        for i, p in enumerate(proventos)
        if p.valor_usd is not None
    ]

    if not dados_batch:
        return

    service.spreadsheets().values().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={"valueInputOption": "USER_ENTERED", "data": dados_batch},
    ).execute()
    log.info("%d valor(es) em dólar gravado(s) na coluna %s.", len(dados_batch), COLUNA_VALOR_USD)


def main() -> None:
    creds = autenticar_service_account()

    try:
        service = build("sheets", "v4", credentials=creds)

        tickers = ler_tickers(service)
        log.info("Tickers na carteira: %s", tickers)
        if not tickers:
            log.warning("Nenhum ticker encontrado na aba CARTEIRA.")
            return

        proventos_raw = buscar_proventos(tickers)
        log.info("Total de proventos encontrados: %d", len(proventos_raw))
        if not proventos_raw:
            log.warning("Nenhum provento retornado pelo scraper.")
            return

        proventos = [Provento.from_dict(p) for p in proventos_raw]

        existentes = ler_lancamentos_existentes(service)
        novos, atualizacoes = separar_novos_e_atualizacoes(proventos, existentes)

        log.info("Novos lançamentos a inserir: %d", len(novos))
        log.info("Lançamentos a corrigir (valor alterado): %d", len(atualizacoes))

        aplicar_atualizacoes(service, atualizacoes)

        if not novos:
            return

        datas_compra = carregar_datas_compra(service)
        validos = filtrar_proventos_por_data_compra(novos, datas_compra)
        log.info("Lançamentos válidos após conferência de data de compra: %d", len(validos))

        if not validos:
            log.info("Nenhum lançamento válido para adicionar após filtro de data de compra.")
            return

        escrever_proventos(service, validos)

    except HttpError as err:
        log.error("Erro na API do Google Sheets: %s", err)
    except Exception:
        log.exception("Erro inesperado na execução do script.")


if __name__ == "__main__":
    main()
