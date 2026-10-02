import os
import html
from urllib.parse import quote
import requests
from dotenv import load_dotenv
import streamlit as st
from bs4 import BeautifulSoup


def clean_html_for_rag(html_content: str) -> str:
  soup = BeautifulSoup(html_content, "html.parser")
  # Extract text with newlines to preserve structural spacing between paragraphs
  return soup.get_text(separator="\n", strip=True)
load_dotenv()  
st.set_page_config(layout="wide") 

API_URL = os.environ["FASTAPI_INTERNAL_URL"] 
API_KEY = os.environ["INTERNAL_API_KEY"]
headers = {"X-API-Key": API_KEY}

def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    st.title("Login")
    password = st.text_input("Enter password", type="password")
    
    if st.button("Login"):
        if password == os.environ["APP_PASSWORD"]:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password")
    
    return False

# if not check_password():
#     st.stop()


def get_open_list():
    EDESK_API_KEY = os.getenv("EDESK_API_KEY")
    if not EDESK_API_KEY:
        st.sidebar.error("EDESK_API_KEY manquante.")
        return []
        
    token = EDESK_API_KEY.strip()
    edesk_headers = {
        "accept": "application/json",
        "authorization": token
    }
    url = "https://api.edesk.com/v1/tickets?filter_status_equals=Pending"

    try:
        response = requests.get(url, headers=edesk_headers, timeout=60.0)
        response.raise_for_status()
        return [ticket["id"] for ticket in response.json().get("data", [])]
    except Exception as e:
        st.sidebar.error(f"Erreur eDesk: {e}")
        return []



with st.sidebar:
    st.title("Queue")
    open_tickets = get_open_list()
    
    if not open_tickets:
        st.info("Aucun ticket en attente.")
        st.stop()
        
    ticket_id = st.selectbox("Select a ticket to review:", open_tickets)
    if st.button("Refresh Queue", use_container_width=True):
        st.rerun()


st.header(f"Reviewing Ticket: {ticket_id}")

try:
    response = requests.get(f"{API_URL}/{ticket_id}", headers=headers, timeout=60.0)
    if not response.ok:
        raise RuntimeError(
            f"Backend returned {response.status_code}: {response.text[:1000]}"
        )
    ticket_data = response.json()
    messages = ticket_data.get("messages", [])
except Exception as e:
    st.error(f"Impossible de récupérer le contexte du ticket: {e}")
    st.stop()


if "current_draft" not in st.session_state:
    st.session_state.current_draft = ""
if "last_ticket" not in st.session_state:
    st.session_state.last_ticket = None
if "current_sources" not in st.session_state:
    st.session_state.current_sources = []

ticket_revision = (str(ticket_id), ticket_data.get("last_message_id"))
if st.session_state.get("draft_revision") != ticket_revision:
    st.session_state.current_draft = ""
    st.session_state.current_sources = []
    st.session_state.reference_messages = {}

if st.session_state.last_ticket != ticket_id or not st.session_state.current_draft:
    with st.spinner("Generating initial draft..."):
        try:

            llm_response = requests.get(
                f"{API_URL}/{ticket_id}/llm_response",
                headers=headers,
                timeout=120,
            )

            if not llm_response.ok:
                raise RuntimeError(
                    f"Backend returned {llm_response.status_code}: "
                    f"{llm_response.text[:1000]}"
                )

            llm_res = llm_response.json()
            raw_reply = llm_res.get("draft_response", {})

            # Normalize: initial /llm_response returns {"reply": "..."}, reprompt returns the string directly
            if isinstance(raw_reply, dict):
                draft_text = raw_reply.get("reply") or ""
            else:
                draft_text = str(raw_reply) if raw_reply is not None else ""

            st.session_state.current_draft = html.unescape(draft_text).replace("<br />", "\n")
            st.session_state.current_sources = llm_res.get("sources", [])
            st.session_state.last_ticket = ticket_id
            st.session_state.draft_revision = ticket_revision
        except Exception as e:
            st.error(f"Erreur lors de la génération du draft initial : {e}")
            st.stop()



col_history, col_editor = st.columns([1, 1])

with col_history:
    st.subheader("Context")
    for message in messages:
        st.chat_message(message["role"]).write(clean_html_for_rag(message["text"]))

with col_editor:
    st.subheader("Proposed AI Response")

    corrected_text = st.text_area(
        "Edit response here:", 
        value=st.session_state.current_draft, 
        height=300
    )
    
    # -- Referenced Tickets Section --
    sources = list(dict.fromkeys(
        str(source) for source in (st.session_state.get("current_sources") or [])
    ))
    st.divider()
    st.subheader("Referenced Tickets")
    if sources:
        st.caption(
            "Tickets returned by the agent's knowledge search; not necessarily cited "
            "in the reply. Messages are loaded from eDesk when requested."
        )
        src_ticket = st.selectbox(
            "Reference ticket", sources, key=f"reference_ticket_{ticket_id}",
        )
        st.link_button(
            "Open reference in eDesk",
            f"https://dashboard-3.edesk.com/crm/view/{quote(src_ticket, safe='')}",
        )
        reference_cache = st.session_state.setdefault("reference_messages", {})
        if st.button("Load / refresh reference messages"):
            reference_cache.pop(src_ticket, None)
            with st.spinner("Loading reference messages..."):
                try:
                    reference_response = requests.get(
                        f"{API_URL}/{quote(src_ticket, safe='')}",
                        headers=headers, timeout=120,
                    )
                    reference_response.raise_for_status()
                    reference_cache[src_ticket] = reference_response.json().get("messages", [])
                except (requests.RequestException, ValueError) as exc:
                    st.error(f"Could not load reference ticket {src_ticket}: {exc}")
        if src_ticket in reference_cache:
            with st.expander(f"Messages from ticket {src_ticket}", expanded=True):
                if not reference_cache[src_ticket]:
                    st.info("No visible messages in this reference ticket.")
                for message in reference_cache[src_ticket]:
                    st.chat_message(message["role"]).write(
                        clean_html_for_rag(message.get("text") or "")
                    )
    else:
        st.caption("No reference tickets were recorded for this draft.")

    # -- Message-type selector (Note = internal comment, Message = public) --
    if "response_type" not in st.session_state:
        st.session_state.response_type = "Message"
    
    resp_type = st.radio(
        "Send as:",
        options=["Message", "Note"],
        horizontal=True,
        label_visibility="collapsed",
        index=0 if st.session_state.response_type == "Message" else 1,
        key="resp_type_widget",
        help='"Message" is visible to the customer; "Note" is an internal comment only.',
    )
    st.session_state.response_type = resp_type

    c1, c2, c3 = st.columns([3, 1, 2])
    with c1:
        if st.button("🚀 Approve & Send", use_container_width=True):
            try:
                res = requests.post(
                    f"{API_URL}/{ticket_id}/response", 
                    json={"text": corrected_text, "type": resp_type}, 
                    headers=headers,
                    timeout=60.0
                )
                if res.status_code == 200:
                    st.success(f"Response sent as {resp_type} to ticket {ticket_id}!")
                    st.rerun()
            except Exception as e:
                st.error(f"Erreur d'envoi: {e}")

    with c2:
        reprompt_instruction = st.text_input("What should the AI change?", placeholder="Make it more formal...")
        if st.button("🔄 Reprompt AI", use_container_width=True):
            if reprompt_instruction:
                with st.spinner("AI is rethinking..."):
                    try:
                        payload = {
                            "instructions": reprompt_instruction,
                            "last_response": corrected_text,
                        }
                        reprompt_response = requests.post(
                            f"{API_URL}/{ticket_id}/reprompt", 
                            json=payload,
                            headers=headers,
                            timeout=60
                        )
                        reprompt_response.raise_for_status()
                        llm_res = reprompt_response.json()

                        # Normalize: reprompt returns the string directly
                        raw_reply = llm_res.get("draft_response", "")
                        if isinstance(raw_reply, dict):
                            new_draft = raw_reply.get("reply") or ""
                        else:
                            new_draft = str(raw_reply) if raw_reply is not None else ""

                        st.session_state.current_draft = html.unescape(new_draft).replace("<br />", "\n")
                        st.session_state.current_sources = llm_res.get("sources", [])
                        st.rerun() 
                    except Exception as e:
                        st.error(f"Erreur lors du reprompt: {e}")
            else:
                st.warning("Please enter an instruction first!")

    with c3:
        if st.button("👉 Go straight to Ticket", use_container_width=True):
            st.info("Action non configurée.")
