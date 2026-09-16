# Sedatech AI Support Agent — First Refactor

A small, layered starter architecture for a customer-support agent using Ollama,
optional Gemini escalation, explicit tools, and replaceable repositories.

## Structure

```text
app.py                  CLI entry point
factory.py              dependency wiring
config.py               environment settings
agent/                   orchestration, state, prompts, validation
llm/                     Ollama/Gemini adapters and model routing
tools/                   schemas, registry, and thin AI-facing adapters
services/                business rules
repositories/            demo and SQL Server data access
models/                  domain and response models
tests/                   unit tests
```

## Setup

Model settings are shared with the backend. See
[`MODEL_CONFIGURATION.md`](../../MODEL_CONFIGURATION.md) for environment
variables and precedence, including standalone CLI usage.

Use Python 3.11 or newer.

```powershell
cd sedatech_ai_agent_refactor
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
copy .env.example .env
```

Make sure Ollama is running and the model is installed:

```powershell
ollama pull qwen3.5:9b
ollama list
```

Run the agent:

```powershell
python app.py
```

Run the component forecast worker in a separate terminal or service process:

```powershell
python -m services.forecast_worker
```

The worker warms the forecast cache when it starts and refreshes it every day
using the Europe/Berlin timezone. Configure its schedule and forecast horizon in
`.env`:

```env
FORECAST_RUN_HOUR=8
FORECAST_RUN_MINUTE=0
FORECAST_WEEKS=1
```

Try:

```text
What is the status of order 13891?
```

The demo repository contains that order so you can test tool calling before
connecting the production database.

## Run tests

```powershell
pytest -q
```

## Enable Gemini

In `.env`:

```env
MODEL_PROVIDER=gemini
GEMINI_API_KEY=your-key
GEMINI_MODEL=gemini-2.5-flash
```

For simple routing between local and Gemini:

```env
MODEL_PROVIDER=hybrid
```

The current hybrid router is intentionally basic. Replace its keyword rule only
after you have an evaluation set of real tickets.

## Connect SQL Server

First update the real table and column names in:

```text
repositories/sqlserver_order_repository.py
```

Then set:

```env
REPOSITORY_BACKEND=sqlserver
SQLSERVER_CONNECTION_STRING=DRIVER={SQL Server};SERVER=YOUR_SERVER;DATABASE=ShopCenterSL2014;Trusted_Connection=yes;
```

Keep the Windows/SQL account read-only and keep every query parameterized. Do
not add a generic `execute_sql` tool for the model.

## Add another tool

1. Add or reuse a service method.
2. Create a Pydantic argument model and thin handler in `tools/`.
3. Register it in `tools/factory.py`.
4. Add unit tests for validation, success, and failure.

## Next production improvements

- Preserve provider-native tool-call history for Gemini rather than the minimal
  text conversion used in this first scaffold.
- Add structured logs and request IDs.
- Add per-domain tool selection instead of sending all schemas.
- Add database integration tests against a read-only test database.
- Add ticket-history/RAG tools and source citations in generated drafts.
- Add an explicit human-approval state before any external action.
