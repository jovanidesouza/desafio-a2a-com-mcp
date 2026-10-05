"""O agente como host MCP: descobre as tools por tools/list, le o resource da
politica e chama o servidor MCP sempre com _meta e headers completos, sem
carregar lista fixa de ferramentas no codigo."""

from __future__ import annotations

import itertools

import httpx

from .protocolo import (
    CAPABILITY_ELICITATION_FORM,
    CLIENT_INFO,
    META_CAPABILITIES,
    META_CLIENT_INFO,
    META_PROTOCOLO,
    META_TRACEPARENT,
    POLITICA_URI,
    PROTOCOLO,
    extrair_versao_politica,
)

_contador_id = itertools.count(1)


def _novo_id() -> str:
    return f"agente-{next(_contador_id)}"


class ErroProtocoloMCP(Exception):
    def __init__(self, code: int | None, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class ClienteMCP:
    """Sem sessao: cada chamada carrega seus proprios _meta e headers.

    O objeto HTTP fica vivo entre chamadas (pooling de conexao), o que e
    normal e recomendado - a ausencia de sessao e sobre o protocolo, nao
    sobre o processo.
    """

    def __init__(self, base_url: str):
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(timeout=30.0)
        self.tools: dict[str, dict] = {}
        self.politica_versao: str | None = None

    async def fechar(self) -> None:
        await self._http.aclose()

    def _meta(self, traceparent: str | None) -> dict:
        meta = {
            META_PROTOCOLO: PROTOCOLO,
            META_CLIENT_INFO: CLIENT_INFO,
            META_CAPABILITIES: CAPABILITY_ELICITATION_FORM,
        }
        if traceparent:
            meta[META_TRACEPARENT] = traceparent
        return meta

    async def _chamar(self, metodo: str, params: dict, nome: str | None, traceparent: str | None) -> dict:
        corpo = {
            "jsonrpc": "2.0",
            "id": _novo_id(),
            "method": metodo,
            "params": {**params, "_meta": self._meta(traceparent)},
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOLO,
            "Mcp-Method": metodo,
        }
        if nome:
            headers["Mcp-Name"] = nome
        resposta = await self._http.post(f"{self._base_url}/mcp", json=corpo, headers=headers)
        dados = resposta.json()
        if "error" in dados:
            erro = dados["error"]
            raise ErroProtocoloMCP(erro.get("code"), erro.get("message", ""))
        return dados["result"]

    async def descobrir(self) -> None:
        """tools/list seguido da leitura do resource, sempre antes do 1o tools/call."""
        resultado = await self._chamar("tools/list", {}, None, None)
        self.tools = {t["name"]: t for t in resultado.get("tools", [])}

        resultado = await self._chamar("resources/read", {"uri": POLITICA_URI}, POLITICA_URI, None)
        conteudos = resultado.get("contents") or []
        texto = conteudos[0].get("text", "") if conteudos else ""
        self.politica_versao = extrair_versao_politica(texto) if texto else None

    async def chamar_tool(
        self,
        nome: str,
        arguments: dict,
        traceparent: str | None,
        input_responses: dict | None = None,
        request_state: str | None = None,
    ) -> dict:
        if nome not in self.tools:
            raise ErroProtocoloMCP(None, f"tool nao descoberta via tools/list: {nome}")
        params: dict = {"name": nome, "arguments": arguments}
        if input_responses is not None:
            params["inputResponses"] = input_responses
        if request_state is not None:
            params["requestState"] = request_state
        return await self._chamar("tools/call", params, nome, traceparent)
