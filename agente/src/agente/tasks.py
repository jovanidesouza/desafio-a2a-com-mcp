"""A Task do A2A: identidade, estado e produto. Guardada em memoria, por processo."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field

ESTADOS_TERMINAIS = {"TASK_STATE_COMPLETED", "TASK_STATE_CANCELED", "TASK_STATE_FAILED"}


@dataclass
class Mensagem:
    messageId: str
    role: str
    parts: list[dict]
    taskId: str | None = None
    contextId: str | None = None

    def to_dict(self) -> dict:
        corpo: dict = {"messageId": self.messageId, "role": self.role, "parts": self.parts}
        if self.taskId:
            corpo["taskId"] = self.taskId
        if self.contextId:
            corpo["contextId"] = self.contextId
        return corpo


@dataclass
class Pendencia:
    """O que a Task guarda enquanto espera a resposta da elicitation.

    O requestState aqui dentro e opaco: o agente so o ecoa de volta ao MCP,
    nunca abre nem interpreta.
    """

    chave: str
    request_state: str
    alternativas: list[str]
    tool_args: dict


@dataclass
class Task:
    id: str
    context_id: str
    state: str = "TASK_STATE_SUBMITTED"
    status_message: Mensagem | None = None
    history: list[Mensagem] = field(default_factory=list)
    artifacts: list[dict] = field(default_factory=list)
    pendencia: Pendencia | None = None

    @property
    def terminal(self) -> bool:
        return self.state in ESTADOS_TERMINAIS

    def to_dict(self) -> dict:
        status: dict = {"state": self.state}
        if self.status_message:
            status["message"] = self.status_message.to_dict()
        return {
            "id": self.id,
            "contextId": self.context_id,
            "status": status,
            "history": [m.to_dict() for m in self.history],
            "artifacts": self.artifacts,
        }


class ArmazemDeTasks:
    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}

    def criar(self) -> Task:
        task = Task(id=f"task-{secrets.token_hex(6)}", context_id=f"ctx-{secrets.token_hex(6)}")
        self._tasks[task.id] = task
        return task

    def obter(self, task_id: str | None) -> Task | None:
        if not task_id:
            return None
        return self._tasks.get(task_id)
