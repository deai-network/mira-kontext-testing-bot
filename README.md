# Mira Kontext Testing Bot

An agentic testing chatbot for the [Mira Kontext API](https://github.com/hash00x1/mira-kontext-api). This bot provides both an interactive CLI interface for testing API endpoints and a comprehensive automated test suite for validating user scenarios.

## Features

### Interactive Chat Interface
- **Project & Session Management**: Create and switch between conversation projects and sessions
- **Memory Operations**: Write, retrieve, and search conversation memory
- **Context Queries**: Query the API with automatic context retrieval
- **Ingestion**: Interactive content ingestion from the CLI
- **Document Retrieval**: Fetch specific documents by short ID

### Test Scenarios
- **Health Checks**: Verify API and database connectivity
- **Ingestion Tests**: Test content creation, updates, and deduplication
- **Memory Tests**: Validate conversation memory write/read/search
- **Query Tests**: Test context retrieval with various filters
- **Permission Tests**: Validate role-based access control
- **Audit Tests**: Verify audit logging functionality

## Installation

```bash
# Clone or navigate to the testing bot directory
cd mira-kontext-testing-bot

# Install with Poetry
poetry install

# Or install with pip
pip install -e .
```

## Configuration

Create a `.env` file in the project root:

```bash
# Required: API endpoint and token
KONTEXT_API_URL=http://localhost:8080
KONTEXT_TOKEN=your-api-token-here

# Optional: Bot identity
BOT_PRINCIPAL_ID=testing-bot
BOT_DISPLAY_NAME="Mira Kontext Testing Bot"
BOT_ROLES=["tester", "admin"]

# Optional: Default project/session
DEFAULT_PROJECT_ID=default-test-project
DEFAULT_SESSION_ID=default-test-session

# Optional: Test settings
REQUEST_TIMEOUT=30.0
DEBUG=false
```

## Usage

### Interactive Chat Mode

Start the interactive chat interface:

```bash
# Using Poetry
poetry run python -m mira_kontext_testing_bot

# Or using the CLI
poetry run kontext-bot chat
```

Available commands in chat mode:

| Command | Description |
|---------|-------------|
| `/user <id> [roles]` | Switch to or create a user principal |
| `/blank-user <id> [roles]` | Start a fresh memory session for a user |
| `/users` | List known users |
| `/project <id>` | Switch to or create a project |
| `/session <id>` | Switch to or create a session |
| `/sessions` | List active sessions |
| `/query <text>` | Query for context |
| `/memory` | Show recent conversation memory |
| `/search <text>` | Search conversation memory |
| `/sources` | List ingested sources |
| `/doc <short_id>` | Retrieve a document |
| `/ingest` | Interactive content ingestion into the current user's private context by default |
| `/crawl <url>` | Fetch and ingest a web page (requires FIRECRAWL_API_KEY) |
| `/search-web <query>` | Search the web and ingest top results |
| `/test <suite>` | Run test scenarios |
| `/status` | Check API status |
| `/help` | Show help |
| `/quit` | Exit the bot |

Use `/blank-user` when you want a clean storage/retrieval run for embedding-backed memory tests. It creates a fresh session for the selected principal, so subsequent `/memory`, `/search`, chat storage, and context queries are scoped to that user/project/session combination.

Natural-language chat can also trigger existing API actions when the fast intent classifier is configured. Phrases like “ingest this dataset...” or “show my sources” are routed through the same client methods as `/ingest` and `/sources`; no extra CLI commands are added. Auto-ingest requires explicit write wording and stores into the current user's private context by default.

### CLI Commands

#### Run Test Suites

```bash
# Run full test suite
poetry run kontext-bot test full

# Run specific test suite
poetry run kontext-bot test health
poetry run kontext-bot test memory
poetry run kontext-bot test query
poetry run kontext-bot test ingest
poetry run kontext-bot test audit
```

#### Single Query

```bash
poetry run kontext-bot query "What is Project Atlas?" --limit 5
```

#### Fetch and Ingest a Web Page

```bash
poetry run kontext-bot crawl https://example.com/article
```

#### Search the Web and Ingest Results

```bash
poetry run kontext-bot search-web "Project Atlas documentation" --max-results 3
```

#### Check API Status

```bash
poetry run kontext-bot status
```

#### Show Configuration

```bash
poetry run kontext-bot config
```

## Web Fetching

The bot can crawl the web and ingest pages directly into the Kontext API as source records. This is useful when the knowledge base does not contain relevant information and you want to pull in up-to-date content from the internet.

### Features

- **Manual Crawl**: Fetch a specific URL via Firecrawl and ingest it into your private collection (`/crawl`).
- **Web Search**: Search with Firecrawl, fetch top results, and ingest them automatically (`/search-web`).
- **Auto-Propose**: When `AUTO_WEB_SEARCH=true` and a chat query returns no local sources, the bot asks if you want to search the web, then re-queries after ingestion.

### Configuration

Add to your `.env` file:

```bash
# Firecrawl API key (get one at https://firecrawl.dev)
FIRECRAWL_API_KEY=fc-xxxxxxxxxxxxxxxxxxxxxxxx

# Whether to propose web search when local sources are empty
AUTO_WEB_SEARCH=true
```

## Nebius Endpoints

The bot uses Nebius OpenAI-compatible endpoints for response generation and intent classification. Configure:

```bash
NEBIUS_API_KEY=your-nebius-key
LLM_BASE_URL=https://api.tokenfactory.nebius.com/v1/
LLM_MODEL=openai/gpt-oss-120b
LLM_PROVIDER=nebius

# Optional separate classifier key
INTENT_API_KEY=
INTENT_BASE_URL=https://api.tokenfactory.nebius.com/v1/
INTENT_MODEL=openai/gpt-oss-120b
INTENT_PROVIDER=nebius
INTENT_CONFIDENCE_THRESHOLD=0.75
INTENT_TIMEOUT=8.0
```

If `INTENT_API_KEY` is not set, the classifier uses `NEBIUS_API_KEY`.

The internal client call pattern follows the OpenAI SDK style:

```python
import os
from openai import AsyncOpenAI

client = AsyncOpenAI(
    base_url="https://api.tokenfactory.nebius.com/v1/",
    api_key=os.environ.get("NEBIUS_API_KEY"),
)

response = await client.chat.completions.create(
    model="openai/gpt-oss-120b",
    messages=[
        {"role": "system", "content": "SYSTEM_PROMPT"},
        {"role": "user", "content": [{"type": "text", "text": "USER_MESSAGE"}]},
    ],
)
```

For private-context ingest, the bot omits `collection_external_id` so the API creates or reuses the current user's private source collection.

### Interactive Chat Commands

| Command | Description |
|---------|-------------|
| `/crawl <url>` | Fetch a web page and ingest it into your private collection |
| `/search-web <query>` | Search the web, fetch top results, and ingest them |

### CLI Commands

| Command | Description |
|---------|-------------|
| `kontext-bot crawl <url>` | Fetch and ingest a single page |
| `kontext-bot search-web <query> --max-results 3` | Search and ingest web results |

---

## API Endpoints Tested

The bot validates the following Kontext API endpoints:

### Health & Status
- `GET /health` - API health check
- `GET /ready` - Database readiness check

### Query & Context
- `POST /v1/query` - Context retrieval with semantic search
- `GET /v1/documents/{short_id}` - Document retrieval
- `GET /v1/sources` - List ingested sources

### Memory
- `POST /v1/memory/messages` - Write conversation message
- `GET /v1/memory/recent` - Retrieve recent messages
- `POST /v1/memory/search` - Semantic search in memory

### Ingestion
- `POST /v1/ingest/records` - Ingest source records
- `POST /v1/ingest/requests` - Ingest request records
- `POST /v1/ingest/files` - Ingest files

### Audit
- `GET /v1/audit/{audit_id}` - Retrieve audit records

### Token Management
- `POST /v1/tokens` - Create API tokens
- `GET /v1/tokens` - List tokens
- `DELETE /v1/tokens/{token_id}` - Revoke tokens

## Test Scenarios

### Health Checks
Verify API connectivity and database readiness.

### Ingestion Cycle
Tests idempotent ingestion:
1. Create new record
2. Re-ingest same content (unchanged)
3. Update content (updated)
4. Verify in sources list

### Memory Operations
- Write messages to conversation memory
- Retrieve recent messages
- Search memory semantically
- Verify session isolation

### Context Queries
- Query with content kind filters
- Source scope filtering
- Role-based access control
- Metadata matching

### Permission Tests
- Restricted content filtering
- Role-denied access attempts
- Unknown ACL handling

### Audit Tests
- Verify audit events are created
- Validate audit record content
- Check tenant isolation

## Project Structure

```
mira-kontext-testing-bot/
├── src/mira_kontext_testing_bot/
│   ├── __init__.py
│   ├── cli.py              # CLI entry point
│   ├── client.py           # API HTTP client
│   ├── config.py           # Configuration settings
│   ├── chat_interface.py   # Interactive chat UI
│   ├── session.py          # Session management
│   ├── memory_manager.py   # Memory operations
│   ├── test_runner.py      # Test scenarios
│   ├── models.py           # Pydantic models
│   └── errors.py           # Custom exceptions
├── tests/                  # Test suite (to be added)
├── pyproject.toml          # Poetry configuration
└── README.md               # This file
```

## Development

### Running Tests

```bash
# Run with pytest
poetry run pytest

# Run with coverage
poetry run pytest --cov=src/mira_kontext_testing_bot
```

### Code Quality

```bash
# Lint with ruff
poetry run ruff check src tests

# Format code
poetry run ruff format src tests

# Type check with pyright
poetry run pyright src
```

## Integration with mira-kontext-api

This testing bot is designed to work with the mira-kontext-api. When the API is running locally (e.g., via Docker Compose):

```bash
# In mira-kontext-api directory
docker compose -f docker/docker-compose.yml up

# In another terminal, start the testing bot
poetry run kontext-bot chat
```

## API Request Logging

The bot automatically logs all API HTTP traffic (both to the Kontext API and the Nebius/Ollama LLM endpoints) into `bot_api_requests.log` in the testing bot directory.

To monitor API calls in real-time and review the JSON payloads, you can run a tail command in your terminal while interacting with the bot in another window:

```bash
tail -f bot_api_requests.log
```

Alternatively, you can monitor the logs directly from an interactive Python REPL:

```python
import os
import time

def tail_bot_logs():
    """Tails the bot API logger file."""
    log_path = "bot_api_requests.log"
    if not os.path.exists(log_path):
        print(f"Waiting for {log_path} to be created...")
    
    with open(log_path, "a+") as f:
        f.seek(0, os.SEEK_END)
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.5)
                continue
            print(line, end="")

tail_bot_logs()
```

## License

Proprietary - Owned by deAI Labs UG (haftungsbeschränkt). See LICENSE file for details.

## Contributing

This is an internal testing tool. For issues or feature requests related to the testing bot, please open an issue in the repository.
