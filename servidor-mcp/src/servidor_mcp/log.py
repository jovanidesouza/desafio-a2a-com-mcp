"""Log de cada request no stderr (nao no modulo logging, por convencao do MCP)."""

from __future__ import annotations

import sys
import time


def registrar(metodo: str | None, id_, traceparent: str | None) -> None:
    carimbo = time.strftime("%Y-%m-%dT%H:%M:%S")
    linha = f"[{carimbo}] method={metodo} id={id_}"
    if traceparent:
        linha += f" traceparent={traceparent}"
    print(linha, file=sys.stderr, flush=True)
