"""The one door to a language model: task-named, provider-agnostic.

account-vision.md §13.21. Call sites ask for a task -- `extract_document` --
never for a provider. Which provider and model answer is configuration
(LLM_PROVIDER, LLM_MODEL_EXTRACT, LLM_API_KEY), so switching is an env change
plus a rerun of the golden-document eval, not an edit.

What may be sent is decided by the caller, and the caller is narrow on purpose:
syllabi, which are course documents. Personal documents are not sent until
their rule is decided (Phase 1 D3), and nothing identifying a user -- no
email, no name, no id -- goes in a request.

Each provider is two pure functions, a request builder and a response reader,
so the shapes are tested without the network. The live call is one place.
Untested against the live APIs until a key exists: the first real parse should
be watched (see Phase 1 decisions).
"""

import base64
import json
import re

import requests

from app.config import settings

TIMEOUT_SECONDS = 90
MAX_OUTPUT_TOKENS = 4096


class NotConfigured(Exception):
    """No provider, model or key: the feature reports itself unavailable."""


class ProviderError(Exception):
    """The provider answered with something unusable, or not at all."""


def configured() -> bool:
    return bool(settings.LLM_PROVIDER and settings.LLM_MODEL_EXTRACT and settings.LLM_API_KEY)


def _b64(content: bytes) -> str:
    return base64.b64encode(content).decode("ascii")


# --- request builders: (url, headers, body) --------------------------------

def openai_request(model: str, key: str, system: str, prompt: str, content: bytes, media_type: str, filename: str):
    if media_type == "application/pdf":
        document = {"type": "file", "file": {
            "filename": filename, "file_data": f"data:application/pdf;base64,{_b64(content)}",
        }}
    else:
        document = {"type": "text", "text": content.decode("utf-8", errors="replace")}
    return (
        "https://api.openai.com/v1/chat/completions",
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": [document, {"type": "text", "text": prompt}]},
            ],
            "response_format": {"type": "json_object"},
            "max_completion_tokens": MAX_OUTPUT_TOKENS,
        },
    )


def gemini_request(model: str, key: str, system: str, prompt: str, content: bytes, media_type: str, filename: str):
    if media_type == "application/pdf":
        document = {"inline_data": {"mime_type": "application/pdf", "data": _b64(content)}}
    else:
        document = {"text": content.decode("utf-8", errors="replace")}
    return (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        # The key as a header, never in the URL, where request logs would keep it.
        {"x-goog-api-key": key, "Content-Type": "application/json"},
        {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [document, {"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": MAX_OUTPUT_TOKENS},
        },
    )


def anthropic_request(model: str, key: str, system: str, prompt: str, content: bytes, media_type: str, filename: str):
    if media_type == "application/pdf":
        document = {"type": "document", "source": {
            "type": "base64", "media_type": "application/pdf", "data": _b64(content),
        }}
    else:
        document = {"type": "text", "text": content.decode("utf-8", errors="replace")}
    return (
        "https://api.anthropic.com/v1/messages",
        {"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
        {
            "model": model,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "system": system,
            "messages": [{"role": "user", "content": [document, {"type": "text", "text": prompt}]}],
        },
    )


# --- response readers: provider JSON -> the model's text -------------------

def openai_text(body: dict) -> str:
    return body["choices"][0]["message"]["content"]


def gemini_text(body: dict) -> str:
    return "".join(part.get("text", "") for part in body["candidates"][0]["content"]["parts"])


def anthropic_text(body: dict) -> str:
    return "".join(block.get("text", "") for block in body["content"] if block.get("type") == "text")


PROVIDERS = {
    "openai": (openai_request, openai_text),
    "gemini": (gemini_request, gemini_text),
    "anthropic": (anthropic_request, anthropic_text),
}


def parse_json(text: str) -> dict:
    """The model's answer as JSON, tolerating a fenced code block around it."""
    cleaned = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ProviderError("The answer was not JSON") from exc
    if not isinstance(value, dict):
        raise ProviderError("The answer was not a JSON object")
    return value


def extract_document(
    content: bytes, media_type: str, filename: str, system: str, prompt: str, *, transport=None,
) -> dict:
    """Read a document into the JSON the prompt describes.

    `transport` stands in for the network in tests: a callable taking
    (url, headers, body) and returning the provider's JSON.
    """
    if not configured():
        raise NotConfigured
    provider = settings.LLM_PROVIDER
    if provider not in PROVIDERS:
        raise NotConfigured
    build, read = PROVIDERS[provider]
    url, headers, body = build(
        settings.LLM_MODEL_EXTRACT, settings.LLM_API_KEY, system, prompt, content, media_type, filename,
    )
    send = transport or _post
    try:
        answer = send(url, headers, body)
        return parse_json(read(answer))
    except ProviderError:
        raise
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError("The provider's answer had an unexpected shape") from exc


def http_post(url: str, headers: dict, body: dict) -> dict:
    try:
        response = requests.post(url, headers=headers, json=body, timeout=TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise ProviderError(f"Couldn't reach the provider: {type(exc).__name__}") from exc
    if response.status_code >= 400:
        # The status alone: a provider's error body can echo the request back.
        raise ProviderError(f"The provider refused the request ({response.status_code})")
    return response.json()


#: The network call extract_document makes. A module name of its own so the
#: test suite can replace it in one place (conftest's _no_llm_network) while
#: `http_post` itself stays testable.
_post = http_post
