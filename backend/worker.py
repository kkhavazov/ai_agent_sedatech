"""Cache worker: processes all open eDesk tickets and pre-generates caches.

For each open ticket, including tickets with missing translations, this
worker will:
  1. Fetch individual message bodies from the eDesk API and store them in
     the SQLite messages table (so they are not re-fetched).
  2. Translate every non-already-translated message into French via Ollama.
     Successful translations are cached in the translations table so that
     repeated calls reuse the result.
  3. Generate an LLM draft response for tickets that have no cached draft yet.

Run directly:
    python -m backend.worker              # process all open tickets
    python -m backend.worker --tickets 12345,67890   # only specific tickets
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

import httpx

from llm_requests import (
    translate_ticket_messages,
)
from database import (
    DATABASE_PATH,
    get_cached_draft,
    get_cached_message_ids,
    get_cached_messages,
    get_ticket_revision,
    initialize_database,
    store_draft,
    store_ticket_messages,
)

EDESK_API_KEY = os.getenv("EDESK_API_KEY")
if not EDESK_API_KEY:
    raise RuntimeError("EDESK_API_KEY is not configured in the environment.")

TOKEN = EDESK_API_KEY.strip()
HEADERS = {"accept": "application/json", "authorization": TOKEN}
MAX_CONCURRENT = 5

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("worker")


async def fetch_all_open_tickets(client: httpx.AsyncClient) -> list[dict]:
    """Return raw eDesk ticket objects whose state is open."""
    url = "https://api.edesk.com/v1/tickets"
    params = {"state": "open"}
    tickets: list[dict] = []

    while url is not None:
        resp = await client.get(url, params=params, headers=HEADERS)
        resp.raise_for_status()
        body = resp.json()
        data = body.get("data", [])
        if isinstance(data, dict):
            data = data.get("data", [data])
        tickets.extend([t for t in data if isinstance(t, dict)])
        next_url = (
            body.get("meta", {}).get("pagination", {}).get("next")
            or body.get("links", {}).get("next")
        )
        url = next_url

    return tickets


async def fetch_message_details(
    client: httpx.AsyncClient,
    message_id: str,
    semaphore: asyncio.Semaphore,
) -> dict:
    """Fetch one eDesk message and normalise its role / body."""
    async with semaphore:
        resp = await client.get(
            f"https://api.edesk.com/v1/messages/{message_id}",
            headers=HEADERS,
        )
        resp.raise_for_status()

    data = resp.json()["data"]
    if data["direction"] == "Incoming":
        role = "Customer"
    elif data["direction"] == "Outgoing":
        role = "Sedatech Support"
    else:
        return {"role": "", "text": "", "visible": False}

    return {"role": role, "text": data.get("body") or "", "visible": True}


async def fetch_messages_for_ticket(
    client: httpx.AsyncClient, ticket_id: str, message_ids: list[str],
) -> int:
    """Fetch and cache every new message body for ticket_id."""
    cached_ids = await asyncio.to_thread(get_cached_message_ids, ticket_id, message_ids)
    missing_ids = [mid for mid in message_ids if mid not in cached_ids]
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    tasks = [fetch_message_details(client, mid, semaphore) for mid in missing_ids]
    details = await asyncio.gather(*tasks)
    await asyncio.to_thread(
        store_ticket_messages, ticket_id, message_ids, dict(zip(missing_ids, details))
    )
    return len(missing_ids)


async def process_single_ticket(
    client: httpx.AsyncClient,
    ticket_id: str,
    raw_ticket: dict,
) -> dict:
    """Process one ticket end-to-end.  Returns a summary dict."""
    message_ids = [str(mid) for mid in raw_ticket.get("messages_ids", [])]
    remote_last = message_ids[-1] if message_ids else None

    cached_last = await asyncio.to_thread(get_ticket_revision, ticket_id)
    is_current = bool(remote_last) and (cached_last == remote_last)

    summary: dict = {
        "ticket_id": ticket_id,
        "was_current": is_current,
        "messages_cached": 0,
        "translations_generated": 0,
        "drafts_generated": 0,
        "errors": [],
    }

    # Verify individual bodies even when the cached revision is current.
    try:
        summary["messages_cached"] = await fetch_messages_for_ticket(
            client, ticket_id, message_ids
        )
        messages = await asyncio.to_thread(get_cached_messages, ticket_id, message_ids)
        if messages is None:
            raise RuntimeError("Could not build complete ticket history")
    except Exception as exc:
        summary["errors"].append(f"message_fetch: {exc}")
        return summary

    # Warm translations from the exact stored text served by the API.
    try:
        await asyncio.to_thread(translate_ticket_messages, messages)
        summary["translations_generated"] = len(messages)
    except Exception as exc:
        summary["errors"].append(f"translate_batch: {exc}")
        return summary

    # --- 3. Generate draft response if missing ---
    try:
        from customer_support_agent import generate_ticket_reply

        cached_draft = await asyncio.to_thread(
            get_cached_draft, ticket_id, remote_last or ""
        )

        if cached_draft is None and remote_last:
            draft = await asyncio.to_thread(
                generate_ticket_reply,
                messages,
                ticket_id,
                remote_last,
            )
            await asyncio.to_thread(
                store_draft, ticket_id, remote_last, draft,
                event_type="first_draft", messages=messages,
            )
            summary["drafts_generated"] = 1
            log.info("Ticket %s — LLM draft generated.", ticket_id)
    except Exception as exc:
        summary["errors"].append(f"draft: {exc}")
        log.warning("Ticket %s — draft generation failed: %s", ticket_id, exc)


    return summary


async def run_cache_worker(ticket_ids: list[str] | None = None) -> list[dict]:
    """Process all open (or specified) eDesk tickets and pre-cache their data.

    Returns a list of per-ticket summary dicts.
    """
    initialize_database()
    log.info("Cache worker started — database initialised at %s", DATABASE_PATH)

    timeout = httpx.Timeout(30.0, connect=5.0)
    all_summaries: list[dict] = []

    async with httpx.AsyncClient(timeout=timeout) as client:
        if ticket_ids is not None:
            raw_tickets = []
            for tid in ticket_ids:
                try:
                    resp = await client.get(
                        f"https://api.edesk.com/v1/tickets/{tid}",
                        headers=HEADERS,
                    )
                    if resp.status_code == 200:
                        raw_tickets.append(resp.json()["data"])
                    else:
                        log.warning("Could not fetch ticket %s — HTTP %d", tid, resp.status_code)
                except Exception as exc:
                    log.warning("Ticket %s — error: %s", tid, exc)
        else:
            raw_tickets = await fetch_all_open_tickets(client)

        log.info("Found %d ticket(s) to process.", len(raw_tickets))

        for i, rt in enumerate(raw_tickets):
            tid = str(rt["id"])
            log.info("[%d/%d] Processing ticket %s ...", i + 1, len(raw_tickets), tid)
            summary = await process_single_ticket(client, tid, rt)
            if summary.get("errors"):
                for err in summary["errors"]:
                    log.error("Ticket %s — error: %s", tid, err)
            all_summaries.append(summary)

    total_msgs = sum(s["messages_cached"] for s in all_summaries)
    total_trans = sum(s["translations_generated"] for s in all_summaries)
    total_drafts = sum(s["drafts_generated"] for s in all_summaries)
    total_errors = sum(len(s.get("errors", [])) for s in all_summaries)
    was_current = sum(1 for s in all_summaries if s["was_current"])

    log.info("=" * 60)
    log.info(
        "Worker complete: %d tickets | %d msgs cached | %d translations | %d drafts | %d errors",
        len(all_summaries), total_msgs, total_trans, total_drafts, total_errors,
    )
    if was_current:
        log.info("  %d ticket(s) already had current message revisions.", was_current)
    log.info("=" * 60)

    return all_summaries


def main():
    """CLI entry-point for standalone execution."""
    import argparse

    parser = argparse.ArgumentParser(description="Pre-cache open eDesk tickets")
    parser.add_argument(
        "--tickets",
        type=str,
        default=None,
        help="Comma-separated list of ticket IDs to process (default: all open)",
    )
    args = parser.parse_args()

    ticket_ids = [t.strip() for t in args.tickets.split(",")] if args.tickets else None

    summaries = asyncio.run(run_cache_worker(ticket_ids))

    has_errors = any(s.get("errors") for s in summaries)
    sys.exit(1 if has_errors else 0)


if __name__ == "__main__":
    main()
