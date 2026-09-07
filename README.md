# 📊 Carteira de Dividendos

Automação para monitoramento e registro de proventos (dividendos, JCP e rendimentos) de FIIs, ações e ETFs, com integração direta ao Google Sheets e execução automática via GitHub Actions.

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![GitHub Actions](https://img.shields.io/badge/CI-GitHub%20Actions-2088FF?logo=githubactions&logoColor=white)
![Google Sheets API](https://img.shields.io/badge/Google%20Sheets-API-34A853?logo=googlesheets&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green)

---

## 🎯 Sobre o Projeto

Este projeto automatiza a coleta e o registro de proventos de uma carteira de investimentos (FIIs, ações e ETFs nacionais/internacionais), eliminando a necessidade de lançamento manual em planilhas.

**O que ele faz:**
- 🔍 Busca proventos recentes e futuros de cada ativo da carteira
- 💵 Converte valores em dólar (ETFs internacionais) usando cotação de referência do dia
- 📋 Insere novos lançamentos automaticamente no Google Sheets
- 🔄 Detecta e corrige valores desatualizados (ex: proventos com valor estimado que depois é confirmado)
- 📅 Valida `data_com` contra a data de compra do ativo, evitando lançamentos indevidos
- ⚙️ Executa de forma automática e agendada via GitHub Actions

---

## 🛠️ Stack Técnica

| Categoria | Tecnologia |
|---|---|
| Linguagem | Python 3.11 |
| Planilha | Google Sheets API |
| Cotação USD/BRL | API de cotação (AwesomeAPI / Frankfurter) |
| Automação | GitHub Actions (cron) |
| Autenticação | Google Service Account |

---

## 📂 Estrutura do Projeto

\`\`\`
carteira-dividendos-tracker/
├── main.py                    # Ponto de entrada da automação
├── scraper.py                  # Coleta de proventos por ticker
├── cotacao.py                    # Busca cotação USD/BRL
├── sheets_client.py               # Integração com Google Sheets API
├── requirements.txt
├── .env.example
├── .gitignore
└── .github/
    └── workflows/
        └── update.yml           # Workflow de execução automática
\`\`\`

---

## ⚙️ Como Funciona

1. **Leitura da carteira**: obtém a lista de tickers a partir da planilha
2. **Busca de proventos**: para cada ticker, verifica proventos recentes/futuros
3. **Conversão de moeda**: se o ativo for cotado em USD, converte para BRL usando cotação do dia
4. **Comparação e atualização**: verifica se já existe o lançamento e se o dividendo mudou
5. **Validação de data**: ignora proventos com `data_com` anterior à data de compra do ativo
6. **Gravação**: insere novos lançamentos e corrige os que tiveram valor alterado

---

## 🔑 Configurando a Service Account (Google Cloud)

A autenticação é feita via **Service Account**, ideal para automações que rodam sem interação humana (como no GitHub Actions).

### Passo 1 — Criar o projeto no Google Cloud

1. Acesse [console.cloud.google.com](https://console.cloud.google.com/)
2. Clique em **Selecionar projeto → Novo Projeto**
3. Dê um nome (ex: `carteira-dividendos`) e clique em **Criar**

### Passo 2 — Ativar a Google Sheets API

1. No menu lateral, vá em **APIs e Serviços → Biblioteca**
2. Pesquise por **Google Sheets API**
3. Clique em **Ativar**
4. (Opcional) Ative também a **Google Drive API**, caso precise listar/mover arquivos

### Passo 3 — Criar a Service Account

1. Vá em **APIs e Serviços → Credenciais**
2. Clique em **Criar Credenciais → Conta de serviço**
3. Preencha:
   - **Nome**: `sheets-automation`
   - **ID**: gerado automaticamente
4. Clique em **Criar e continuar**
5. Em "Conceder acesso" (papel/role), pode deixar em branco ou usar `Viewer` (o acesso real será dado direto na planilha)
6. Clique em **Concluído**

### Passo 4 — Gerar a chave JSON

1. Na lista de contas de serviço, clique na que você criou
2. Vá na aba **Chaves**
3. Clique em **Adicionar Chave → Criar nova chave**
4. Selecione **JSON** e clique em **Criar**
5. O arquivo `.json` será baixado automaticamente — **guarde-o com segurança, nunca commite ele!**

O arquivo terá esse formato:

\`\`\`json
{
  "type": "service_account",
  "project_id": "carteira-dividendos",
  "private_key_id": "...",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
  "client_email": "sheets-automation@carteira-dividendos.iam.gserviceaccount.com",
  "client_id": "...",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token"
}
\`\`\`

### Passo 5 — Compartilhar a planilha com a Service Account

1. Copie o valor de `client_email` do JSON (ex: `sheets-automation@carteira-dividendos.iam.gserviceaccount.com`)
2. Abra sua planilha no Google Sheets
3. Clique em **Compartilhar**
4. Cole o e-mail da Service Account e conceda permissão de **Editor**
5. Clique em **Enviar** (não precisa marcar "notificar", pois é uma conta de serviço)

### Passo 6 — Usar a credencial no código

\`\`\`python
# sheets_client.py
import gspread
from google.oauth2.service_account import Credentials
import os
import json

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

def conectar_planilha():
    credenciais_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")

    if credenciais_json:
        # Usado no GitHub Actions (via Secret)
        info = json.loads(credenciais_json)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        # Usado localmente (arquivo físico)
        creds = Credentials.from_service_account_file(
            os.environ.get("GOOGLE_CREDENTIALS_PATH", "credentials.json"),
            scopes=SCOPES
        )

    client = gspread.authorize(creds)
    spreadsheet_id = os.environ.get("SPREADSHEET_ID")
    return client.open_by_key(spreadsheet_id)
\`\`\`

---

## 🚀 Como Rodar Localmente

### 1. Clone o repositório
\`\`\`bash
git clone https://github.com/SEU_USUARIO/carteira-dividendos.git
cd carteira-dividendos-tracker
\`\`\`

### 2. Crie o ambiente virtual e instale as dependências
\`\`\`bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
\`\`\`

### 3. Configure as variáveis de ambiente
\`\`\`bash
cp .env.example .env
\`\`\`

Edite o `.env`:
\`\`\`env
SPREADSHEET_ID=seu_id_da_planilha_aqui
GOOGLE_CREDENTIALS_PATH=credentials.json
\`\`\`

### 4. Coloque o `credentials.json` (da Service Account) na raiz do projeto
> ⚠️ Esse arquivo **nunca** deve ser commitado. Ele já está no `.gitignore`.

### 5. Execute
\`\`\`bash
python main.py
\`\`\`

---

## 🤖 Automação via GitHub Actions

O workflow roda a automação em intervalos programados, sem precisar de máquina local ligada.

### Passo 1 — Configurar os Secrets no repositório

1. No GitHub, vá em **Settings → Secrets and variables → Actions**
2. Clique em **New repository secret** e crie:

| Nome do Secret | Valor |
|---|---|
| `SPREADSHEET_ID` | ID da sua planilha (está na URL do Google Sheets) |
| `GOOGLE_CREDENTIALS_JSON` | Conteúdo **completo** do arquivo `credentials.json` (copie e cole o JSON inteiro) |

> 💡 Para pegar o `SPREADSHEET_ID`: na URL `https://docs.google.com/spreadsheets/d/AQUI_ESTA_O_ID/edit`, copie a parte entre `/d/` e `/edit`.

### Passo 2 — Workflow (`.github/workflows/update.yml`)

\`\`\`yaml
name example: Atualizar Proventos

on:
  schedule:
    # Roda todos os dias às 09:00 e 21:00 (horário de Brasília, UTC-3)
    - cron: '0 12,0 * * *'
  workflow_dispatch:  # permite rodar manualmente pela interface do GitHub

jobs:
  atualizar:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout do código
        uses: actions/checkout@v4

      - name: Configurar Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Instalar dependências
        run: pip install -r requirements.txt

      - name: Executar automação
        env:
          SPREADSHEET_ID: \${{ secrets.SPREADSHEET_ID }}
          GOOGLE_CREDENTIALS_JSON: \${{ secrets.GOOGLE_CREDENTIALS_JSON }}
        run: python main.py
\`\`\`

### Passo 3 — Testar manualmente (opcional)

1. Vá na aba **Actions** do repositório
2. Selecione o workflow **Atualizar Proventos**
3. Clique em **Run workflow** para testar sem esperar o cron

### 📌 Sobre o `cron`

O GitHub Actions usa **UTC**. Para converter para horário de Brasília (UTC-3):

| Quer rodar às (Brasília) | Cron (UTC) |
|---|---|
| 09:00 | `0 12 * * *` |
| 21:00 | `0 0 * * *` |
| A cada 6 horas | `0 */6 * * *` |

Use [crontab.guru](https://crontab.guru/) para gerar/validar expressões.

---

## 📌 Roadmap / Melhorias Futuras

- [ ] Aba de ativos retornando o valor teto de um ativo para saber melhor hora da compra
- [ ] Suporte a múltiplas carteiras/planilhas
- [ ] Dashboard de visualização (Streamlit ou Google Data Studio)
- [ ] Notificação via Telegram/WhatsApp de novos proventos

---

## ⚠️ Aviso

Este projeto é para fins **educacionais e de organização pessoal de finanças**. Não constitui recomendação de investimento.

---

## 📄 Licença

MIT License — sinta-se livre para usar, adaptar e contribuir.
