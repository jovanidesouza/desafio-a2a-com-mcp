"""Parser do formato fixo de pedido e de continuacao. Nada de linguagem natural."""

from __future__ import annotations

import re

_PADRAO_PEDIDO = re.compile(
    r"^reservar\s+sala=(?P<sala>\S+)\s+inicio=(?P<inicio>\S+)\s+fim=(?P<fim>\S+)\s+responsavel=(?P<responsavel>.+)$"
)
_PADRAO_ESCOLHA = re.compile(r"^escolha=(?P<valor>.+)$")


def parse_pedido(texto: str) -> dict | None:
    encontrado = _PADRAO_PEDIDO.match(texto.strip())
    if not encontrado:
        return None
    return {
        "sala": encontrado.group("sala"),
        "inicio": encontrado.group("inicio"),
        "fim": encontrado.group("fim"),
        "responsavel": encontrado.group("responsavel"),
    }


def parse_escolha(texto: str) -> str | None:
    encontrado = _PADRAO_ESCOLHA.match(texto.strip())
    return encontrado.group("valor") if encontrado else None
