"""O requestState do MRTR: opaco para o cliente, mas protegido por integridade.

Formato: "v1.<payload-base64url>.<assinatura-base64url>". O payload e JSON legivel
(a spec so exige integridade, nao sigilo), assinado com HMAC-SHA256 sobre a chave
de REQUEST_STATE_SECRET. Expira entre 5 e 30 minutos depois de emitido (usamos 10).
Carrega tudo que o servidor precisa para reconstruir o pedido original no retry, e
por isso sobrevive a um restart do processo: a verificacao nao depende de nada
guardado em memoria.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import time

VERSAO = "v1"
TTL_SEGUNDOS = 10 * 60
TAMANHO_MINIMO_SEGREDO = 32


class EstadoInvalido(Exception):
    """requestState adulterado, malformado ou expirado: sempre vira -32602."""


def verificar_configuracao() -> None:
    """Falha cedo e alto se REQUEST_STATE_SECRET nao estiver configurado."""
    valor = os.environ.get("REQUEST_STATE_SECRET", "")
    if len(valor) < TAMANHO_MINIMO_SEGREDO:
        print(
            "REQUEST_STATE_SECRET ausente ou curto demais (minimo "
            f"{TAMANHO_MINIMO_SEGREDO} caracteres). Gere um com:\n"
            '  python3 -c "import secrets; print(secrets.token_hex(32))"\n'
            "e exporte antes de subir o servidor.",
            file=sys.stderr,
        )
        raise SystemExit(1)


def _chave_secreta() -> bytes:
    valor = os.environ.get("REQUEST_STATE_SECRET", "")
    if len(valor) < TAMANHO_MINIMO_SEGREDO:
        raise RuntimeError("REQUEST_STATE_SECRET ausente ou curto demais")
    return valor.encode("utf-8")


def _b64(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados).rstrip(b"=").decode("ascii")


def _unb64(texto: str) -> bytes:
    preenchimento = "=" * (-len(texto) % 4)
    return base64.urlsafe_b64decode(texto + preenchimento)


def selar(payload: dict) -> str:
    corpo = dict(payload)
    corpo["exp"] = int(time.time()) + TTL_SEGUNDOS
    payload_b64 = _b64(json.dumps(corpo, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    assinatura = hmac.new(_chave_secreta(), payload_b64.encode("ascii"), hashlib.sha256).digest()
    return f"{VERSAO}.{payload_b64}.{_b64(assinatura)}"


def abrir(estado: str) -> dict:
    try:
        versao, payload_b64, assinatura_b64 = estado.split(".")
        if versao != VERSAO:
            raise ValueError("versao de requestState desconhecida")
        esperada = hmac.new(_chave_secreta(), payload_b64.encode("ascii"), hashlib.sha256).digest()
        recebida = _unb64(assinatura_b64)
        if not hmac.compare_digest(esperada, recebida):
            raise ValueError("assinatura invalida")
        payload = json.loads(_unb64(payload_b64))
        if payload.get("exp", 0) < int(time.time()):
            raise ValueError("requestState expirado")
        return payload
    except EstadoInvalido:
        raise
    except Exception as exc:
        raise EstadoInvalido("requestState invalido ou expirado") from exc
