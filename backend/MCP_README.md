# Company tools in ChatGPT

## Private OpenAI tunnel installed on this PC

### Run independently of VS Code on Windows

From Windows PowerShell in the repository root:

```powershell
.\Manage-CompanyTunnel.ps1 -Action Install
# Enter the runtime API key in the hidden prompt, then stop the old foreground
# tunnel with Ctrl+C in its terminal before starting the scheduled task.
.\Manage-CompanyTunnel.ps1 -Action Start
.\Manage-CompanyTunnel.ps1 -Action Status
```

Installation registers `CompanyBot-Tunnel` under the current Windows account.
It starts at sign-in, runs hidden, and restarts one minute after an exit (up to
999 failure retries). A repeating one-minute trigger also starts it if it was
terminated without triggering failure recovery; running instances are not duplicated.
It has no default three-day execution limit. Closing VS Code or
locking the desktop does not stop it. Signing out stops it; it is not a Windows
service that runs before login. Keep Docker Desktop running and the PC awake.
This supervisor restarts exited processes; it does not kill/restart a hung but
still-running process based on readiness.

The API key is stored using Windows DPAPI encryption in the ignored
`.tunnel-client/runtime-key.dpapi`, restricted to the installing user and SYSTEM.
It is decrypted into process memory when the task starts. The same Windows
account on this PC must run the task. This does not protect against malware
running as that user or administrators. No secret is put into task arguments.

Logs are in `.tunnel-client/logs/tunnel.log`, with five rotated files at 10 MB
each. The wrapper redacts literal runtime/local keys and OpenAI key patterns;
logs can still contain operational details, so review before sharing.

Use `-Action Stop` to disable automatic starts and stop the scheduled instance
(`-Action Start` re-enables it), or `-Action Remove` to
unregister it. Removal retains encrypted credentials and logs. Do not run the
foreground launcher simultaneously. An exit code of 1 tells Task Scheduler to
restart; consult the log for the underlying tunnel-client exit reason.

The workspace-local client is `.tunnel-client/tunnel-client.exe` (v0.0.19 at
installation, checked against the official release SHA-256). Its ignored local
profile is `.tunnel-client/profiles/company-bot.yaml`; it targets
`http://127.0.0.1:8001/mcp` and uses the provided OpenAI tunnel ID. The profile
stores an environment-variable reference, not an API key.

From a PowerShell terminal in the repository root, run:

```powershell
docker compose -f docker-compose.mcp.yml up --build -d mcp
.\Start-CompanyTunnel.ps1
```

The script prompts securely for a runtime API key, runs `doctor --explain`, and
starts the tunnel in the foreground if diagnostics pass. Use `-CheckOnly` for
diagnostics without starting. The key is not saved; the terminal must stay open
while the tunnel runs. Status UI: `http://127.0.0.1:8091/ui`.

Create the runtime key at https://platform.openai.com/settings/organization/api-keys
under the organization associated with your tunnel. The key's principal needs
Tunnels Read + Use. Do not use an admin key. Check the tunnel's account/workspace
associations at https://platform.openai.com/settings/organization/tunnels before
selecting Connection: Tunnel in ChatGPT.

Compose now starts the server with `--tunnel`. This mode needs no public URL,
certificate, or OAuth provider. It authenticates the local tunnel client using
a random secret in the ignored `.tunnel-client/mcp-key` file. Compose mounts it
as a read-only secret; the launcher injects it into MCP requests and discovery
probes using a file reference. This is separate from your OpenAI runtime key.
The secret file is restricted to the Windows workspace owner, SYSTEM, and the
local setup account. Keep it private and do not commit or paste it into chat.

For this mode choose **Connection: Tunnel** and **No authentication** in ChatGPT:
OpenAI tunnel access controls authorize callers, and the client authenticates
its local hop. Every account authorized to use this tunnel can use all 18 tools.
There is no separate employee identity check or record filtering. Keep the
Docker port bound to `127.0.0.1`; do not expose this mode publicly. The default
server mode (without `--tunnel`) still requires OAuth; `--local` is development
only. To rotate the local secret, replace the file with a new random value,
recreate the container, and restart the tunnel client.

Installation diagnostics currently stop at the missing runtime API key; an
authenticated live tunnel and a ChatGPT tool call have not yet been verified.
Official guide: https://developers.openai.com/api/docs/guides/secure-mcp-tunnels

`mcp_server.py` exposes all five main assistant tools and every tool registered
by the configured inventory backend through Streamable HTTP at `/mcp`.
It reuses the existing schemas, defaults, validation and handlers. With SQL Server
configured there are 18 tools. Demo mode omits the SQL-only tools, just as the
existing inventory agent does. This service does not start the Streamlit UI or
the ticket API and does not send replies to customers.

## Tools

Main assistant: `query_inventory`, `analyze_data`, `search_customer_kb`,
`run_python_calculation`, `query_website_traffic`.

Inventory: `inventory_items_compatability`, `inventory_get_emails`,
`inventory_get_order`, `inventory_filter_orders`, `inventory_analyze_data`,
`inventory_count_orders`, `inventory_search_item`, `inventory_search_items_skus`,
`inventory_analyse_items_used`, `inventory_forecast_components`,
`inventory_find_missing_components`,
`inventory_find_missing_components_for_open_orders`, `inventory_get_current_time`.

The `inventory_` prefix avoids the two different `analyze_data` schemas colliding.
Direct inventory tools bypass model routing; `query_inventory` retains the
existing Ollama/Gemini agent. KB retrieval still needs Ollama embeddings and
Qdrant; GA4 still needs the existing Google credentials. Forecasting retains the
existing forecast database requirements. Chart results are JSON data for ChatGPT
to render, not Streamlit widgets. Returned backend errors are marked as MCP
tool errors. No new OpenAI API key is required by this server.

## Local development

From the repository root, using a working Python 3.12 installation:

```powershell
python -m pip install -r backend/requirements.txt
python backend/mcp_server.py --local
```

Connect an MCP client/Inspector using Streamable HTTP to
`http://127.0.0.1:8001/mcp`. Local mode binds only to loopback, checks the peer
address, and disables forwarded-address trust. It has no authentication and
must not be exposed using a public proxy or tunnel. It is for development only.

The server loads the existing environment configuration (process variables,
backend `.env`, inventory `.env`, repository `.env`, in that precedence order).
Use `REPOSITORY_BACKEND=sqlserver` and the existing SQLSERVER settings for real
company data. Tool discovery constructs clients but does not query SQL.

## Authenticated remote deployment

Configure these in `backend/.env` (examples also appear in `.env.example`):

```dotenv
MCP_PUBLIC_URL=https://tools.example.com/mcp
MCP_OAUTH_ISSUER=https://your-company-identity-provider.example.com/
MCP_OAUTH_JWKS_URL=https://your-company-identity-provider.example.com/.well-known/jwks.json
MCP_OAUTH_SCOPES=company.tools.read
```

Use the exact issuer advertised by your identity provider, including any trailing
slash. Register an OAuth resource/API with audience equal to `MCP_PUBLIC_URL` and
the configured scope. Register ChatGPT as an OAuth client with the callback URL
shown in its connection setup. The provider must support authorization-code flow
with PKCE and OAuth discovery; configure static client credentials in ChatGPT
unless the provider supports its dynamic registration flow. Grant this scope
only to employees authorized for all exposed company tools.

The server is an OAuth **resource server**, not an identity provider. It verifies
RS256/ES256 JWT signatures using the configured JWKS, issuer, audience, expiry,
subject and scopes. Opaque access tokens are not supported. Protected-resource
discovery is available at `/.well-known/oauth-protected-resource/mcp`, and
unauthorized requests receive a discovery challenge. Scope grants access to all
tools; this implementation does not provide per-employee row filtering.

Start OAuth mode directly with `python backend/mcp_server.py`. The supplied
Compose file instead selects private tunnel mode; to use OAuth with Docker,
remove `--tunnel` from its command and supply the OAuth settings above.
Start the supplied private tunnel deployment from the repository root:

```powershell
docker compose -f docker-compose.mcp.yml up --build -d
```

Direct mode listens on port 8001. Compose publishes that port only on the host's
loopback interface. Put an HTTPS reverse proxy in front of it and forward `/mcp`
and `/.well-known/oauth-protected-resource/mcp`. Preserve the public Host and
Authorization headers. Do not log bearer tokens or tool bodies. Set suitable
request-size/rate limits and timeouts for your deployment. When using GA4 in
Docker, also mount its service-account credentials and set
`GOOGLE_APPLICATION_CREDENTIALS`, as for the existing analytics service.

The default server refuses to start without OAuth configuration. Private
`--tunnel` mode instead refuses to start without its shared secret. There is no
anonymous public mode. Public OAuth deployment requires provider registration,
DNS and TLS; private tunnel deployment follows the instructions above.

## Connect ChatGPT

On ChatGPT web, open Plugins, add a custom MCP server, enter your public `/mcp`
URL and select OAuth. Supply the registered client credentials if needed, finish
company login, and install/select the resulting plugin. Each individual account
connects separately. Account availability and UI labels can vary.

Official references:
- https://developers.openai.com/api/docs/guides/custom-mcp-server
- https://developers.openai.com/plugins/build/mcp-server

For verification without test files, use MCP Inspector to initialize, list tools,
call `inventory_get_current_time`, and call `run_python_calculation` with
`{"code":"sum([1, 2, 3])"}`. Check missing/invalid tokens return 401 and tokens
without the required scope return 403. Validate live data tools against known
records after deployment; local transport checks alone do not verify SQL, GA4,
Qdrant, forecasting or model availability.
