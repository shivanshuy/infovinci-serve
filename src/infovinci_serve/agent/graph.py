"""
Chat graph: LangGraph `MessagesState` for Agent Server (`langgraph dev`).

Persistence is provided by the platform (thread id in run config), not a custom checkpointer.
LLM defaults to local Ollama `llama3.1:8b`; otherwise a demo echo node can be selected.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, MessagesState, StateGraph

from infovinci_serve.blog_embedder import retrieve_blog_context

DEFAULT_SYSTEM = os.environ.get(
    "INFOVINCI_CHAT_SYSTEM",
    "You are a helpful assistant for the Infovinci blog site. Be concise and clear. "
    "When blog context is provided, answer only from that context. "
    "End with a short 'Sources:' section listing each post title and URL exactly as given in the context. "
    "Do not cite external papers or websites unless they appear in the context.",
)

_compiled: Any = None


def _load_chat_model():
    """Load the configured chat model.

    Default is local Ollama (`ollama:llama3.1:8b`). Set INFOVINCI_CHAT_MODEL=echo
    to use the demo echo node, or another `provider:model` spec supported by LangChain.
    """
    from langchain.chat_models import init_chat_model

    spec = (os.environ.get("INFOVINCI_CHAT_MODEL") or "ollama:llama3.1:8b").strip()
    if spec.lower() in {"", "echo", "none", "disabled"}:
        return None
    temp = float(os.environ.get("INFOVINCI_CHAT_TEMPERATURE", "0.2"))
    try:
        if spec.startswith("ollama:"):
            from langchain_ollama import ChatOllama

            return ChatOllama(
                model=spec.removeprefix("ollama:"),
                temperature=temp,
                base_url=os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            )
        return init_chat_model(spec, temperature=temp)
    except Exception:
        return None


def _echo_node(state: MessagesState) -> dict[str, list[AIMessage]]:
    msgs: list[BaseMessage] = list(state.get("messages") or [])
    last = msgs[-1] if msgs else None
    text = ""
    if last is not None:
        c = getattr(last, "content", "")
        text = c if isinstance(c, str) else str(c)
    reply = (
        "(Chat model disabled. Set INFOVINCI_CHAT_MODEL, or unset it to use Ollama llama3.1:8b.) "
        f"Demo echo: {text!r}"
    )
    return {"messages": [AIMessage(content=reply)]}


def _make_llm_node(model: Any):
    def chat_node(state: MessagesState) -> dict[str, list[Any]]:
        state_messages: list[BaseMessage] = list(state.get("messages") or [])
        latest_user = next(
            (
                str(message.content)
                for message in reversed(state_messages)
                if isinstance(message, HumanMessage)
            ),
            "",
        )
        blog_context = retrieve_blog_context(latest_user)
        system_content = DEFAULT_SYSTEM
        if blog_context:
            logger.info("RAG retrieved %s chars of blog context", len(blog_context))
            system_content = (
                f"{DEFAULT_SYSTEM}\n\n"
                "Relevant Infovinci blog context (use only this material):\n"
                f"{blog_context}\n\n"
                "If the answer is not in the context, say what is missing instead of inventing."
            )
        elif os.environ.get("INFOVINCI_SKIP_RAG", "").lower() not in {"1", "true", "yes"}:
            system_content = (
                f"{DEFAULT_SYSTEM}\n\n"
                "No matching Infovinci blog posts were retrieved for this question. "
                "Say that clearly and do not invent post titles, URLs, or citations."
            )

        messages: list[BaseMessage] = [SystemMessage(content=system_content)]
        messages.extend(state_messages)
        # stream() (not invoke) so LangGraph emits messages/partial SSE during Ollama generation
        response: AIMessage | AIMessageChunk | None = None
        for chunk in model.stream(messages):
            response = chunk if response is None else response + chunk
        if response is None:
            return {"messages": [AIMessage(content="")]}
        if isinstance(response, AIMessageChunk):
            return {"messages": [AIMessage(content=str(response.content or ""))]}
        return {"messages": [response]}

    return chat_node


def _build_and_compile() -> Any:
    model = _load_chat_model()
    builder = StateGraph(MessagesState)
    if model is None:
        builder.add_node("chat", _echo_node)
    else:
        builder.add_node("chat", _make_llm_node(model))
    builder.add_edge(START, "chat")
    builder.add_edge("chat", END)
    # No checkpointer: LangGraph API attaches persistence for `langgraph dev` / deploy.
    return builder.compile()


def _warm_vector_index() -> None:
    """Load Chroma + embedding model once so the first chat is not silent for minutes."""
    if os.environ.get("INFOVINCI_SKIP_RAG", "").lower() in {"1", "true", "yes"}:
        return
    try:
        from infovinci_serve.blog_embedder import get_collection

        get_collection()
        logger.info("Blog vector index warmed for RAG")
    except Exception as exc:
        logger.warning("Blog vector index warmup failed: %s", exc)


def get_compiled_graph() -> Any:
    global _compiled
    if _compiled is None:
        _compiled = _build_and_compile()
    return _compiled


_warm_vector_index()

# Exported for `langgraph.json` → graphs.agent (LangGraph Agent Server / `langgraph dev`).
graph = get_compiled_graph()
