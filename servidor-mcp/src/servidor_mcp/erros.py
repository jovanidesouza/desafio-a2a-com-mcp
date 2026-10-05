"""Mensagens exatas das regras de negocio e o erro de protocolo JSON-RPC."""

from __future__ import annotations


class ErroProtocolo(Exception):
    """Erro de protocolo JSON-RPC: vira {"error": {code, message, data}} na resposta."""

    def __init__(self, code: int, message: str, data: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


def erro_sala_inexistente(sala_id: str) -> str:
    return f"Sala inexistente: {sala_id}"


ERRO_JANELA = "Fora da janela de uso: a politica permite reservas entre 08:00 e 20:00"
ERRO_DURACAO = "Duracao acima do limite: a politica permite no maximo 2 horas"
ERRO_INTERVALO = "Intervalo invalido: fim deve ser posterior a inicio"
ERRO_SEM_ALTERNATIVA = "Sem alternativas disponiveis no intervalo"
