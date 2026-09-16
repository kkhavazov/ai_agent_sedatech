Model configuration is defined in `inventory_agent/ai_agent_sedatech/model_settings.py`
and shared by the support agent, conversation/summarization client, inventory
agent, and Gemini reprompt client. The module lives in the inventory project so
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

The default remains `qwen3.5:9b`. The default server is now consistently
`http://localhost:11434`; set `OLLAMA_BASE_URL` explicitly for a remote host.
`OLLAMA_THINK` accepts true/false, yes/no, or 1/0. Context, output token limit,
embedding context, and timeout must be positive. `OLLAMA_KEEP_ALIVE` is an Ollama
duration such as `30m` or `0` to unload after requests. Routine chat now uses
consistent temperature and thinking settings, including summarization.

Gemini credentials are optional for local operation. The existing reprompt
feature still uses Gemini, with `GEMINI_MODEL` and `GEMINI_API_KEY` from these
settings (the Google SDK's credential fallback remains available).

Keep the embedding model aligned with the model used to build the Qdrant
collection; changing it requires rebuilding the corresponding embeddings.
Existing cached drafts are not invalidated by a model change.
