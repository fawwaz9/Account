"""BYOAI routes under `/api/assistant`: your digest, read by your own assistant (Phase 4 item 7).

Authenticated by an assistant token (D4), never by a session: a session token is
refused here, and an assistant token is refused everywhere else, because it is not
a JWT. Two doors over the same digest: a plain endpoint, and a small MCP server
(stateless JSON-RPC over HTTP) with one tool. Neither reads anything but the digest.
"""

import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from app._database.dependencies import DBSession
from app._database.identity import act_as
from app.Auth.services.client_address import client_of
from app.Auth.services.login_throttle import SlidingWindowLimiter
from app.Briefing.schemas.digest import Digest
from app.Briefing.services.assistant_service import resolve
from app.Briefing.services.digest_service import build_digest

router = APIRouter()

#: Failed token attempts allowed per address in the window, then refused. A token
#: can't be guessed (256 bits); this keeps a broken client from hammering the lookup.
failed_attempts = SlidingWindowLimiter(max_attempts=30)

#: The MCP protocol versions this server speaks, newest first.
MCP_VERSIONS = ("2025-06-18", "2025-03-26")
TOOL = {
    "name": "get_briefing",
    "title": "Today's briefing",
    "description": (
        "The student's day from their Account app: today's calendar, work due and overdue, exams in the "
        "next week, deadlines at risk, the week's load and free time. No money and nothing else."
    ),
    "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
}
UNAUTHORIZED = {"WWW-Authenticate": 'Bearer realm="account-assistant"'}


def _allowed_origins() -> set[str]:
    """The browser origins the API answers, as configured for CORS."""
    return {o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",") if o.strip()}


def assistant_user(request: Request, db: DBSession, authorization: str | None = Header(default=None)):
    """Resolve the bearer assistant token to its owner, and act as them; else refuse.

    Args:
        request: The incoming request, for the caller's address.
        db: Request-scoped database session.
        authorization: The `Authorization` header.

    Returns:
        The owner's id; the session now acts as them, so row security applies.

    Raises:
        HTTPException: 403 for a browser origin the API doesn't serve; 429 after too
            many failed tokens from this address; 401 for a missing, malformed,
            session, unknown or revoked token.
    """
    # An assistant calls from a server, not a page. A browser page from anywhere
    # else is refused before the token is even read: the MCP transport's guard
    # against a page talking to this server on someone's behalf.
    origin = request.headers.get("origin")
    if origin is not None and origin not in _allowed_origins():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not from this origin")
    client = client_of(request)
    retry = failed_attempts.retry_after(client)
    if retry is not None:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many attempts",
                            headers={"Retry-After": str(retry)})
    scheme, _, value = (authorization or "").partition(" ")
    user_id = resolve(db, value.strip()) if scheme.lower() == "bearer" else None
    if user_id is None:
        failed_attempts.record_attempt(client)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not a valid assistant token",
                            headers=UNAUTHORIZED)
    act_as(db, user_id)
    return user_id


@router.get("/digest", response_model=Digest, responses={401: {"description": "Not a valid assistant token"}})
def assistant_digest(db: DBSession, user_id=Depends(assistant_user)):
    """Return the token owner's digest for today: the one thing a token can read.

    Args:
        db: Request-scoped database session, acting as the token's owner.
        user_id: The token's owner.

    Returns:
        The digest, with its plain-text rendering; no money (D8).

    Raises:
        HTTPException: 401 for anything but a live assistant token.
    """
    digest = build_digest(db, user_id)
    if digest is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not a valid assistant token",
                            headers=UNAUTHORIZED)
    return digest


def _error(request_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


class RpcMessage(BaseModel):
    """One JSON-RPC 2.0 message from an MCP client.

    Attributes:
        jsonrpc: Must be "2.0".
        method: The method called.
        id: The request's id; absent on a notification.
        params: The method's parameters.
    """
    model_config = ConfigDict(extra="allow")
    jsonrpc: str
    method: str
    id: int | str | None = None
    params: dict | None = None


# Only POST is served: a GET, the way a client asks for a server-to-client stream,
# is answered 405 by the framework, which is what the MCP transport expects from a
# server that answers each request directly.
@router.post("/mcp", responses={401: {"description": "Not a valid assistant token"}})
def mcp(message: RpcMessage, db: DBSession, user_id=Depends(assistant_user)):
    """Answer one MCP JSON-RPC message: initialize, ping, tools/list, or the one tool.

    Stateless: each request stands alone, authenticated by the assistant token. The
    one tool returns the same digest as `/api/assistant/digest`.

    Args:
        message: The JSON-RPC message.
        db: Request-scoped database session, acting as the token's owner.
        user_id: The token's owner.

    Returns:
        The JSON-RPC response; 202 with no body for a notification.
    """
    if message.jsonrpc != "2.0":
        return JSONResponse(_error(message.id, -32600, "Invalid request"), status_code=400)
    method, request_id = message.method, message.id
    if "id" not in message.model_fields_set:  # a notification: nothing to answer
        return Response(status_code=status.HTTP_202_ACCEPTED)

    if method == "initialize":
        asked = (message.params or {}).get("protocolVersion")
        result = {
            "protocolVersion": asked if asked in MCP_VERSIONS else MCP_VERSIONS[0],
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "account-briefing", "version": "1"},
            "instructions": "Call get_briefing for the student's day. It carries no money and nothing private beyond the day's plan.",
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": [TOOL]}
    elif method == "tools/call":
        name = (message.params or {}).get("name")
        if name != TOOL["name"]:
            return JSONResponse(_error(request_id, -32602, f"Unknown tool: {name}"))
        digest = build_digest(db, user_id)
        result = {
            "content": [{"type": "text", "text": digest.text}],
            "structuredContent": digest.model_dump(mode="json"),
            "isError": False,
        }
    else:
        return JSONResponse(_error(request_id, -32601, f"Method not found: {method}"))
    return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": result})
