"""Entrypoint: sobe o agente (A2A por fora, host MCP por dentro) na porta 7300."""

from __future__ import annotations

import os

import uvicorn


def executar() -> None:
    porta = int(os.environ.get("AGENTE_PORT", "7300"))
    uvicorn.run("agente.rpc:app", host="0.0.0.0", port=porta, log_level="warning")


if __name__ == "__main__":
    executar()
