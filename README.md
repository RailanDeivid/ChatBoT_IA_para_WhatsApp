# NINOIA — ChatBot IA para WhatsApp

Assistente inteligente integrado ao WhatsApp que responde perguntas de negócio para bares e restaurantes consultando dados em tempo real via Dremio (vendas) e MySQL (compras).

---

## Fluxo de funcionamento

```
Usuário (WhatsApp)
        │
        ▼
  Evolution API          ← Gateway WhatsApp
        │  POST /webhook
        ▼
   FastAPI (bot)         ← Recebe evento messages.upsert
        │
        ▼
  Message Buffer         ← Acumula mensagens no Redis
  (debounce 3s)          ← Agrupa mensagens enviadas em sequência
        │
        ▼
  LangChain ReAct Agent  ← GPT-4o decide qual ferramenta usar
        │
   ┌────┴────┐
   ▼         ▼
Dremio     MySQL         ← Executa SQL e retorna DataFrame
(vendas)  (compras)
   │         │
   └────┬────┘
        │ df.to_string()
        ▼
  GPT-4o interpreta
  e formula resposta
        │
        ▼
  Evolution API          ← Envia resposta ao WhatsApp
        │
        ▼
  Usuário (WhatsApp)
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
| Dremio | Dados de vendas — `views."financial_sales_testes"` |
| MySQL | Dados de compras — tabela `` `505 COMPRA` `` |

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
EVOLUTION_INSTANCE_NAME=Bot-whatsapp
AUTHENTICATION_API_KEY=sua_api_key

# OpenAI
OPENAI_API_KEY=sk-...
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
[CHAINS] Carregando modelo e ferramentas...
[CHAINS] Baixando prompt do LangChain Hub...
[CHAINS] Prompt carregado. Criando agente...
[CHAINS] Agente pronto.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

## Logs ao receber mensagem

```
Recebido no webhook: {...}
[BUFFER] Mensagem adicionada ao buffer de 55119...@s.whatsapp.net: oi
[BUFFER] Task de debounce criada para 55119...@s.whatsapp.net
[BUFFER] Iniciando debounce para 55119...@s.whatsapp.net
[BUFFER] Enviando mensagem agrupada para 55119...@s.whatsapp.net: oi
> Entering new AgentExecutor chain...
Final Answer: Olá! Sou o NINOIA...
[BUFFER] Resposta do agente para 55119...@s.whatsapp.net: Olá! Sou o NINOIA...
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
