"""The one door to a language model: named by task, independent of provider.

Callers ask for a task (`extract_document`); which provider and model answer is
configuration (`LLM_PROVIDER`, `LLM_MODEL_EXTRACT`, `LLM_API_KEY`). Each provider is
a pure request builder and response reader, so their shapes are tested without the
network; nothing identifying a user is ever sent.
"""

import base64
import json
import re

import requests

from app.config import settings

TIMEOUT_SECONDS = 90
MAX_OUTPUT_TOKENS = 4096


class NotConfigured(Exception):
    """Raised when no usable provider, model and key are configured."""


class ProviderError(Exception):
    """Raised when the provider cannot be reached, refuses, or answers unusably."""


def configured() -> bool:
    """Return whether a provider, model and key are set; the provider is not checked.

    Returns:
        True when all three settings are non-empty.
    """
    return bool(settings.LLM_PROVIDER and settings.LLM_MODEL_EXTRACT and settings.LLM_API_KEY)


def _b64(content: bytes) -> str:
    """Return bytes as base64 text."""
    return base64.b64encode(content).decode("ascii")


# --- request builders: (url, headers, body) --------------------------------

def openai_request(model: str, key: str, system: str, prompt: str, content: bytes, media_type: str, filename: str):
    """Return the (url, headers, body) for an OpenAI chat completion asking for JSON.

    Args:
        model: The provider's model name.
        key: The provider's API key.
        system: The system instruction.
        prompt: The task prompt sent after the document.
        content: The document's bytes.
        media_type: "application/pdf" or "text/plain"; text is decoded as UTF-8.
        filename: The document's file name.

    Returns:
        The request's URL, headers and JSON body.
    """
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
    """Return the (url, headers, body) for a Gemini call asking for JSON.

    The key travels in a header, never in the URL.

    Args:
        model: The provider's model name.
        key: The provider's API key.
        system: The system instruction.
        prompt: The task prompt sent after the document.
        content: The document's bytes.
        media_type: "application/pdf" or "text/plain"; text is decoded as UTF-8.
        filename: The document's file name.

    Returns:
        The request's URL, headers and JSON body.
    """
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
    """Return the (url, headers, body) for an Anthropic Messages API call.

    Args:
        model: The provider's model name.
        key: The provider's API key.
        system: The system instruction.
        prompt: The task prompt sent after the document.
        content: The document's bytes.
        media_type: "application/pdf" or "text/plain"; text is decoded as UTF-8.
        filename: The document's file name.

    Returns:
        The request's URL, headers and JSON body.
    """
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
    """Return the answer text from an OpenAI chat completion response.

    Args:
        body: The parsed JSON response.

    Returns:
        The first choice's message content.
    """
    return body["choices"][0]["message"]["content"]


def gemini_text(body: dict) -> str:
    """Return the answer text from a Gemini response, its parts joined.

    Args:
        body: The parsed JSON response.

    Returns:
        The text of the first candidate's parts, concatenated.
    """
    return "".join(part.get("text", "") for part in body["candidates"][0]["content"]["parts"])


def anthropic_text(body: dict) -> str:
    """Return the answer text from an Anthropic response, its text blocks joined.

    Args:
        body: The parsed JSON response.

    Returns:
        The text of every text block, concatenated.
    """
    return "".join(block.get("text", "") for block in body["content"] if block.get("type") == "text")


PROVIDERS = {
    "openai": (openai_request, openai_text),
    "gemini": (gemini_request, gemini_text),
    "anthropic": (anthropic_request, anthropic_text),
}
"""Each supported `LLM_PROVIDER` value and its (request builder, response reader)."""


def parse_json(text: str) -> dict:
    """Return the model's answer as a JSON object, tolerating a fenced code block.

    Args:
        text: The model's answer.

    Returns:
        The decoded object.

    Raises:
        ProviderError: If the answer is not JSON or not an object.
    """
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
    """Send a document to the configured model and return its JSON answer.

    Args:
        content: The document's bytes.
        media_type: "application/pdf" or "text/plain".
        filename: The document's file name.
        system: The system instruction.
        prompt: The task prompt, describing the JSON wanted.
        transport: Stand-in for the network in tests: a callable taking (url, headers,
            body) and returning the provider's JSON; None makes the real call.

    Returns:
        The model's answer as a dict.

    Raises:
        NotConfigured: If no provider, model or key is set, or the provider is unknown.
        ProviderError: If the provider is unreachable, refuses, or answers with an
            unexpected shape or non-JSON text.
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
    """POST a JSON body to a provider and return its JSON answer (90 s timeout).

    Args:
        url: The provider endpoint.
        headers: Request headers, including the key.
        body: The JSON body.

    Returns:
        The decoded response body.

    Raises:
        ProviderError: If the request fails or the status is 400 or above; the message
            carries only the status, never the provider's body.
    """
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
