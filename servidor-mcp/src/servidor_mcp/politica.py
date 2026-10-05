"""As quatro regras da politica de uso, na ordem que o enunciado fixa: janela,
intervalo e so entao duracao."""

from __future__ import annotations

from datetime import datetime, time, timedelta

from .erros import ERRO_DURACAO, ERRO_INTERVALO, ERRO_JANELA

_ABERTURA = time(8, 0)
_FECHAMENTO = time(20, 0)
_DURACAO_MAXIMA = timedelta(hours=2)


def validar(inicio: datetime, fim: datetime) -> str | None:
    """Devolve a mensagem de erro exata, ou None se o intervalo e valido."""
    if not (_ABERTURA <= inicio.time() <= _FECHAMENTO) or not (_ABERTURA <= fim.time() <= _FECHAMENTO):
        return ERRO_JANELA
    if fim <= inicio:
        return ERRO_INTERVALO
    if fim - inicio > _DURACAO_MAXIMA:
        return ERRO_DURACAO
    return None
