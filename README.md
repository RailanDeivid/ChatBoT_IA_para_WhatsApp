# whatsapp-agent

Assistente inteligente integrado ao WhatsApp com um agente ReAct (GPT-4o) que, dependendo da intenção da pergunta, aciona a ferramenta especializada adequada: consulta dados de **vendas em tempo real via Dremio** ou dados de **compras via MySQL.**

<img src="image-1.png" width="800" alt="Diagrama do fluxo">


## Fluxo Completo — Do WhatsApp à Resposta

<p align="center">
  <img src="src/docs/architecture.svg" width="100%" />
</p>


---

## Estrutura do projeto

```
whatsapp-agent/
├── src/
│   ├── app.py                      # FastAPI — endpoints /webhook e /health
│   ├── chains.py                   # Agente LangChain ReAct: prompt em PT, lazy init, pré-processamento de datas
│   ├── config.py                   # Leitura das variáveis de ambiente (.env)
│   ├── memory.py                   # Histórico de conversa via Redis (TTL 24h)
│   ├── message_buffer.py           # Buffer de mensagens com debounce
│   ├── prompts.py                  # Prompt legado (não utilizado pelo agente atual)
│   ├── vectorstore.py              # RAG: indexação de PDFs/TXTs via Chroma + OpenAI Embeddings
│   ├── docs/
│   │   └── architecture.svg        # Diagrama do fluxo completo
│   ├── connectors/
│   │   ├── dremio.py               # Conector REST API Dremio → DataFrame
│   │   └── mysql.py                # Conector MySQL → DataFrame (lazy pool)
│   ├── tools/
│   │   ├── dremio_tools.py         # Tool LangChain: consultar_vendas (Dremio)
│   │   ├── mysql_tools.py          # Tool LangChain: consultar_compras (MySQL)
│   │   ├── utils.py                # strip_markdown — remove blocos ```sql``` do output do agente
│   │   └── fantasia_abreviacao.py  # Mapeamento abreviação → nome fantasia do estabelecimento
│   └── integrations/
│       └── evolution_api.py        # Envio de mensagem via Evolution API
├── .dockerignore
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
| `redis` | redis:7 | 6379 | Buffer de mensagens + histórico de conversa |

Todos os serviços possuem **health checks** configurados. O `bot` e a `evolution-api` só sobem após Redis e Postgres estarem prontos.

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
    image: evoapicloud/evolution-api:latest   # pin a versão quando estável
    restart: always
    ports:
      - "8080:8080"
    env_file:
      - .env
    volumes:
      - evolution_instances:/evolution/instances
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  # ── PostgreSQL (banco de dados interno da Evolution API) ───────
  postgres:
    container_name: postgres
    image: postgres:15
    command: ["postgres", "-c", "max_connections=1000"]
    restart: always
    ports:
      - 5432:5432
    environment:
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-postgres}   # configurável via .env
    volumes:
      - postgres_data:/var/lib/postgresql/data
    expose:
      - 5432
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

  # ── Redis (buffer de mensagens + histórico de conversa) ────────
  redis:
    image: redis:7
    container_name: redis
    command: >
      redis-server --port 6379 --appendonly yes   # persistência AOF
    volumes:
      - redis:/data
    ports:
      - 6379:6379
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  # ── Bot IA ─────────────────────────────────────────────────────
  bot:
    build: .
    container_name: bot
    ports:
      - "8000:8000"
    env_file:
      - .env
    depends_on:
      redis:
        condition: service_healthy
    restart: always
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3

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

O agente usa **inicialização lazy** — o modelo e as ferramentas são carregados apenas na **primeira mensagem recebida**, não no boot. Isso elimina a dependência de rede no startup e evita falhas ao subir o container.

```
# Inicialização do servidor
INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

## Logs ao receber mensagem

```
# 1. Webhook recebe a mensagem do WhatsApp
2026-03-02 10:00:00 [INFO] src.app: Mensagem de João: "Quanto vendemos em janeiro?"
INFO:     POST /webhook HTTP/1.1  200 OK

# 2. Buffer de debounce — aguarda 3s por mensagens adicionais
2026-03-02 10:00:00 [INFO] src.message_buffer: Mensagem adicionada ao buffer de 55119...@s.whatsapp.net
2026-03-02 10:00:03 [INFO] src.message_buffer: Enviando mensagem agrupada para 55119...@s.whatsapp.net

# 3. Inicialização do agente (apenas na primeira mensagem)
2026-03-02 10:00:03 [INFO] src.chains: Inicializando modelo e agente...
2026-03-02 10:00:04 [INFO] src.chains: Agente pronto.

# 4. Agente ReAct em execução
> Entering new AgentExecutor chain...

Thought: O usuário quer saber o total de vendas de janeiro. Preciso consultar o Dremio.
Action: consultar_vendas
Action Input: SELECT SUM(valor_liquido_final) AS total FROM views."financial_sales_testes"
              WHERE EXTRACT(MONTH FROM data_evento) = 1

2026-03-02 10:00:04 [INFO] src.tools.dremio_tools: Executando query Dremio: SELECT ...
2026-03-02 10:00:05 [INFO] src.connectors.dremio: Obtendo token Dremio...
2026-03-02 10:00:05 [INFO] src.connectors.dremio: Submetendo query ao Dremio...
2026-03-02 10:00:05 [INFO] src.connectors.dremio: Job criado: abc123. Aguardando conclusão...
2026-03-02 10:00:08 [INFO] src.connectors.dremio: Estado do job: COMPLETED (3s)
2026-03-02 10:00:08 [INFO] src.tools.dremio_tools: Query OK — 1 linhas retornadas.

Observation:
      total
   45230.00

Final Answer: Em janeiro foram vendidos R$ 45.230,00.

> Finished chain.

# 5. Resposta enviada de volta ao WhatsApp
2026-03-02 10:00:08 [INFO] src.message_buffer: Resposta do agente para 55119...@s.whatsapp.net: "Em janeiro..."
```

---

## Personalidade e regras do agente

O comportamento do agente está definido na variável `_REACT_PROMPT_TEMPLATE` em [src/chains.py](src/chains.py). Para alterar a personalidade, regras ou instruções do NINOIA, edite esse template.

Regras configuradas:
- Nunca revela detalhes técnicos (tabelas, bancos, ferramentas) ao usuário
- Sempre consulta as ferramentas para cada pergunta — não reutiliza respostas anteriores
- Responde exclusivamente em português
- Perguntas fora do escopo retornam: *"Não tenho acesso a essas informações"*
- Se apresenta pelo nome **NINOIA** ao cumprimentar
- Chama o usuário pelo nome do WhatsApp quando disponível
- Datas sem ano (ex: `26/02`, `5/3`) são completadas automaticamente com o ano corrente antes de chegar ao modelo — tratamento determinístico via regex em `chains.py`, sem depender do LLM
- Mantém as últimas **15 mensagens** do histórico de conversa por sessão; mensagens curtas de correção ou complemento usam esse histórico para reconstruir a pergunta completa
- Histórico de cada sessão expira automaticamente após **24h de inatividade** no Redis

#### Configuração do histórico de conversa (Redis)

| Configuração | Valor | Onde |
|---|---|---|
| Mensagens mantidas no contexto | 15 mensagens (pares usuário + bot) | `_MAX_HISTORY = 15` em `chains.py` |
| Tempo de expiração | 24 horas de inatividade | `_SESSION_TTL = 86400` em `memory.py` |
| Quando o timer reinicia | A cada nova mensagem enviada | comportamento padrão do TTL do Redis |

> Se o usuário ficar 24h sem mandar mensagem, o histórico é apagado automaticamente. Se continuar conversando, o timer renova e nunca expira.

---

## Modelos OpenAI compatíveis

Use modelos da família **chat** (não reasoning):

| Modelo | Indicado para |
|---|---|
| `gpt-4o` | Produção — melhor aderência ao formato ReAct e geração de SQL |
| `gpt-4-turbo` | Alternativa ao gpt-4o |
| `gpt-4o-mini` | Testes — mais rápido/barato, menor confiabilidade no ReAct |

> **Evite modelos da série `o`** (`o1`, `o3`, `o4-mini`) — não suportam o parâmetro `temperature` e não seguem o formato ReAct do LangChain.
