"""Dispatcher JSON-RPC do agente A2A: GET do card e POST /a2a com SendMessage/GetTask."""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from . import ponte
from .card import construir_agent_card
from .mcp_client import ClienteMCP
from .tasks import ArmazemDeTasks

MCP_URL = os.environ.get("MCP_URL", "http://localhost:7301")

_store = ArmazemDeTasks()
_mcp: ClienteMCP | None = None


@asynccontextmanager
async def _lifespan(_app: Starlette):
    global _mcp
    _mcp = ClienteMCP(MCP_URL)
    await _mcp.descobrir()
    try:
        yield
    finally:
        await _mcp.fechar()


async def endpoint_card(_request: Request) -> JSONResponse:
    return JSONResponse(construir_agent_card())


async def endpoint_a2a(request: Request) -> JSONResponse:
    try:
        corpo = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(
            {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "JSON malformado"}},
            status_code=400,
        )

    id_ = corpo.get("id")
    metodo = corpo.get("method")
    params = corpo.get("params") or {}
    traceparent = request.headers.get("traceparent")

    assert _mcp is not None, "lifespan deveria ter inicializado o cliente MCP"

    try:
        if metodo == "SendMessage":
            resultado = await ponte.enviar_mensagem(_store, _mcp, params, traceparent)
        elif metodo == "GetTask":
            resultado = ponte.obter_task(_store, params)
        else:
            return JSONResponse(
                {"jsonrpc": "2.0", "id": id_, "error": {"code": -32601, "message": f"metodo desconhecido: {metodo}"}},
                status_code=400,
            )
    except ponte.ErroA2A as exc:
        return JSONResponse(
            {"jsonrpc": "2.0", "id": id_, "error": {"code": -32000, "message": str(exc)}},
            status_code=200,
        )

    return JSONResponse({"jsonrpc": "2.0", "id": id_, "result": resultado}, status_code=200)


app = Starlette(
    routes=[
        Route("/.well-known/agent-card.json", endpoint_card, methods=["GET"]),
        Route("/a2a", endpoint_a2a, methods=["POST"]),
    ],
    lifespan=_lifespan,
)
