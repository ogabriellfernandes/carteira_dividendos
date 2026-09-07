from datetime import datetime

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


def normalizar_valor(valor_str: str) -> float | None:
    valor_limpo = valor_str.replace("R$", "").strip().replace(",", ".")
    try:
        return round(float(valor_limpo), 4)
    except ValueError:
        return None


def _formatar_data_celula(valor) -> str:
    if valor is None:
        return ""
    valor_str = str(valor).strip()
    if not valor_str:
        return ""
    normalizado = normalizar_data(valor_str)
    return normalizado or valor_str


def ler_tickers(service):
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=CARTEIRA_RANGE
    ).execute()
    valores = result.get("values", [])

    tickers = []
    for linha in valores:
        if not linha:
            continue
        ticker = linha[0].strip().upper()
        if ticker and ticker not in TICKERS_IGNORADOS:
            tickers.append(ticker)

    return tickers


def ler_lancamentos_existentes(service):
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=LANCAMENTOS_RANGE
    ).execute()
    valores = result.get("values", [])

    existentes = {}
    linha_inicial = 5

    for i, linha in enumerate(valores):
        if len(linha) >= 6:
            data_com = _formatar_data_celula(linha[0])
            data_pagamento = _formatar_data_celula(linha[1])
            ativo = linha[2].strip().upper()
            valor = linha[3]
            descricao = linha[4].strip()
            tipo = linha[5].strip()

            chave = (data_com, data_pagamento, ativo, descricao, tipo)
            numero_linha = linha_inicial + i

            existentes[chave] = {"linha": numero_linha, "valor": valor}

    return existentes


def separar_novos_e_atualizacoes(proventos, existentes):
    novos = []
    atualizacoes = []

    for p in proventos:
        valor_normalizado = normalizar_valor(p["valor"])

        data_com = normalizar_data(p["data_com"]) or p["data_com"]
        data_pagamento = normalizar_data(p["data_pagamento"]) or p["data_pagamento"]
        ativo = p["ativo"].strip().upper()
        descricao = p["descricao"].strip()
        tipo = p["tipo"].strip()

        chave = (data_com, data_pagamento, ativo, descricao, tipo)

        if chave in existentes:
            valor_existente = existentes[chave]["valor"]
            if valor_existente != valor_normalizado:
                atualizacoes.append({
                    "linha": existentes[chave]["linha"],
                    "valor_novo": valor_normalizado,
                    "ativo": ativo,
                    "valor_antigo": valor_existente,
                    "valor_usd": p.get("valor_usd"),
                })
        else:
            novos.append(p)

    return novos, atualizacoes


def aplicar_atualizacoes(service, atualizacoes):
    """Atualiza valor (coluna D) e, quando houver, valor em dólar (coluna O)."""
    if not atualizacoes:
        print("Nenhum provento existente precisou de atualização de valor.")
        return

    dados_batch = []
    qtd_usd = 0

    for att in atualizacoes:
        linha = att["linha"]
        dados_batch.append({
            "range": f"{NOME_ABA_LANCAMENTOS}!D{linha}",
            "values": [[att["valor_novo"]]]
        })

        if att.get("valor_usd") is not None:
            dados_batch.append({
                "range": f"{NOME_ABA_LANCAMENTOS}!O{linha}",
                "values": [[round(att["valor_usd"], 6)]]
            })
            qtd_usd += 1

        print(
            f"ATUALIZADO: {att['ativo']} linha {linha} "
            f"-> {att['valor_antigo']} => {att['valor_novo']}"
        )

    service.spreadsheets().values().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={"valueInputOption": "USER_ENTERED", "data": dados_batch}
    ).execute()

    print(f"{len(atualizacoes)} provento(s) atualizado(s) por mudança de valor.")
    if qtd_usd:
        print(f"{qtd_usd} valor(es) em dólar atualizado(s) na coluna O.")


def carregar_datas_compra(service):
    """
    Lê MOVIMENTAÇÕES e retorna { 'TICKER': data_inicio_posicao_atual (datetime) },
    rastreando saldo (Compra soma / Venda subtrai) para achar quando a posição
    ATUAL foi aberta (saldo saiu de 0 para positivo).
    """
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=MOVIMENTACAO_RANGE
    ).execute()
    linhas = result.get("values", [])

    movimentos = []
    for linha in linhas:
        if len(linha) < 4:
            continue

        data_str = linha[0].strip()
        tipo_operacao = linha[1].strip().upper()
        ticker = linha[2].strip().upper()
        qtd_str = linha[3].strip().replace(",", ".")

        if tipo_operacao not in ("COMPRA", "VENDA"):
            continue

        try:
            data = datetime.strptime(data_str, "%d/%m/%Y")
            qtd = float(qtd_str)
        except ValueError:
            continue

        movimentos.append((data, tipo_operacao, ticker, qtd))

    movimentos.sort(key=lambda m: m[0])

    saldo = {}
    data_inicio_atual = {}

    for data, tipo, ticker, qtd in movimentos:
        saldo_anterior = saldo.get(ticker, 0)
        saldo[ticker] = saldo_anterior + qtd if tipo == "COMPRA" else saldo_anterior - qtd

        if saldo_anterior <= 0 and saldo[ticker] > 0:
            data_inicio_atual[ticker] = data

    return data_inicio_atual


def filtrar_proventos_por_data_compra(proventos, datas_compra):
    proventos_validos = []

    for p in proventos:
        ticker = p["ativo"].strip().upper()
        data_compra = datas_compra.get(ticker)

        if data_compra is None:
            proventos_validos.append(p)
            continue

        try:
            data_com = datetime.strptime(p["data_com"], "%d/%m/%Y")
        except ValueError:
            proventos_validos.append(p)
            continue

        if data_com >= data_compra:
            proventos_validos.append(p)
        else:
            print(
                f"IGNORADO: {ticker} - data_com {p['data_com']} "
                f"anterior à compra ({data_compra.strftime('%d/%m/%Y')})"
            )

    return proventos_validos


def obter_sheet_id(service, nome_aba):
    metadata = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    for aba in metadata["sheets"]:
        if aba["properties"]["title"] == nome_aba:
            return aba["properties"]["sheetId"]
    return None


def escrever_proventos(service, proventos):
    """Insere os novos proventos na linha 5, empurrando os demais para baixo."""
    if not proventos:
        print("Nenhum lançamento novo para adicionar.")
        return

    valores = [
        [
            p["data_com"],
            p["data_pagamento"],
            p["ativo"],
            normalizar_valor(p["valor"]),
            p["descricao"],
            p["tipo"]
        ]
        for p in proventos
    ]

    qtd = len(valores)

    sheet_id = obter_sheet_id(service, NOME_ABA_LANCAMENTOS)
    if sheet_id is None:
        print(f"ERRO: aba '{NOME_ABA_LANCAMENTOS}' não encontrada.")
        return

    requests = [{
        "insertDimension": {
            "range": {
                "sheetId": sheet_id,
                "dimension": "ROWS",
                "startIndex": 4,
                "endIndex": 4 + qtd
            },
            "inheritFromBefore": False
        }
    }]

    service.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={"requests": requests}
    ).execute()

    range_escrita = f"{NOME_ABA_LANCAMENTOS}!A5:F{4 + qtd}"

    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=range_escrita,
        valueInputOption="USER_ENTERED",
        body={"values": valores}
    ).execute()

    print(f"{qtd} novo(s) lançamento(s) adicionado(s) na linha 5, empurrando os demais.")

    dados_batch_usd = []
    for i, p in enumerate(proventos):
        if p.get("valor_usd") is not None:
            linha_atual = 5 + i
            dados_batch_usd.append({
                "range": f"{NOME_ABA_LANCAMENTOS}!O{linha_atual}",
                "values": [[round(p["valor_usd"], 6)]]
            })

    if dados_batch_usd:
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body={"valueInputOption": "USER_ENTERED", "data": dados_batch_usd}
        ).execute()
        print(f"{len(dados_batch_usd)} valor(es) em dólar gravado(s) na coluna O.")


def main():
    creds = autenticar_service_account()

    try:
        service = build("sheets", "v4", credentials=creds)

        tickers = ler_tickers(service)
        print(f"Tickers na carteira: {tickers}")

        if not tickers:
            print("Nenhum ticker encontrado na aba CARTEIRA.")
            return

        proventos = buscar_proventos(tickers)
        print(f"\nTotal de proventos encontrados: {len(proventos)}")

        if not proventos:
            print("Nenhum provento retornado pelo scraper.")
            return

        existentes = ler_lancamentos_existentes(service)

        novos, atualizacoes = separar_novos_e_atualizacoes(proventos, existentes)
        print(f"Novos lançamentos a inserir: {len(novos)}")
        print(f"Lançamentos a corrigir (valor alterado): {len(atualizacoes)}")

        aplicar_atualizacoes(service, atualizacoes)

        if not novos:
            print("Nenhum lançamento novo para adicionar.")
            return

        datas_compra = carregar_datas_compra(service)
        validos = filtrar_proventos_por_data_compra(novos, datas_compra)
        print(f"Lançamentos válidos após conferência de data de compra: {len(validos)}")

        if not validos:
            print("Nenhum lançamento válido para adicionar após filtro de data de compra.")
            return

        escrever_proventos(service, validos)

    except HttpError as err:
        print(err)


if __name__ == "__main__":
    main()
