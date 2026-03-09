# whatsapp-agent

Assistente inteligente integrado ao WhatsApp com arquitetura **multi-agente**: um **Router LLM** classifica cada pergunta e roteia para o **Agente SQL** (GPT-4o + Dremio/MySQL, para dados de vendas e compras), o **Agente RAG** (GPT-4o + Chroma, para documentos internos como políticas, organograma e contatos), ou responde diretamente via **LLM** para saudações e perguntas fora do escopo.

## Perguntas sobre Compras
### Interação por Texto :

<img src="image/image-1.png" width="800" alt="Diagrama do fluxo">

<img src="image/image-2.png" width="800" alt="Diagrama do fluxo">

<img src="image/image-3.png" width="800" alt="Diagrama do fluxo">

### Interação por Audio:
<img src="image/image.png" width="800" alt="Diagrama do fluxo">

## Perguntas sobre Vendas:
### Interação por Texto :
<img src="image/image-4.png" width="800" alt="Diagrama do fluxo">

<img src="image/image-6.png" width="800" alt="Diagrama do fluxo">

<img src="image/image-7.png" width="800" alt="Diagrama do fluxo">

### Interação por Audio:
<img src="image/image-5.png" width="800" alt="Diagrama do fluxo">


## Perguntas sobre Politicas\Regras:
<img src="image/image-8.png" width="800" alt="Diagrama do fluxo">

---

## Fluxo Completo — Do WhatsApp à Resposta

<p align="center">
  <img src="src/docs/architecture.svg" width="100%" />
</p>

---

## Estrutura do projeto

```
whatsapp-agent/
├── src/
│   ├── app.py                      # FastAPI — endpoints /webhook e /health + comandos admin
│   ├── access_control.py           # Controle de acesso — SQLite (autorizar, bloquear, remover)
│   ├── chains.py                   # Multi-agente: Router + Agente SQL + Agente RAG
│   ├── config.py                   # Leitura das variáveis de ambiente (.env)
│   ├── memory.py                   # Histórico de conversa via Redis (TTL 24h)
│   ├── message_buffer.py           # Buffer de mensagens com debounce
│   ├── prompts.py                  # Prompts: ReAct SQL (NINOIA), ReAct RAG, Router, Geral (LLM direto)
│   ├── vectorstore.py              # RAG: indexação de PDFs/TXTs via Chroma + OpenAI Embeddings
│   ├── docs/
│   │   └── architecture.svg        # Diagrama do fluxo completo
│   ├── connectors/
│   │   ├── dremio.py               # Conector REST API Dremio → DataFrame
│   │   └── mysql.py                # Conector MySQL → DataFrame (lazy pool)
│   ├── tools/
│   │   ├── dremio_tools.py         # Tools LangChain: consultar_vendas, consultar_delivery, consultar_formas_pagamento, consultar_estornos (Dremio)
│   │   ├── mysql_tools.py          # Tool LangChain: consultar_compras (MySQL)
│   │   ├── rag_tool.py             # Tool LangChain: consultar_documentos (Chroma)
│   │   ├── utils.py                # strip_markdown — remove blocos sql do output do agente
│   │   └── fantasia_abreviacao.py  # Mapeamento abreviação → nome fantasia do estabelecimento
│   └── integrations/
│       ├── evolution_api.py        # Envio de mensagem + download de mídia via Evolution API
│       └── transcribe.py           # Transcrição de áudio via OpenAI Whisper (whisper-1)
├── data/                           # Banco SQLite de controle de acesso (data/access.db)
├── rag_files/                      # PDFs e TXTs para indexação (apagados após indexar)
├── vectorstore/                    # Índice Chroma gerado automaticamente
├── .dockerignore
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env
```

---

## Arquitetura Multi-Agente

```
mensagem → route_and_invoke()
                │
         [Router LLM]         ← classifica a intenção: sql / docs / ambos / geral
                │
     ┌──────────┼──────────┬──────────┐
   "sql"      "docs"    "ambos"    "geral"
     │           │           │           │
[Agente SQL] [Agente RAG] [Agente SQL] [LLM direto]
GPT-4o       GPT-4o       +            GPT-4o
Dremio+MySQL Chroma       [Agente RAG] sem ferramentas
                          (sequencial)
```

| Rota | Quando aciona | Ferramentas |
|---|---|---|
| `sql` | Vendas, faturamento, delivery, formas de pagamento, estornos, compras, pedidos, SSS, ticket médio | `consultar_vendas` (Dremio) + `consultar_delivery` (Dremio) + `consultar_formas_pagamento` (Dremio) + `consultar_estornos` (Dremio) + `consultar_compras` (MySQL) |
| `docs` | Políticas, organograma, contatos, emails, ramais, quem procurar | `consultar_documentos` (Chroma) |
| `ambos` | Pergunta envolve dados numéricos E documentos ao mesmo tempo | Executa Agente SQL + Agente RAG em sequência e combina as respostas |
| `geral` | Saudações, agradecimentos, perguntas fora do escopo | Nenhuma — LLM chamado diretamente (sem ReAct, sem ferramentas) |

Cada agente tem seu próprio **prompt especializado** e **ferramentas exclusivas** — o Agente SQL nunca acessa documentos e o Agente RAG nunca acessa bancos de dados. Para `geral`, não há overhead de agente ReAct: o modelo responde diretamente via `general_prompt`.

---

## Serviços Docker

| Serviço | Imagem | Porta | Função |
|---|---|---|---|
| `bot` | build local | 8000 | FastAPI + Agentes IA |
| `evolution_api` | evoapicloud/evolution-api:latest | 8080 | Gateway WhatsApp |
| `postgres` | postgres:15 | 5432 | Banco de dados da Evolution API |
| `redis` | redis:7 | 6379 | Buffer de mensagens + histórico de conversa |

Todos os serviços possuem **health checks** configurados. O `bot` e a `evolution-api` só sobem após Redis e Postgres estarem prontos.

**Bases de dados externas** (não sobem no Docker):

| Banco | Função |
|---|---|
| Dremio | Dados de vendas — `views."AI_AGENTS"."fSales"`, `views."AI_AGENTS"."fSalesDelivery"`, `views."AI_AGENTS"."fFormasPagamento"` e `views."AI_AGENTS"."fEstornos"` |
| MySQL | Dados de compras — tabela `` `tabela_compras` `` |

**Volumes persistentes:**

| Volume | Conteúdo |
|---|---|
| `evolution_instances` | Instâncias e sessões do WhatsApp |
| `postgres_data` | Banco de dados da Evolution API |
| `redis` | Dados persistidos do Redis (AOF) |
| `vectorstore` | Índice Chroma com os documentos indexados (RAG) |

### Exemplo do docker-compose.yml

```yaml
services:

  # ── Evolution API (Gateway WhatsApp) ───────────────────────────
  evolution-api:
    container_name: evolution_api
    image: evoapicloud/evolution-api:latest
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
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-postgres}
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
      redis-server --port 6379 --appendonly yes
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
    volumes:
      - ./rag_files:/app/rag_files        # PDFs/TXTs para indexar
      - ./vectorstore:/app/vectorstore    # índice Chroma (bind mount — sem problema de permissão)
      - ./data:/app/data                  # banco SQLite de controle de acesso
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/health')\""]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  evolution_instances:
  postgres_data:
  redis:
```

---

## Controle de Acesso

O bot possui um sistema de controle de acesso por número de WhatsApp. Apenas usuários autorizados conseguem interagir — os demais recebem uma mensagem de bloqueio configurável. Existem dois perfis: **usuário comum** e **admin**.

### Onde os dados ficam

Os usuários são armazenados em um banco SQLite no caminho definido por `SQLITE_PATH` (padrão: `data/access.db`), persistido via bind mount `./data:/app/data` no Docker.

| Campo | Descrição |
|---|---|
| `telefone` | Número no formato `5511999999999` (sem `+`, sem espaços) |
| `nome` | Nome do usuário |
| `cargo` | Cargo do usuário (ex: Analista, Coordenador) |
| `casa` | Estabelecimento/unidade (ex: Matriz, Filial) |
| `is_admin` | `1` = admin, `0` = usuário comum |
| `active` | `1` = ativo, `0` = bloqueado |
| `adicionado_por` | Telefone de quem autorizou (legado / compat.) |
| `adicionado_por_tel` | Telefone de quem autorizou |
| `adicionado_por_nome` | Nome de quem autorizou |
| `criado_em` | Data/hora de criação do registro |
| `alterado_em` | Data/hora da última alteração (bloquear/desbloquear/autorizar) |

### Configuração inicial — usuários seed (admin)

Defina os administradores iniciais via variável `SEED_USERS` no `.env`. Eles são inseridos automaticamente na primeira vez que o bot sobe e **nunca sobrescritos** nas reinicializações seguintes.

```env
# Formato: TELEFONE:NOME:CARGO:CASA:admin  (separados por vírgula para múltiplos)
SEED_USERS=5511999990000:João Silva:Analista:Matriz:admin

# Múltiplos usuários seed:
SEED_USERS=5511999990000:João Silva:Analista:Matriz:admin,5511988880000:Maria Souza:Estagiaria:Matriz:user
```

> Usuários seed com perfil `admin` podem gerenciar outros usuários via comandos no próprio WhatsApp.

### Mensagem para usuários não autorizados

```env
UNAUTHORIZED_MESSAGE=Olá! Você não está autorizado a usar este assistente. Entre em contato com um administrador.
```
<img src="image/image-10.png" width="800" alt="Diagrama do fluxo">

---

### Comandos admin (via WhatsApp)

Apenas usuários com `is_admin = 1` podem usar os comandos abaixo. Usuários comuns que tentarem recebem `"Comando não reconhecido."`.

#### Listar usuários padrão

O que escrever no WhatsApp:
```
/usuarios
```

Resposta do bot:
```
*Usuários padrão:*
• 5511988880000 | Maria Souza | Filial | Estagiaria

*Bloqueados:*
• Carlos Lima (5511977770000)
```

---

#### Listar administradores

O que escrever no WhatsApp:
```
/usuarios admin
```

Resposta do bot:
```
*Administradores:*
• 5511999990000 | João Silva | Matriz | Analista | _admin_
```

---

#### Adicionar usuário comum

O que escrever no WhatsApp:
```
/autorizar 5511977770000 ; Carlos Lima ; Analista ; Matriz
```

Resposta do bot:
```
✅ Carlos Lima (5511977770000) autorizado com sucesso.
```

---

#### Adicionar usuário admin

O que escrever no WhatsApp:
```
/autorizar 5511966660000 ; Ana Reis ; Analista ; Matriz ; admin
```

Resposta do bot:
```
✅ Ana Reis (5511966660000) autorizado com sucesso.
```

> Se o número já existir (mesmo que bloqueado), o comando **reativa e atualiza** os dados. Resposta será `reativado` no lugar de `autorizado`.

---

#### Bloquear usuário

Desativa o acesso sem apagar o registro. Pode ser reativado com `/desbloquear`.

O que escrever no WhatsApp:
```
/bloquear 5511977770000
```

Resposta do bot:
```
🚫 Carlos Lima (5511977770000) bloqueado com sucesso.
```

---

#### Desbloquear usuário

Reativa um usuário bloqueado **sem alterar nenhum dado** (nome, cargo, casa, perfil). Não é necessário redigitar as informações.

O que escrever no WhatsApp:
```
/desbloquear 5511977770000
```

Resposta do bot:
```
✅ Carlos Lima (5511977770000) desbloqueado com sucesso.
```

> Se o usuário já estiver ativo, o bot informa: `⚠️ Carlos Lima já está ativo.`

---

#### Remover usuário permanentemente

Apaga o registro do banco. Não pode ser desfeito — para reativar será necessário usar `/autorizar` novamente.

O que escrever no WhatsApp:
```
/remover 5511977770000
```

Resposta do bot:
```
🗑️ Carlos Lima (5511977770000) removido permanentemente.
```

---

#### Ver ajuda no WhatsApp

O que escrever no WhatsApp:
```
/ajuda
```

Resposta do bot:
```
*Comandos disponíveis:*

*/autorizar* 5511999 ; Nome ; Cargo ; Casa
→ Autoriza um novo usuário padrão

*/autorizar* 5511999 ; Nome ; Cargo ; Casa ; admin
→ Autoriza um novo usuário como administrador

*/bloquear* 5511999
→ Bloqueia o acesso de um usuário

*/desbloquear* 5511999
→ Desbloqueia um usuário sem alterar seus dados

*/remover* 5511999
→ Remove o usuário do sistema permanentemente

*/usuarios*
→ Lista todos os usuários padrão cadastrados

*/usuarios admin*
→ Lista todos os administradores cadastrados
```

---

## Gerenciamento de Documentos (RAG)

Coloque PDFs ou TXTs na pasta `rag_files/` para que o Agente RAG passe a responder perguntas sobre eles.

**Fluxo de indexação:**
```
1. Coloque o arquivo em  rag_files/
2. docker compose restart bot
3. Na primeira pergunta sobre documentos, o bot:
   - extrai o texto (PyPDFLoader / TextLoader)
   - divide em chunks de 1000 caracteres com sobreposição de 200
   - gera embeddings via OpenAI
   - salva no índice Chroma em  vectorstore/  (volume persistente)
   - apaga o arquivo original automaticamente
4. Próximas consultas usam o índice já salvo — sem reprocessar
```

**Comandos Docker para o RAG:**

```bash
# Adicionou novo PDF — só restart, sem rebuild
docker compose restart bot

# Acompanhar a indexação nos logs
docker compose logs -f bot
# Procure por: "Arquivo indexado e removido: organograma.pdf"

# Zerar todo o índice de documentos
docker compose down
rm -rf ./vectorstore
docker compose up -d
```

> O custo de embedding (OpenAI) ocorre apenas na indexação. Perguntas subsequentes não geram custo de embedding — apenas o custo normal de tokens do GPT-4o.

---

## Suporte a áudio (Whisper)

O bot transcreve automaticamente mensagens de áudio antes de enviá-las ao agente.

**Fluxo:**
```
Áudio WhatsApp → Evolution API → app.py detecta audioMessage
   → get_media_base64() baixa o áudio da Evolution API
   → transcribe_audio() envia para OpenAI Whisper (whisper-1)
   → texto transcrito → buffer_message() → route_and_invoke() → agente
```

| Arquivo | Responsabilidade |
|---|---|
| `app.py` | Detecta `audioMessage` e orquestra o fluxo |
| `integrations/evolution_api.py` | `get_media_base64()` — baixa o áudio como base64 |
| `integrations/transcribe.py` | `transcribe_audio()` — chama Whisper e retorna texto |

> Mensagens de texto e áudio seguem o mesmo fluxo após a transcrição. O agente não distingue a origem.

**Custo:** ~$0.006/minuto de áudio (OpenAI Whisper). Sem nova dependência — usa o `openai` já instalado.

---

## Ferramentas dos agentes

### `consultar_vendas` — Agente SQL → Dremio
Usada para perguntas sobre faturamento, receita e desempenho de vendas.

Tabela: `views."AI_AGENTS"."fSales"`

| Coluna | Tipo | Descrição |
|---|---|---|
| `casa_ajustado` | TEXT | Nome do estabelecimento |
| `alavanca` | TEXT | Vertical/segmento (Bar, Restaurante, Iraja) |
| `data_evento` | DATE | Data da venda |
| `hora_item` | FLOAT | Hora do item (06:00 a 05:59) |
| `descricao_produto` | TEXT | Nome do produto vendido |
| `quantidade` | FLOAT | Quantidade vendida |
| `valor_produto` | DOUBLE | Valor unitário |
| `nome_funcionario` | TEXT | Nome do funcionário |
| `valor_liquido_final` | DOUBLE | Valor líquido final (use para totais) |
| `desconto_total` | FLOAT | Desconto total aplicado |
| `distribuicao_pessoas` | FLOAT | Somar para obter Fluxo de clientes |
| `ticket_medio` | — | Não é coluna — calcular: `SUM(valor_liquido_final) / SUM(distribuicao_pessoas)` |

### `consultar_delivery` — Agente SQL → Dremio
Usada para perguntas sobre pedidos delivery, faturamento delivery e plataformas (iFood, Rappi, etc.).

Tabela: `views."AI_AGENTS"."fSalesDelivery"`

| Coluna | Tipo | Descrição |
|---|---|---|
| `casa_ajustado` | TEXT | Nome do estabelecimento |
| `alavanca` | TEXT | Vertical/segmento (Bar, Restaurante, Iraja) |
| `data_evento` | DATE | Data do pedido delivery |
| `hora_item` | FLOAT | Hora do item (06:00 a 05:59) |
| `codigo_produto` | TEXT | Código do produto |
| `descricao_produto` | TEXT | Nome do produto vendido |
| `quantidade` | FLOAT | Quantidade de itens vendidos |
| `valor_produto` | DOUBLE | Valor unitário |
| `valor_venda` | DOUBLE | Valor de venda antes de descontos |
| `desconto_produto` | FLOAT | Desconto aplicado no produto |
| `desconto_total` | FLOAT | Desconto total aplicado no pedido |
| `nome_funcionario` | TEXT | Canal/plataforma do pedido (IFOOD, RAPPI, APP PROPRIO, TERMINAL) |
| `valor_conta` | DOUBLE | Valor total da conta/pedido |
| `valor_liquido_final` | DOUBLE | Valor líquido final (use para totais) |
| `distribuicao_pessoas` | FLOAT | Somar para obter Fluxo de clientes |
| `ticket_medio` | — | Não é coluna — calcular: `SUM(valor_liquido_final) / SUM(distribuicao_pessoas)` |

### `consultar_formas_pagamento` — Agente SQL → Dremio
Usada para perguntas sobre mix de pagamentos e participação de cada forma (dinheiro, cartão, pix, etc.).

Tabela: `views."AI_AGENTS"."fFormasPagamento"`

| Coluna | Tipo | Descrição |
|---|---|---|
| `cnpj_casa` | TEXT | CNPJ do estabelecimento |
| `casa_ajustado` | TEXT | Nome do estabelecimento |
| `alavanca` | TEXT | Vertical/segmento (Bar, Restaurante, Iraja) |
| `data` | DATE | Data do registro |
| `descricao_forma_pagamento` | TEXT | Nome da forma de pagamento (VISA_CREDITO, DINHEIRO, PIX, etc.) |
| `pessoas` | FLOAT | Número de pessoas |
| `vl_recebido` | DOUBLE | Valor bruto recebido nessa forma de pagamento (use para totais) |

### `consultar_estornos` — Agente SQL → Dremio
Usada para perguntas sobre estornos, cancelamentos ou devoluções de produtos.

Tabela: `views."AI_AGENTS"."fEstornos"`

| Coluna | Tipo | Descrição |
|---|---|---|
| `casa_ajustado` | TEXT | Nome do estabelecimento |
| `alavanca` | TEXT | Vertical/segmento (Bar, Restaurante, Iraja) |
| `data_evento` | TIMESTAMP | Data e hora do estorno — usar `CAST(data_evento AS DATE)` para filtrar por data |
| `codigo_produto` | INT | Código do produto estornado |
| `descricao_produto` | TEXT | Nome do produto estornado |
| `quantidade` | FLOAT | Quantidade estornada |
| `valor_produto` | DOUBLE | Valor total do estorno — usar `SUM(valor_produto)` para totalizar |
| `descricao_motivo_estorno` | TEXT | Motivo do estorno — usar `GROUP BY` para agrupar por motivo |
| `perda` | INT | Indica se houve perda: `1` = sim, `0` = não |
| `tipo_estorno` | TEXT | Tipo do estorno (ex: COM FATURAMENTO) |
| `nome_cliente` | TEXT | Identificação do cliente |
| `nome_funcionario` | TEXT | Nome do funcionário que realizou o estorno |
| `nome_usuario_funcionario` | TEXT | Login do funcionário |

### `consultar_compras` — Agente SQL → MySQL
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

### `consultar_documentos` — Agente RAG → Chroma
Usada para perguntas sobre documentos internos da empresa.

| Tipo de documento | Exemplos |
|---|---|
| Organograma e estrutura | Hierarquia, setores, departamentos |
| Contatos e emails | Quem procurar para cada assunto, ramais, emails |
| Políticas internas | RH, financeiro, TI, compras |
| Manuais e procedimentos | Processos operacionais, guias |

> A busca é **semântica** — o agente encontra a informação mesmo que a pergunta use palavras diferentes das usadas no documento.

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

# RAG (documentos internos)
RAG_FILES_DIR=rag_files        # pasta onde colocar os PDFs/TXTs
VECTOR_STORE_PATH=vectorstore  # onde o índice Chroma é salvo

# Controle de acesso
SQLITE_PATH=data/access.db
UNAUTHORIZED_MESSAGE=Olá! Você não está autorizado a usar este assistente. Entre em contato com um administrador.

# Usuários iniciais (seed) — inseridos na primeira vez que o bot sobe
# Formato: TELEFONE:NOME:SETOR:CASA:admin  (vírgula para múltiplos)
SEED_USERS=5511999990000:João Silva:TI:Matriz:admin

```

---

## Subir o projeto

```bash
# Primeira vez ou após mudanças no código
docker compose up --build -d

# Reiniciar sem rebuild (após mudanças no .env ou adição de PDFs)
docker compose restart bot

# Ver logs em tempo real
docker compose logs -f bot

# Últimas 100 linhas do bot
docker logs bot --tail 100
```

---

## Logs de startup esperados

Os agentes usam **inicialização lazy** — o modelo e as ferramentas são carregados apenas na **primeira mensagem recebida**, não no boot.

```
INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

## Logs ao receber mensagem — pergunta de dados (SQL)

```
# 1. Webhook recebe a mensagem
2026-03-02 10:00:00 [INFO] src.app: Mensagem de João: "Quanto vendemos em janeiro?"

# 2. Buffer de debounce — aguarda 3s
2026-03-02 10:00:00 [INFO] src.message_buffer: Mensagem adicionada ao buffer de 55119...
2026-03-02 10:00:03 [INFO] src.message_buffer: Enviando mensagem agrupada para 55119...

# 3. Agente SQL inicializado (apenas na primeira mensagem)
2026-03-02 10:00:03 [INFO] src.chains: Inicializando agente SQL...
2026-03-02 10:00:04 [INFO] src.chains: Agente SQL pronto.

# 4. Router classifica a intenção
2026-03-02 10:00:04 [INFO] src.chains: Intencao classificada como 'sql' para: Quanto vendemos em janeiro?

# 5. Agente SQL em execução
> Entering new AgentExecutor chain...

Thought: O usuário quer saber o total de vendas de janeiro. Preciso consultar o Dremio.
Action: consultar_vendas
Action Input: SELECT SUM(valor_liquido_final) AS total FROM views."financial_sales_testes"
              WHERE EXTRACT(MONTH FROM data_evento) = 1

2026-03-02 10:00:08 [INFO] src.connectors.dremio: Estado do job: COMPLETED (3s)

Observation:
      total
   45230.00

Final Answer: Em janeiro foram vendidos R$ 45.230,00.

> Finished chain.
2026-03-02 10:00:08 [INFO] src.message_buffer: Resposta do agente para 55119...: "Em janeiro..."
```

## Logs ao receber mensagem — pergunta de documentos (RAG)

```
# 4. Router classifica a intenção
2026-03-02 10:00:04 [INFO] src.chains: Intencao classificada como 'docs' para: Quem e o responsavel pelo RH?

# 5. Agente RAG inicializado (apenas na primeira vez)
2026-03-02 10:00:04 [INFO] src.chains: Inicializando agente RAG...
2026-03-02 10:00:05 [INFO] src.chains: Agente RAG pronto.

# 6. Vectorstore carregado (apenas na primeira consulta RAG)
2026-03-02 10:00:05 [INFO] src.tools.rag_tool: Carregando vectorstore...
2026-03-02 10:00:06 [INFO] src.tools.rag_tool: Vectorstore pronto.
2026-03-02 10:00:06 [INFO] src.tools.rag_tool: Buscando nos documentos: Quem e o responsavel pelo RH?

# 7. Agente RAG em execução
> Entering new AgentExecutor chain...

Thought: Preciso buscar nos documentos quem é o responsável pelo RH.
Action: consultar_documentos
Action Input: responsavel pelo setor de Recursos Humanos

Observation:
[Trecho 1]
João Silva é o Gerente de Recursos Humanos.
Contato: joao.silva@empresa.com | Ramal: 2301

Final Answer: O responsável pelo RH é João Silva.
Contato: joao.silva@empresa.com | Ramal: 2301

> Finished chain.
```

---

## Personalidade e regras dos agentes

O comportamento de cada agente está definido em [src/prompts.py](src/prompts.py).

### Agente SQL (`react_prompt`)
- **Confidencialidade absoluta:** nunca revela tabelas, bancos, schemas, colunas ou estrutura técnica
- Sempre consulta as ferramentas para cada pergunta — não reutiliza respostas anteriores
- Responde exclusivamente em português
- Perguntas fora do escopo retornam: *"Não tenho acesso a essas informações"*
- Datas sem ano (ex: `26/02`, `5/3`) completadas automaticamente com o ano corrente via regex em `chains.py`
- **SSS (Same Store Sales):** calcula com uma única query CTE no Dremio; deduz o período de comparação automaticamente sem perguntar ao usuário
- Mantém as últimas **5 mensagens** do histórico de conversa por sessão

### Agente RAG (`rag_prompt`)
- Responde **somente** com base nos trechos encontrados nos documentos indexados
- Se não encontrar, informa claramente: *"Não encontrei essa informação nos documentos disponíveis"*
- Para contatos e emails: lista de forma organizada o que estiver nos documentos
- Nunca inventa informações

### Resposta Geral (`general_prompt`)
- Chamada direta ao LLM — **sem agente ReAct, sem ferramentas**
- Usada para saudações, agradecimentos e perguntas fora do escopo
- Resposta mais rápida e de menor custo (sem overhead de Thought/Action/Observation)
- Informa gentilmente o que o bot pode ajudar se a pergunta estiver fora do escopo

### Router (`router_prompt`)
- Classifica a intenção em: `sql`, `docs`, `ambos` ou `geral`
- `geral` é usado para saudações, agradecimentos e perguntas fora do escopo
- Em caso de resposta inválida, usa `sql` como fallback

#### Configuração do histórico de conversa (Redis)

| Configuração | Valor | Onde |
|---|---|---|
| Mensagens mantidas no contexto | 5 pares (usuário + bot) | `_MAX_HISTORY = 5` em `chains.py` |
| Tempo de expiração | 24 horas de inatividade | `_SESSION_TTL = 86400` em `memory.py` |
| Quando o timer reinicia | A cada nova mensagem enviada | comportamento padrão do TTL do Redis |

> Ambos os agentes compartilham o mesmo histórico por sessão — o usuário pode alternar entre perguntas de dados e documentos livremente.

---

## Modelos OpenAI compatíveis

### Agentes (chat / ReAct)

Use modelos da família **chat** (não reasoning):

| Modelo | Indicado para |
|---|---|
| `gpt-4o` | Produção — melhor aderência ao formato ReAct e geração de SQL |
| `gpt-4-turbo` | Alternativa ao gpt-4o |
| `gpt-4o-mini` | Testes — mais rápido/barato, menor confiabilidade no ReAct |

> **Evite modelos da série `o`** (`o1`, `o3`, `o4-mini`) — não suportam o parâmetro `temperature` e não seguem o formato ReAct do LangChain.

### Embeddings (RAG)

| Modelo | Uso |
|---|---|
| `text-embedding-ada-002` | Padrão do `OpenAIEmbeddings()` — indexação e busca no Chroma |

> Custo de indexação: ~$0.0001 por 1000 tokens (~centavos por PDF).

### Transcrição de áudio (Whisper)

| Modelo | Uso |
|---|---|
| `whisper-1` | Único modelo disponível — usado em `integrations/transcribe.py` |

> O modelo é fixo (`whisper-1`). Custo aproximado: **$0.006/minuto** de áudio (R$0,035 por minuto).

---

## Custo por interação (estimativa)

Cada mensagem respondida consome tokens em até duas etapas: **Router LLM** (classificação leve) + **Agente SQL ou RAG** (resposta).

| Tipo de interação | Custo (USD) | Custo (BRL) |
|---|---|---|
| Router (classificação) | ~$0,0005 | ~R$0,003 |
| Mensagem SQL simples | ~$0,002 | ~R$0,012 |
| Mensagem SQL com histórico ativo | ~$0,004 | ~R$0,023 |
| Mensagem RAG (busca em documentos) | ~$0,002 | ~R$0,012 |
| Mensagem geral (saudação/fora do escopo) | ~$0,0003 | ~R$0,002 |
| Áudio de 30s + agente | ~$0,005 | ~R$0,029 |
| Indexação de PDF (~5 páginas) | ~$0,001 (uma vez) | ~R$0,006 |

> Preços GPT-4o: $2,50/1M tokens input · $10,00/1M tokens output · Whisper: $0,006/min · Embeddings: $0,0001/1k tokens

### Exemplo real de custo

**Pergunta:** `"Quanto foi comprado de alimentos dia 26/02/2026 no [estabelecimento]?"`

| Componente | Tokens | Custo (USD) | Custo (BRL) |
|---|---|---|---|
| Router — classificação | ~80 tokens | ~$0,0002 | ~R$0,001 |
| Input — prompt + pergunta + resultado do banco | 362 tokens | ~$0,001 | ~R$0,005 |
| Output — Thought + SQL gerado + Final Answer | 117 tokens | ~$0,001 | ~R$0,007 |
| **Total** | **~559 tokens** | **~$0,002** | **~R$0,013** |

> Valores medidos colando cada componente no [OpenAI Tokenizer](https://platform.openai.com/tokenizer) e somando os totais de input e output separadamente.
