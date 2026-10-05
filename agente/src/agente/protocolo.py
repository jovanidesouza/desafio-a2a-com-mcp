"""Constantes e utilitarios de protocolo MCP compartilhados pelo host."""

from __future__ import annotations

import secrets

PROTOCOLO = "2026-07-28"
META_PROTOCOLO = "io.modelcontextprotocol/protocolVersion"
META_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"
META_CLIENT_INFO = "io.modelcontextprotocol/clientInfo"
META_TRACEPARENT = "traceparent"
POLITICA_URI = "politica://uso"
CLIENT_INFO = {"name": "agente-central-de-salas", "version": "1.0.0"}
CAPABILITY_ELICITATION_FORM = {"elicitation": {"form": {}}}


def extrair_versao_politica(conteudo: str) -> str:
    """A primeira linha do markdown declara 'versao: <valor>'."""
    primeira_linha = conteudo.splitlines()[0]
    return primeira_linha.split(":", 1)[1].strip()


def propagar_traceparent(recebido: str | None) -> str:
    """Mesmo trace-id do cliente A2A (quando houver), span-id sempre novo."""
    partes = recebido.split("-") if recebido else []
    trace_id = partes[1] if len(partes) == 4 else secrets.token_hex(16)
    span_id = secrets.token_hex(8)
    return f"00-{trace_id}-{span_id}-01"
