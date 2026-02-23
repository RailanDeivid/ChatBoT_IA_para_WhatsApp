# ChatBot IA para WhatsApp

Chatbot de WhatsApp com inteligência artificial que responde perguntas sobre **vendas** e **compras** consultando bancos de dados em tempo real.

O agente entende a pergunta do usuário, decide qual banco de dados acessar (Dremio ou MySQL) e retorna uma resposta em linguagem natural via WhatsApp.

---

## Funcionalidades

- Recebe mensagens do WhatsApp via **Evolution API**
- Agrupa mensagens enviadas em sequência (debounce de 3 segundos)
- Roteamento automático de perguntas:
  - **Vendas / faturamento** → consulta o **Dremio** (`views."financial_sales_testes"`)
  - **Compras / pedidos** → consulta o **MySQL** (`` `505 COMPRA` ``)
- Memória de conversa por usuário (histórico das últimas 10 mensagens)
- Ignora mensagens de grupos automaticamente

---

## Stack de Tecnologias

| Camada | Tecnologia |
|---|---|
| Web / API | FastAPI + Uvicorn |
| IA / LLM | OpenAI GPT-4o via LangChain |
| Orquestração | LangChain ReAct Agent |
| Banco de Dados (Vendas) | Dremio (REST API) |
| Banco de Dados (Compras) | MySQL 8.0 |
| Cache / Memória | Redis |
| Gateway WhatsApp | Evolution API |
| Infraestrutura | Docker + Docker Compose |

---

## Estrutura do Projeto

```
ChatBoT_IA_para_WhatsApp/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env                        # Variáveis de ambiente (não versionado)
└── src/
    ├── app.py                  # Webhook FastAPI — ponto de entrada das mensagens
    ├── message_buffer.py       # Debounce e agrupamento de mensagens (Redis)
    ├── chains.py               # Agente LangChain ReAct + orquestração
    ├── config.py               # Leitura centralizada das variáveis de ambiente
    ├── prompts.py              # Template do prompt do sistema
    ├── memory.py               # Histórico de conversa por sessão (Redis)
    ├── evolution_api.py        # Envio de mensagens de volta ao WhatsApp
    ├── dremio_connector.py     # Conector Dremio via REST API → retorna DataFrame
    ├── dremio_tools.py         # Tool LangChain para consultas de VENDAS (Dremio)
    ├── mysql_connector.py      # Conector MySQL → retorna DataFrame
    └── mysql_tools.py          # Tool LangChain para consultas de COMPRAS (MySQL)
```

### Responsabilidade de cada arquivo

| Arquivo | O que faz |
|---|---|
| `app.py` | Recebe POST do Evolution API no `/webhook`, extrai `chat_id` e `message`, descarta grupos |
| `message_buffer.py` | Armazena mensagens no Redis e dispara o agente após 3s de silêncio |
| `chains.py` | Monta o agente ReAct com as duas tools e gerencia histórico de conversa |
| `config.py` | Carrega todas as variáveis do `.env` em constantes Python |
| `prompts.py` | Cria o `PromptTemplate` com o prompt definido no `.env` |
| `memory.py` | Retorna o histórico Redis por `session_id` (= `chat_id`) |
| `evolution_api.py` | Faz POST na Evolution API para enviar a resposta ao WhatsApp |
| `dremio_connector.py` | Autentica no Dremio, envia SQL, aguarda job, retorna `pd.DataFrame` |
| `dremio_tools.py` | `DremioSalesQueryTool` — tool do agente para perguntas de vendas |
| `mysql_connector.py` | Conecta no MySQL, executa SQL, retorna `pd.DataFrame` |
| `mysql_tools.py` | `MySQLPurchasesQueryTool` — tool do agente para perguntas de compras |

---

## Fluxo Completo — Do WhatsApp à Resposta

```
┌──────────────────────────────────────────────────────────────┐
│  Usuário WhatsApp                                            │
│  "Quanto vendemos em janeiro?"                               │
└──────────────────────────┬───────────────────────────────────┘
                           │  webhook POST
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  Evolution API  (porta 8080)                                 │
│  Gateway que recebe e repassa mensagens do WhatsApp          │
└──────────────────────────┬───────────────────────────────────┘
                           │  POST /webhook
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  app.py — Webhook FastAPI  (porta 8000)                      │
│  • Extrai chat_id e message do JSON                          │
│  • Filtra grupos (@g.us) — ignora se for grupo               │
│  • Chama buffer_message(chat_id, message)                    │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  message_buffer.py — Debounce Redis                          │
│  • Armazena mensagem na lista Redis: {chat_id}:buffer        │
│  • Inicia timer de 3 segundos                                │
│  • Se nova mensagem chegar → reseta o timer                  │
│  • Após 3s de silêncio → combina todas as mensagens          │
│    e chama invoke_sql_agent(mensagem_combinada, chat_id)      │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  chains.py — invoke_sql_agent()                              │
│                                                              │
│  1. Busca histórico no Redis (últimas 10 mensagens)          │
│  2. Monta prompt:                                            │
│     [system_prompt] + [pergunta] + [histórico]               │
│  3. Passa para o AgentExecutor                               │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  LangChain ReAct Agent — GPT-4o                              │
│                                                              │
│  Loop de raciocínio:                                         │
│                                                              │
│  Thought: "Pergunta é sobre vendas"                          │
│  Action:  consultar_vendas                                   │
│  Input:   SELECT ... FROM views."financial_sales_testes"     │
│                          │                                   │
│                          ▼                                   │
│         ┌────────────────────────────────┐                   │
│         │  DremioSalesQueryTool          │                   │
│         │  → dremio_connector.client()   │                   │
│         │  → Dremio REST API             │                   │
│         │  → pd.DataFrame                │                   │
│         └────────────────────────────────┘                   │
│                          │                                   │
│  Observation: [dados do DataFrame]                           │
│                                                              │
│  Thought: "Tenho os dados, posso responder"                  │
│  Final Answer: "Em janeiro foram vendidos R$ 45.230,00"      │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           │  (se fosse compras)
                           │  ┌────────────────────────────────┐
                           │  │  MySQLPurchasesQueryTool       │
                           │  │  → mysql_connector.client()    │
                           │  │  → MySQL `505 COMPRA`          │
                           │  │  → pd.DataFrame                │
                           │  └────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  chains.py — Pós processamento                               │
│  • Salva pergunta no Redis (histórico)                       │
│  • Salva resposta no Redis (histórico)                       │
│  • Retorna resposta para message_buffer.py                   │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  evolution_api.py                                            │
│  send_whatsapp_message(chat_id, resposta)                    │
│  POST → Evolution API → WhatsApp                             │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  Usuário WhatsApp                                            │
│  "Em janeiro foram vendidos R$ 45.230,00..."                 │
└──────────────────────────────────────────────────────────────┘
```

---

## Roteamento de Perguntas pelo Agente

O GPT-4o lê a `description` de cada tool e decide automaticamente qual banco consultar:

| Tipo de pergunta | Tool ativada | Banco | Tabela |
|---|---|---|---|
| Vendas, faturamento, receita, financeiro | `consultar_vendas` | Dremio | `views."financial_sales_testes"` |
| Compras, pedidos, fornecedores | `consultar_compras` | MySQL | `` `505 COMPRA` `` |

---

## Serviços Docker

```
docker-compose up --build
```

| Serviço | Imagem | Porta | Descrição |
|---|---|---|---|
| `bot` | Build local | 8000 | Aplicação principal |
| `evolution-api` | atendai/evolution-api | 8080 | Gateway WhatsApp |
| `redis` | redis:latest | 6379 | Buffer de mensagens + histórico |
| `db` | mysql:8.0 | 3306 | Banco de dados de compras |
| `postgres` | postgres:15 | 5432 | Banco interno da Evolution API |

---

## Configuração — Arquivo `.env`

```env
# Evolution API
EVOLUTION_API_URL=http://evolution-api:8080
EVOLUTION_INSTANCE_NAME=sua_instancia
AUTHENTICATION_API_KEY=sua_api_key

# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL_NAME=gpt-4o
OPENAI_MODEL_TEMPERATURE=0.3

# Prompt do sistema (use {q} como placeholder da pergunta)
AI_SYSTEM_PROMPT=Você é um assistente especialista em dados de restaurantes e bares. Responda com base nos dados dos bancos de dados. Pergunta: {q}

# Redis
CACHE_REDIS_URI=redis://redis:6379
BUFFER_KEY_SUFIX=:buffer
DEBOUNCE_SECONDS=3
BUFFER_TTL=300

# MySQL
DB_HOST=db
DB_PORT=3306
DB_USER=root
DB_PASSWORD=sua_senha
DB_NAME=seu_banco

# Dremio
DREMIO_HOST=seu_host_dremio
DREMIO_USER=seu_usuario
DREMIO_PASSWORD=sua_senha
```

---

## Como Executar

### Pré-requisitos
- Docker e Docker Compose instalados
- Arquivo `.env` configurado (veja seção acima)
- Instância do Dremio acessível com a tabela `views."financial_sales_testes"`
- Banco MySQL populado com a tabela `505 COMPRA`

### Subir os serviços

```bash
docker-compose up --build
```

### Configurar o Webhook na Evolution API

Após subir os serviços, configure o webhook na Evolution API apontando para:

```
http://bot:8000/webhook
```

---

## Variáveis de Configuração

| Variável | Descrição | Padrão |
|---|---|---|
| `DEBOUNCE_SECONDS` | Segundos de espera para agrupar mensagens | `3` |
| `BUFFER_TTL` | Tempo de vida do buffer no Redis (segundos) | `300` |
| `OPENAI_MODEL_TEMPERATURE` | Criatividade do modelo (0 = preciso, 1 = criativo) | `0.3` |
| `OPENAI_MODEL_NAME` | Modelo OpenAI utilizado | `gpt-4o` |
