"""As tres tools do servidor: listar_salas, consultar_disponibilidade e
reservar_sala com o ciclo completo de MRTR."""

from __future__ import annotations

import json
from datetime import datetime

from mcp.types import ElicitRequestFormParams

from . import politica, request_state
from .dominio import Repositorio
from .erros import ERRO_SEM_ALTERNATIVA, ErroProtocolo, erro_sala_inexistente

CHAVE_ESCOLHA = "reservar_sala:escolha_de_sala"
MENSAGEM_ELICITATION = "A sala pedida esta ocupada nesse intervalo. Escolha uma alternativa."


def _tem_elicitation_form(capabilities: dict | None) -> bool:
    if not isinstance(capabilities, dict):
        return False
    elicitation = capabilities.get("elicitation")
    return isinstance(elicitation, dict) and "form" in elicitation


def _texto_json(estrutura: dict) -> str:
    return json.dumps(estrutura, indent=2, ensure_ascii=False)


def _erro_execucao(mensagem: str) -> dict:
    return {"content": [{"type": "text", "text": mensagem}], "isError": True, "resultType": "complete"}


def _completo(estrutura: dict) -> dict:
    return {
        "content": [{"type": "text", "text": _texto_json(estrutura)}],
        "isError": False,
        "resultType": "complete",
        "structuredContent": estrutura,
    }


def listar_salas(repo: Repositorio) -> dict:
    estrutura = {
        "salas": [
            {"id": s.id, "nome": s.nome, "capacidade": s.capacidade, "recursos": s.recursos}
            for s in repo.salas.values()
        ]
    }
    return _completo(estrutura)


def _validar_pedido(repo: Repositorio, sala_id: str, inicio_str: str, fim_str: str):
    """Devolve (inicio, fim) parseados, ou um dict de erro de execucao pronto."""
    if sala_id not in repo.salas:
        return _erro_execucao(erro_sala_inexistente(sala_id))
    inicio = datetime.fromisoformat(inicio_str)
    fim = datetime.fromisoformat(fim_str)
    mensagem = politica.validar(inicio, fim)
    if mensagem:
        return _erro_execucao(mensagem)
    return inicio, fim


def consultar_disponibilidade(repo: Repositorio, arguments: dict) -> dict:
    sala_id = arguments.get("sala")
    validado = _validar_pedido(repo, sala_id, arguments["inicio"], arguments["fim"])
    if isinstance(validado, dict):
        return validado
    inicio, fim = validado
    conflitos = repo.conflitos(sala_id, inicio, fim)
    estrutura = {
        "sala": sala_id,
        "livre": not conflitos,
        "conflitos": [
            {"id": c.id, "inicio": c.inicio.isoformat(), "fim": c.fim.isoformat(), "responsavel": c.responsavel}
            for c in conflitos
        ],
    }
    return _completo(estrutura)


def _calcular_alternativas(repo: Repositorio, sala_pedida: str, inicio: datetime, fim: datetime) -> list[str]:
    capacidade_minima = repo.salas[sala_pedida].capacidade
    candidatas = [s for s in repo.salas.values() if s.id != sala_pedida and s.capacidade >= capacidade_minima]
    livres = [s for s in candidatas if not repo.conflitos(s.id, inicio, fim)]
    livres.sort(key=lambda s: (s.capacidade, s.id))
    return [s.id for s in livres[:3]]


def _reserva_para_estrutura(reserva, politica_versao: str) -> dict:
    return {
        "reserva": reserva.id,
        "reservado": True,
        "sala": reserva.sala,
        "inicio": reserva.inicio.isoformat(),
        "fim": reserva.fim.isoformat(),
        "responsavel": reserva.responsavel,
        "politica": politica_versao,
        "motivo": None,
    }


def _recusa_para_estrutura(motivo: str) -> dict:
    return {
        "reserva": None,
        "reservado": False,
        "sala": None,
        "inicio": None,
        "fim": None,
        "responsavel": None,
        "politica": None,
        "motivo": motivo,
    }


def reservar_sala(
    repo: Repositorio,
    politica_versao: str,
    capabilities: dict | None,
    arguments: dict,
    input_responses: dict | None,
    estado_recebido: str | None,
) -> dict:
    if estado_recebido:
        return _retomar(repo, politica_versao, input_responses, estado_recebido)
    return _primeira_chamada(repo, politica_versao, capabilities, arguments)


def _primeira_chamada(repo: Repositorio, politica_versao: str, capabilities: dict | None, arguments: dict) -> dict:
    sala_id = arguments.get("sala")
    validado = _validar_pedido(repo, sala_id, arguments["inicio"], arguments["fim"])
    if isinstance(validado, dict):
        return validado
    inicio, fim = validado

    conflitos = repo.conflitos(sala_id, inicio, fim)
    if not conflitos:
        reserva = repo.criar(sala_id, inicio, fim, arguments["responsavel"])
        return _completo(_reserva_para_estrutura(reserva, politica_versao))

    alternativas = _calcular_alternativas(repo, sala_id, inicio, fim)
    if not alternativas:
        return _erro_execucao(ERRO_SEM_ALTERNATIVA)

    if not _tem_elicitation_form(capabilities):
        raise ErroProtocolo(
            -32021,
            f"Client did not declare the form elicitation capability required by resolver '{CHAVE_ESCOLHA}'",
            {"requiredCapabilities": {"elicitation": {"form": {}}}},
        )

    propriedade_sala: dict = {
        "type": "string",
        "title": "Sala",
        "description": "Sala alternativa escolhida",
    }
    if len(alternativas) == 1:
        propriedade_sala["const"] = alternativas[0]
    else:
        propriedade_sala["enum"] = alternativas

    estado = request_state.selar(
        {
            "tool": "reservar_sala",
            "args": {
                "sala": sala_id,
                "inicio": arguments["inicio"],
                "fim": arguments["fim"],
                "responsavel": arguments["responsavel"],
            },
            "alternativas": alternativas,
            "chave": CHAVE_ESCOLHA,
        }
    )

    # ElicitRequestFormParams e o tipo real do SDK oficial para elicitation em
    # form mode; os campos extras do envelope (resultType/inputRequests/
    # requestState) sao o que o SDK publicado nao cobre (ver README).
    elicitation = ElicitRequestFormParams(
        message=MENSAGEM_ELICITATION,
        requestedSchema={
            "type": "object",
            "properties": {"sala": propriedade_sala},
            "required": ["sala"],
        },
    )

    return {
        "resultType": "input_required",
        "inputRequests": {
            CHAVE_ESCOLHA: {
                "method": "elicitation/create",
                "params": elicitation.model_dump(exclude_none=True),
            }
        },
        "requestState": estado,
    }


def _retomar(repo: Repositorio, politica_versao: str, input_responses: dict | None, estado_recebido: str) -> dict:
    payload = request_state.abrir(estado_recebido)
    chave = payload["chave"]
    resposta = (input_responses or {}).get(chave)
    if not isinstance(resposta, dict):
        raise ErroProtocolo(-32602, f"inputResponses nao contem a chave esperada '{chave}'")

    acao = resposta.get("action")
    args_selados = payload["args"]

    if acao in ("decline", "cancel"):
        motivo = "recusado" if acao == "decline" else "cancelado"
        return _completo(_recusa_para_estrutura(motivo))

    if acao != "accept":
        raise ErroProtocolo(-32602, f"action desconhecida: {acao!r}")

    # Os argumentos que o cliente reenviar no retry nao sao confiaveis: so o que
    # foi selado no requestState e usado para reconstruir o pedido original.
    sala_escolhida = (resposta.get("content") or {}).get("sala")
    if sala_escolhida not in payload["alternativas"]:
        raise ErroProtocolo(-32602, "a sala escolhida nao esta entre as alternativas seladas")

    inicio = datetime.fromisoformat(args_selados["inicio"])
    fim = datetime.fromisoformat(args_selados["fim"])
    reserva = repo.criar(sala_escolhida, inicio, fim, args_selados["responsavel"])
    return _completo(_reserva_para_estrutura(reserva, politica_versao))
