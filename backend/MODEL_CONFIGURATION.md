Model configuration is defined in `inventory_agent/ai_agent_sedatech/model_settings.py`
and shared by the support agent, conversation/summarization client, inventory
agent, and optional inventory Gemini client. The module lives in the inventory project so
its standalone CLI can also load it.

Merge the settings from `.env.example` into `backend/.env`; preserve your existing
eDesk, database, and other credentials. Configuration precedence is:

1. Process environment variables
2. `backend/.env`
3. `backend/inventory_agent/ai_agent_sedatech/.env`
4. Repository-root `.env`
5. Defaults in `ModelSettings`

Paths are resolved relative to the source files, independently of your working
directory. Restart the backend and standalone workers after changing settings.
When deploying, provide variables in the backend process/container environment.
The inventory `MODEL_PROVIDER` routing setting remains specific to inventory.

To use the larger model, install it on the Ollama host and set:

```dotenv
OLLAMA_MODEL=qwen3.6:35b
```

The default remains `qwen3.6:35b`. The default server is now consistently
`http://localhost:11434`; set `OLLAMA_BASE_URL` explicitly for a remote host.
`OLLAMA_THINK` accepts true/false, yes/no, or 1/0. Context, output token limit,
embedding context, and timeout must be positive. `OLLAMA_KEEP_ALIVE` is an Ollama
duration such as `30m` or `0` to unload after requests. Routine chat now uses
consistent temperature and thinking settings, including summarization.

Gemini credentials are optional for local operation. Reprompting uses the support
agent and its configured Ollama model, with a separate conversation for each
revision request. Inventory Gemini/hybrid routing uses `GEMINI_MODEL` and
`GEMINI_API_KEY` from these settings.

`GET /tickets/{ticket_id}` translates message text into French with direct Ollama
chat calls using `OLLAMA_MODEL`, without invoking an agent or tools. Translation
disables thinking and sets temperature to zero; other model settings still apply.
Original messages remain in the database. Successful translations are stored in
the same SQLite database (`CACHE_DATABASE_PATH`) as ticket messages and drafts.
The existing `fastapi_cache` Docker volume preserves them across backend restarts
and container rebuilds. The translation table is created automatically on startup
without clearing existing data. Messages translated before this persistent cache
was added need to be translated once more to populate it.

Translations are reused for identical source text, translation instructions, and
effective model/generation settings. Changing these causes a new translation;
changing only the timeout or keep-alive does not. Empty messages are preserved;
failed, empty, or output-limited translations return HTTP 502 and are not cached.

From the repository root, `docker compose up -d --build fastapi` applies backend
changes while preserving this cache. Keep the same Compose project name and
avoid `docker compose down -v`, which deletes the cache volume.

Keep the embedding model aligned with the model used to build the Qdrant
collection; changing it requires rebuilding the corresponding embeddings.
Existing cached drafts are not invalidated by a model change.
