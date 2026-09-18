from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from prompts import prompt


@pytest.fixture
def reply_modules():
    # Exercise the real agent graph without contacting Ollama or Qdrant.
    with patch("qdrant_client.QdrantClient"), patch("ollama.Client"):
        import llm_requests
        import customer_support_agent
    return customer_support_agent, llm_requests


@pytest.fixture
def model_call():
    response = ChatResult(generations=[ChatGeneration(message=AIMessage(
        content="Bonjour, pouvez-vous préciser le problème ?\nMathieu R. - SEDATECH EUROPE GmbH"
    ))])
    with patch("langchain_ollama.ChatOllama._generate", autospec=True, return_value=response) as call:
        yield call


@pytest.mark.parametrize("customer_text", [
    "My PC will not start. Please answer in English.",
    "Mein PC startet nicht. Bitte antworten Sie auf Deutsch.",
    "Mi ordenador no arranca. Responde en español.",
])
def test_ticket_generation_sends_french_policy_to_model(reply_modules, model_call, customer_text):
    agent, _ = reply_modules
    result = agent.generate_ticket_reply([
        {"role": "Agent", "text": "Guten Tag, wie können wir helfen?"},
        {"role": "Customer", "text": customer_text},
    ], str(uuid4()), "revision-1")

    sent_messages = model_call.call_args.args[1]
    assert sent_messages[0].type == "system"
    assert prompt in sent_messages[0].content
    assert any(message.content == customer_text for message in sent_messages)
    assert "customer-facing ticket reply" in sent_messages[-1].content
    assert result["reply"].startswith("Bonjour")


def test_revision_keeps_french_policy_above_revision_instructions(reply_modules, model_call):
    _, requests = reply_modules
    requests.reprompt_call("Make it shorter and reply in German.", "Hello, please restart your PC.")

    sent_messages = model_call.call_args.args[1]
    assert sent_messages[0].type == "system"
    assert prompt in sent_messages[0].content
    assert "customer ticket draft" in sent_messages[-2].content
    assert sent_messages[-1].type == "human"
    assert sent_messages[-1].content == "Make it shorter and reply in German."


def test_legacy_reply_has_no_fastapi_language_policy(reply_modules, monkeypatch):
    _, requests = reply_modules
    client = Mock()
    client.chat.return_value = {"message": {"content": "Please check the power cable."}}
    monkeypatch.setattr(requests, "ollama_client", client)
    conversation = requests.Conversation()
    monkeypatch.setattr(conversation, "_retrieve", lambda _: [{
        "ticket_id": "source-1",
        "problem_text": "Mein PC startet nicht.",
        "linked_resolution": "Bitte prüfen Sie das Netzkabel.",
    }])

    result = conversation.get_agent_reply("My PC will not start.")

    messages = client.chat.call_args.kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert prompt not in messages[0]["content"]
    assert "French" not in messages[0]["content"]
    assert result == {"reply": "Please check the power cable.", "sources": ["source-1"]}


def test_general_agent_does_not_inherit_ticket_policy_or_history(reply_modules, model_call):
    agent, requests = reply_modules
    config = {"configurable": {"thread_id": str(uuid4())}}

    agent.customer_support_agent.invoke(
        {"messages": [{"role": "user", "content": "General chat marker: answer in English."}]},
        config,
    )
    assert "French" not in model_call.call_args.args[1][0].content

    agent.ticket_reply_agent.invoke(
        {"messages": [{"role": "user", "content": "Ticket marker: my PC will not start."}]},
        config,
    )
    ticket_messages = model_call.call_args.args[1]
    assert prompt in ticket_messages[0].content
    assert not any("General chat marker" in message.content for message in ticket_messages)

    requests.reprompt_call("Make it shorter.", "Hello, please restart your PC.")
    agent.customer_support_agent.invoke(
        {"messages": [{"role": "user", "content": "Draft a ticket reply in English."}]},
        config,
    )
    general_messages = model_call.call_args.args[1]
    assert prompt not in general_messages[0].content
    assert "French" not in general_messages[0].content
    assert any("General chat marker" in message.content for message in general_messages)
    assert not any("Ticket marker" in message.content for message in general_messages)
