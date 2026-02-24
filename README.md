# ChatBot IA para WhatsApp

Assistente inteligente integrado ao WhatsApp que responde perguntas de negócio consultando dados em tempo real via Dremio (vendas) e MySQL (compras).

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
│  • Armazena mensagem na lista Redis: {chat_id}_msg_buffer    │
│  • Inicia timer de 3 segundos (asyncio.create_task)          │
│  • Se nova mensagem chegar → cancela e recria o timer        │
│  • Após 3s de silêncio → combina todas as mensagens          │
│    e chama invoke_sql_agent via run_in_executor              │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  chains.py — invoke_sql_agent()                              │
│                                                              │
│  1. Busca histórico no Redis (últimas 6 mensagens)           │
│  2. Monta prompt:                                            │
│     [histórico] + [system_prompt NINOIA] + [pergunta]        │
│  3. Passa para o AgentExecutor (handle_parsing_errors=True)  │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  LangChain ReAct Agent — GPT-4o                              │
│                                                              │
│  Loop de raciocínio:                                         │
│  Thought → Action → Observation → Final Answer              │
│                                                              │
│  Classifica a intenção e aciona a ferramenta adequada        │
└──────────────┬────────────────────────────────┬──────────────┘
               │                                │
  Pergunta de  │                                │  Pergunta de
    Vendas     │                                │    Compras
               ▼                                ▼
┌──────────────────────────┐    ┌───────────────────────────────┐
│  DremioSalesQueryTool    │    │  MySQLPurchasesQueryTool      │
│                          │    │                               │
│  → dremio.client()       │    │  → mysql.client()             │
│  → token cacheado        │    │  → MySQL `tabela_compras`     │
│  → Dremio REST API       │    │  → pd.DataFrame               │
│  → pd.DataFrame          │    │    → to_string()              │
│    → to_string()         │    └──────────────┬────────────────┘
└────────────┬─────────────┘                   │
             │                                 │
             └─────────────────┬───────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│  chains.py — Pós processamento                               │
│  • Salva pergunta no Redis (histórico por session_id)        │
│  • Salva resposta no Redis (histórico por session_id)        │
│  • Retorna resposta para message_buffer.py                   │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  integrations/evolution_api.py                               │
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

## Estrutura do projeto

```
ChatBoT_IA_para_WhatsApp/
├── src/
│   ├── app.py                      # FastAPI — endpoint /webhook
│   ├── chains.py                   # Agente LangChain ReAct + invoke_sql_agent
│   ├── config.py                   # Leitura das variáveis de ambiente (.env)
│   ├── memory.py                   # Histórico de conversa via Redis
│   ├── message_buffer.py           # Buffer de mensagens com debounce
│   ├── prompts.py                  # Prompt do agente NINOIA
│   ├── connectors/
│   │   ├── dremio.py               # Conector REST API Dremio → DataFrame
│   │   └── mysql.py                # Conector MySQL → DataFrame
│   ├── tools/
│   │   ├── dremio_tools.py         # Tool LangChain: consultar_vendas
│   │   └── mysql_tools.py          # Tool LangChain: consultar_compras
│   └── integrations/
│       └── evolution_api.py        # Envio de mensagem via Evolution API
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env
```

---

## Serviços Docker

| Serviço | Imagem | Porta | Função |
|---|---|---|---|
| `bot` | build local | 8000 | FastAPI + Agente IA |
| `evolution_api` | evoapicloud/evolution-api:latest | 8080 | Gateway WhatsApp |
| `postgres` | postgres:15 | 5432 | Banco de dados da Evolution API |
| `redis` | redis:latest | 6379 | Buffer de mensagens + histórico de conversa |

**Bases de dados externas** (não sobem no Docker):

| Banco | Função |
|---|---|
| Dremio | Dados de vendas — `views."tabela_vendas"` |
| MySQL | Dados de compras — tabela `` `tabela_compras` `` |

### Exemplo do docker-compose.yml

```yaml
services:

  # ── Evolution API (Gateway WhatsApp) ───────────────────────────
  evolution-api:
    container_name: evolution_api
    image: evoapicloud/evolution-api:latest
    restart: always
    ports:
      - "8080:8080"                    # Painel de administração e recebimento de webhooks
    env_file:
      - .env
    volumes:
      - evolution_instances:/evolution/instances   # Persiste instâncias do WhatsApp
    depends_on:
      - postgres
      - redis

  # ── PostgreSQL (banco de dados interno da Evolution API) ───────
  postgres:
    container_name: postgres
    image: postgres:15
    command: ["postgres", "-c", "max_connections=1000"]   # Aumenta limite de conexões
    restart: always
    ports:
      - 5432:5432
    environment:
      - POSTGRES_PASSWORD=postgres
    volumes:
      - postgres_data:/var/lib/postgresql/data   # Persiste os dados entre restarts
    expose:
      - 5432

  # ── Redis (buffer de mensagens + histórico de conversa) ────────
  redis:
    image: redis:latest
    container_name: redis
    command: >
      redis-server --port 6379 --appendonly yes   # Habilita persistência AOF
    volumes:
      - redis:/data
    ports:
      - 6379:6379

  # ── Bot IA ─────────────────────────────────────────────────────
  bot:
    build: .                           # Usa o Dockerfile local para buildar a imagem
    container_name: bot
    ports:
      - "8000:8000"                    # FastAPI exposta em localhost:8000
    env_file:
      - .env
    depends_on:
      - evolution-api
      - redis
    restart: always

volumes:
  evolution_instances:   # Instâncias e sessões do WhatsApp
  postgres_data:         # Banco de dados da Evolution API
  redis:                 # Dados persistidos do Redis (AOF)
```

---

## Ferramentas do agente

### `consultar_vendas` — Dremio
Usada para perguntas sobre faturamento, receita e desempenho de vendas.

| Coluna | Tipo | Descrição |
|---|---|---|
| `codigo_casa` | TEXT | Nome do estabelecimento |
| `data_evento` | DATE | Data da venda |
| `descricao_produto` | TEXT | Nome do produto vendido |
| `quantidade` | FLOAT | Quantidade vendida |
| `valor_produto` | DOUBLE | Valor unitário |
| `nome_funcionario` | TEXT | Nome do funcionário |
| `valor_liquido_final` | DOUBLE | Valor líquido final (use para totais) |
| `distribuicao_pessoas` | FLOAT | Somar para obter Fluxo de clientes |

### `consultar_compras` — MySQL
Usada para perguntas sobre pedidos de compra e fornecedores.

| Coluna | Tipo | Descrição |
|---|---|---|
| `` `Fantasia` `` | TEXT | Nome fantasia da empresa |
| `` `D. Lançamento` `` | DATE | Data da nota fiscal |
| `` `N. Nota` `` | BIGINT | Número da nota fiscal |
| `` `Razão Emitente` `` | TEXT | Razão social do fornecedor |
| `` `Descrição Item` `` | TEXT | Nome do produto comprado |
| `` `Grupo` `` | TEXT | Grupo do produto |
| `` `V. Total` `` | DECIMAL | Valor total da compra |

---

## Configuração (.env)

```env
# Python
PYTHONDONTWRITEBYTECODE=1
PYTHONUNBUFFERED=1

# Evolution API (WhatsApp)
EVOLUTION_API_URL=http://evolution-api:8080
EVOLUTION_INSTANCE_NAME=instace_name
AUTHENTICATION_API_KEY=sua_api_key

# OpenAI
OPENAI_API_KEY=token
OPENAI_MODEL_NAME=gpt-4o
OPENAI_MODEL_TEMPERATURE=0.3

# Redis — Bot
BOT_REDIS_URI=redis://redis:6379/0
BUFFER_KEY_SUFIX=_msg_buffer
DEBOUNCE_SECONDS=3
BUFFER_TTL=300

# Redis — Evolution API
CACHE_REDIS_ENABLED=true
CACHE_REDIS_URI=redis://redis:6379/0
CACHE_REDIS_PREFIX_KEY=evolution
CACHE_REDIS_SAVE_INSTANCES=false
CACHE_LOCAL_ENABLED=false

# PostgreSQL (Evolution API)
DATABASE_ENABLED=true
DATABASE_PROVIDER=postgresql
DATABASE_CONNECTION_URI=postgresql://postgres:postgres@postgres:5432/evolution?schema=public
DATABASE_CONNECTION_CLIENT_NAME=evolution_exchange
DATABASE_SAVE_DATA_INSTANCE=true
DATABASE_SAVE_DATA_NEW_MESSAGE=true
DATABASE_SAVE_MESSAGE_UPDATE=true
DATABASE_SAVE_DATA_CONTACTS=true
DATABASE_SAVE_DATA_CHATS=true
DATABASE_SAVE_DATA_LABELS=true
DATABASE_SAVE_DATA_HISTORIC=true

# MySQL (externo)
DB_HOST=seu_host_mysql
DB_PORT=3306
DB_USER=seu_usuario
DB_PASSWORD=sua_senha
DB_NAME=seu_banco

# Dremio (externo)
DREMIO_HOST=seu_host:9047
DREMIO_USER=seu_usuario
DREMIO_PASSWORD=sua_senha
```

---

## Subir o projeto

```bash
# Primeira vez ou após mudanças no código
docker-compose up --build -d

# Reiniciar sem rebuild (apenas após mudanças no .env)
docker-compose up -d

# Ver logs em tempo real
docker logs bot -f

# Ver logs de todos os serviços
docker-compose logs -f

# Últimas 100 linhas
docker logs bot --tail 100
```

---

## Logs de startup esperados

```
# Inicialização do servidor
INFO:     Started server process [1]
INFO:     Waiting for application startup.

# Carregamento do agente (chains.py)
[CHAINS] Carregando modelo e ferramentas...
[CHAINS] Modelo configurado: gpt-4o  |  temperature=0.3
[CHAINS] Ferramentas registradas: consultar_vendas, consultar_compras
[CHAINS] Baixando prompt do LangChain Hub...
[CHAINS] Prompt carregado com sucesso.
[CHAINS] Criando AgentExecutor (ReAct + handle_parsing_errors=True)...
[CHAINS] Agente pronto. ✓

# Servidor disponível para receber mensagens
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

## Logs ao receber mensagem

```
# 1. Webhook recebe a mensagem do WhatsApp
INFO:     POST /webhook HTTP/1.1  200 OK
[WEBHOOK] Mensagem recebida de 55119...@s.whatsapp.net: "Quanto vendemos em janeiro?"

# 2. Buffer de debounce — aguarda 3s por mensagens adicionais
[BUFFER] Mensagem adicionada ao buffer de 55119...@s.whatsapp.net
[BUFFER] Timer de debounce iniciado: 3s
[BUFFER] Nenhuma nova mensagem recebida. Disparando processamento...
[BUFFER] Mensagem combinada enviada ao agente: "Quanto vendemos em janeiro?"

# 3. Agente ReAct em execução (chains.py)
> Entering new AgentExecutor chain...

Thought: O usuário quer saber o total de vendas de janeiro. Preciso consultar o Dremio.
Action: consultar_vendas
Action Input: SELECT SUM(valor_liquido_final) AS total FROM views."tabela_vendas" WHERE MONTH(data_evento) = 1

Observation:
      total
   45230.00

Thought: Tenho o valor total. Posso formatar e responder ao usuário.
Final Answer: Em janeiro foram vendidos R$ 45.230,00.

> Finished chain.

# 4. Resposta enviada de volta ao WhatsApp
[BUFFER] Resposta do agente para 55119...@s.whatsapp.net: "Em janeiro foram vendidos R$ 45.230,00."
[EVOLUTION] Mensagem enviada com sucesso → 55119...@s.whatsapp.net
```

---

## Personalidade e regras do agente

O comportamento do agente está definido em [src/prompts.py](src/prompts.py). Para alterar a personalidade, regras ou instruções do NINOIA, edite o `SYSTEM_PROMPT` diretamente — sem precisar mexer no `.env`.

Regras configuradas:
- Nunca revela detalhes técnicos (tabelas, bancos, ferramentas) ao usuário
- Sempre consulta as ferramentas para cada pergunta — não reutiliza respostas anteriores
- Responde exclusivamente em português
- Perguntas fora do escopo retornam: *"Não tenho acesso a essas informações"*
- Se apresenta pelo nome **NINOIA** ao cumprimentar
- Chama o usuário pelo nome do WhatsApp quando disponível

---

## Modelos OpenAI compatíveis

Use modelos da família **chat** (não reasoning):

| Modelo | Indicado para |
|---|---|
| `gpt-4o` | Produção — melhor aderência ao formato ReAct e geração de SQL |
| `gpt-4-turbo` | Alternativa ao gpt-4o |
| `gpt-4o-mini` | Testes — mais rápido/barato, menor confiabilidade no ReAct |

> **Evite modelos da série `o`** (`o1`, `o3`, `o4-mini`) — não suportam o parâmetro `temperature` e não seguem o formato ReAct do LangChain.
