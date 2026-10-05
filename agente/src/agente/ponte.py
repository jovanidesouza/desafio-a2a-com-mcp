"""A ponte: aqui o input_required do MCP vira TASK_STATE_INPUT_REQUIRED, e e
aqui que o requestState guardado volta para o servidor no retry com id novo.

O agente nao decide regra de sala nenhuma: so traduz entre os dois protocolos.
"""

from __future__ import annotations

import json
import secrets

from . import formato
from .mcp_client import ClienteMCP, ErroProtocoloMCP
from .protocolo import propagar_traceparent
from .tasks import ArmazemDeTasks, Mensagem, Pendencia, Task


class ErroA2A(Exception):
    """Erro de protocolo A2A: SendMessage/GetTask invalidos viram {"error": ...}."""


def _texto_de(resultado: dict) -> str:
    return " ".join(p.get("text", "") for p in resultado.get("content") or [])


def _nova_mensagem_usuario(mensagem_in: dict, task_id: str | None = None) -> Mensagem:
    return Mensagem(
        messageId=mensagem_in.get("messageId") or f"msg-{secrets.token_hex(6)}",
        role="ROLE_USER",
        parts=mensagem_in.get("parts") or [],
        taskId=task_id,
    )


def _adicionar_mensagem_agente(task: Task, texto: str) -> None:
    msg = Mensagem(
        messageId=f"msg-{secrets.token_hex(6)}",
        role="ROLE_AGENT",
        parts=[{"text": texto}],
        taskId=task.id,
        contextId=task.context_id,
    )
    task.status_message = msg
    task.history.append(msg)


def _finalizar(task: Task, estado: str, texto: str) -> None:
    task.state = estado
    task.pendencia = None
    _adicionar_mensagem_agente(task, texto)


def _concluir_com_reserva(task: Task, resultado: dict) -> None:
    estrutura = resultado.get("structuredContent") or {}
    artifact = {
        "artifactId": f"art-{secrets.token_hex(6)}",
        "name": "reserva",
        "parts": [
            {
                "text": json.dumps(
                    {
                        "reserva": estrutura.get("reserva"),
                        "sala": estrutura.get("sala"),
                        "inicio": estrutura.get("inicio"),
                        "fim": estrutura.get("fim"),
                        "responsavel": estrutura.get("responsavel"),
                        "politica": estrutura.get("politica"),
                    },
                    ensure_ascii=False,
                )
            }
        ],
    }
    task.artifacts.append(artifact)
    task.pendencia = None
    task.state = "TASK_STATE_COMPLETED"
    _adicionar_mensagem_agente(task, f"Reserva {estrutura.get('reserva')} confirmada na {estrutura.get('sala')}.")


def _pausar(task: Task, resultado: dict, tool_args: dict) -> None:
    pedidos = resultado.get("inputRequests") or {}
    chave = next(iter(pedidos), None)
    schema = ((pedidos.get(chave) or {}).get("params") or {}).get("requestedSchema") or {}
    campo = (schema.get("properties") or {}).get("sala", {})
    alternativas = campo.get("enum") or ([campo["const"]] if "const" in campo else [])
    task.pendencia = Pendencia(
        chave=chave,
        request_state=resultado.get("requestState"),
        alternativas=list(alternativas),
        tool_args=tool_args,
    )
    task.state = "TASK_STATE_INPUT_REQUIRED"
    _adicionar_mensagem_agente(task, "alternativas: " + ", ".join(alternativas))


async def _iniciar(task: Task, mcp: ClienteMCP, texto: str, traceparent_recebido: str | None) -> None:
    pedido = formato.parse_pedido(texto)
    if pedido is None:
        _finalizar(
            task,
            "TASK_STATE_FAILED",
            "Pedido invalido: formato esperado "
            "'reservar sala=<id> inicio=<iso8601> fim=<iso8601> responsavel=<nome>'",
        )
        return

    traceparent = propagar_traceparent(traceparent_recebido)
    try:
        resultado = await mcp.chamar_tool("reservar_sala", pedido, traceparent)
    except ErroProtocoloMCP as exc:
        _finalizar(task, "TASK_STATE_FAILED", f"Erro de protocolo MCP: {exc.message}")
        return

    if resultado.get("resultType") == "input_required":
        _pausar(task, resultado, pedido)
        return
    if resultado.get("isError"):
        _finalizar(task, "TASK_STATE_FAILED", _texto_de(resultado))
        return
    _concluir_com_reserva(task, resultado)


async def _continuar(task: Task, mcp: ClienteMCP, texto: str, traceparent_recebido: str | None) -> None:
    if task.state != "TASK_STATE_INPUT_REQUIRED" or task.pendencia is None:
        raise ErroA2A(f"Task {task.id} nao esta aguardando input")

    valor = formato.parse_escolha(texto)
    if valor is None:
        raise ErroA2A("Mensagem de continuacao invalida: esperado 'escolha=<valor>'")

    pendencia = task.pendencia
    traceparent = propagar_traceparent(traceparent_recebido)

    if valor == "recusar":
        try:
            resultado = await mcp.chamar_tool(
                "reservar_sala",
                pendencia.tool_args,
                traceparent,
                input_responses={pendencia.chave: {"action": "decline"}},
                request_state=pendencia.request_state,
            )
        except ErroProtocoloMCP as exc:
            _finalizar(task, "TASK_STATE_FAILED", f"Erro de protocolo MCP: {exc.message}")
            return
        if resultado.get("isError"):
            _finalizar(task, "TASK_STATE_FAILED", _texto_de(resultado))
        else:
            _finalizar(task, "TASK_STATE_CANCELED", "Reserva recusada.")
        return

    if valor not in pendencia.alternativas:
        _adicionar_mensagem_agente(task, "alternativas: " + ", ".join(pendencia.alternativas))
        return

    try:
        resultado = await mcp.chamar_tool(
            "reservar_sala",
            pendencia.tool_args,
            traceparent,
            input_responses={pendencia.chave: {"action": "accept", "content": {"sala": valor}}},
            request_state=pendencia.request_state,
        )
    except ErroProtocoloMCP as exc:
        _finalizar(task, "TASK_STATE_FAILED", f"Erro de protocolo MCP: {exc.message}")
        return

    if resultado.get("isError"):
        _finalizar(task, "TASK_STATE_FAILED", _texto_de(resultado))
        return
    _concluir_com_reserva(task, resultado)


async def enviar_mensagem(
    store: ArmazemDeTasks, mcp: ClienteMCP, params: dict, traceparent_recebido: str | None
) -> dict:
    mensagem_in = params.get("message") or {}
    texto = " ".join(p.get("text", "") for p in mensagem_in.get("parts") or [])
    task_id = mensagem_in.get("taskId")

    if task_id:
        task = store.obter(task_id)
        if task is None:
            raise ErroA2A(f"Task desconhecida: {task_id}")
        if task.terminal:
            raise ErroA2A(f"Task {task_id} ja esta em estado terminal ({task.state})")
        task.history.append(_nova_mensagem_usuario(mensagem_in, task_id))
        await _continuar(task, mcp, texto, traceparent_recebido)
        return {"task": task.to_dict()}

    task = store.criar()
    task.history.append(_nova_mensagem_usuario(mensagem_in))
    task.state = "TASK_STATE_WORKING"
    await _iniciar(task, mcp, texto, traceparent_recebido)
    return {"task": task.to_dict()}


def obter_task(store: ArmazemDeTasks, params: dict) -> dict:
    task = store.obter(params.get("id"))
    if task is None:
        raise ErroA2A(f"Task desconhecida: {params.get('id')}")
    return {"task": task.to_dict()}
