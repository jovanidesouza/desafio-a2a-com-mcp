"""Dispatcher JSON-RPC sobre Streamable HTTP, endpoint unico POST /mcp.

Limitacao de SDK registrada aqui, nao so no README: a versao publicada do pacote
`mcp` (1.30.0, a mais recente no momento desta entrega) nao tem o envelope MRTR
deste desafio (`resultType`, `inputRequests`, `requestState`, os codigos -32020 e
-32021). O `CallToolResult` real do SDK so tem `content`, `structuredContent` e
`isError`; o recurso assincrono mais proximo (`mcp.server.experimental.tasks`) e
um mecanismo de polling via `tasks/result`, de forma e proposito diferentes do
MRTR descrito no enunciado. Por isso o transporte e o dispatcher abaixo sao
escritos a mao, reaproveitando do SDK oficial o que de fato se aplica: os tipos
de schema (`pydantic`, usado em schemas.py do jeito que o `mcp` usa por baixo
para gerar inputSchema/outputSchema) e o formato dos tipos de elicitation
(`mcp.types.ElicitRequestFormParams`, `ElicitationCapability`), cuja forma
inspira os dicts montados em tools.py.
"""

from __future__ import annotations

import json

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from . import tools as tools_mod
from .dominio import Repositorio, carregar_reservas, carregar_salas, localizar_dados
from .erros import ErroProtocolo
from .log import registrar
from .request_state import EstadoInvalido, verificar_configuracao
from .resources import POLITICA_URI, extrair_versao
from .schemas import construir_tools_list

PROTOCOLO = "2026-07-28"
META_PROTOCOLO = "io.modelcontextprotocol/protocolVersion"
META_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"
META_TRACEPARENT = "traceparent"
SERVER_INFO = {"name": "central-de-salas", "version": "1.0.0"}

verificar_configuracao()

_dados_dir = localizar_dados()
_repo = Repositorio(carregar_salas(_dados_dir), carregar_reservas(_dados_dir))
_politica_texto = (_dados_dir / "politica-de-uso.md").read_text(encoding="utf-8")
_politica_versao = extrair_versao(_politica_texto)
_tools_list = construir_tools_list()


def _erro_json(id_, code: int, message: str, data: dict | None = None, http_status: int = 400) -> JSONResponse:
    corpo: dict = {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}
    if data is not None:
        corpo["error"]["data"] = data
    return JSONResponse(corpo, status_code=http_status)


def _resultado_json(id_, resultado: dict) -> JSONResponse:
    resultado = {**resultado, "_meta": {"io.modelcontextprotocol/serverInfo": SERVER_INFO}}
    return JSONResponse({"jsonrpc": "2.0", "id": id_, "result": resultado}, status_code=200)


async def endpoint_mcp(request: Request) -> JSONResponse:
    try:
        corpo = await request.json()
    except json.JSONDecodeError:
        return _erro_json(None, -32700, "corpo invalido: JSON malformado")

    id_ = corpo.get("id")
    metodo = corpo.get("method")
    params = corpo.get("params") or {}
    meta = params.get("_meta") or {}

    registrar(metodo, id_, meta.get(META_TRACEPARENT))

    if META_PROTOCOLO not in meta or META_CAPABILITIES not in meta:
        return _erro_json(
            id_,
            -32602,
            "faltam campos obrigatorios em _meta: "
            f"{META_PROTOCOLO} e/ou {META_CAPABILITIES}",
        )

    nome_esperado = None
    if metodo == "tools/call":
        nome_esperado = params.get("name")
    elif metodo == "resources/read":
        nome_esperado = params.get("uri")

    cabecalhos_batem = (
        request.headers.get("mcp-protocol-version") == meta.get(META_PROTOCOLO)
        and request.headers.get("mcp-method") == metodo
        and (nome_esperado is None or request.headers.get("mcp-name") == nome_esperado)
    )
    if not cabecalhos_batem:
        return _erro_json(id_, -32020, "headers do transporte nao batem com o corpo do request")

    capabilities = meta.get(META_CAPABILITIES) or {}

    try:
        if metodo == "tools/list":
            return _resultado_json(id_, {"cacheScope": "private", "resultType": "complete", "tools": _tools_list})

        if metodo == "tools/call":
            nome = params.get("name")
            arguments = params.get("arguments") or {}
            input_responses = params.get("inputResponses")
            estado_recebido = params.get("requestState")
            if nome == "listar_salas":
                resultado = tools_mod.listar_salas(_repo)
            elif nome == "consultar_disponibilidade":
                resultado = tools_mod.consultar_disponibilidade(_repo, arguments)
            elif nome == "reservar_sala":
                resultado = tools_mod.reservar_sala(
                    _repo, _politica_versao, capabilities, arguments, input_responses, estado_recebido
                )
            else:
                return _erro_json(id_, -32602, f"tool desconhecida: {nome}")
            return _resultado_json(id_, resultado)

        if metodo == "resources/read":
            uri = params.get("uri")
            if uri != POLITICA_URI:
                return _erro_json(id_, -32602, f"resource desconhecido: {uri}")
            return _resultado_json(
                id_,
                {
                    "cacheScope": "private",
                    "resultType": "complete",
                    "ttlMs": 0,
                    "contents": [{"uri": POLITICA_URI, "mimeType": "text/markdown", "text": _politica_texto}],
                },
            )

        return _erro_json(id_, -32601, f"metodo desconhecido: {metodo}")
    except ErroProtocolo as exc:
        return _erro_json(id_, exc.code, exc.message, exc.data)
    except EstadoInvalido as exc:
        return _erro_json(id_, -32602, str(exc))


app = Starlette(routes=[Route("/mcp", endpoint_mcp, methods=["POST"])])
