"""Entrypoint: sobe o servidor MCP em Streamable HTTP na porta 7301."""

from __future__ import annotations

import os

import uvicorn


def executar() -> None:
    porta = int(os.environ.get("MCP_PORT", "7301"))
    uvicorn.run("servidor_mcp.rpc:app", host="0.0.0.0", port=porta, log_level="warning")


if __name__ == "__main__":
    executar()
