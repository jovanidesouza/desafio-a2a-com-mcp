"""inputSchema/outputSchema das tres tools, gerados via pydantic (dependencia do
pacote mcp) para que o JSON Schema produzido tenha a mesma forma de um servidor
MCP real construido com esse SDK."""

from __future__ import annotations

from mcp.types import Tool
from pydantic import BaseModel


class _ListarSalasArguments(BaseModel):
    pass


class _ConsultarDisponibilidadeArguments(BaseModel):
    sala: str
    inicio: str
    fim: str


class _ReservarSalaArguments(BaseModel):
    sala: str
    inicio: str
    fim: str
    responsavel: str


class SalaOut(BaseModel):
    id: str
    nome: str
    capacidade: int
    recursos: list[str]


class ListaDeSalas(BaseModel):
    salas: list[SalaOut]


class ConflitoOut(BaseModel):
    id: str
    inicio: str
    fim: str
    responsavel: str


class Disponibilidade(BaseModel):
    sala: str
    livre: bool
    conflitos: list[ConflitoOut]


class ReservaOut(BaseModel):
    reserva: str | None
    reservado: bool
    sala: str | None
    inicio: str | None
    fim: str | None
    responsavel: str | None
    politica: str | None
    motivo: str | None = None


def _schema(modelo: type[BaseModel], titulo: str) -> dict:
    esquema = modelo.model_json_schema()
    esquema["title"] = titulo
    return esquema


def _tool(nome: str, descricao: str, input_schema: dict, output_schema: dict) -> dict:
    # Validado contra o Tool real do SDK oficial (mcp.types.Tool): garante que
    # name/inputSchema/outputSchema tem a forma que um servidor MCP de verdade produz.
    tool = Tool(name=nome, description=descricao, inputSchema=input_schema, outputSchema=output_schema)
    return tool.model_dump(exclude_none=True)


def construir_tools_list() -> list[dict]:
    return [
        _tool(
            "listar_salas",
            "Lista todas as salas com capacidade e recursos.",
            _schema(_ListarSalasArguments, "listar_salasArguments"),
            _schema(ListaDeSalas, "ListaDeSalas"),
        ),
        _tool(
            "consultar_disponibilidade",
            "Diz se uma sala esta livre no intervalo, e quais reservas conflitam.",
            _schema(_ConsultarDisponibilidadeArguments, "consultar_disponibilidadeArguments"),
            _schema(Disponibilidade, "Disponibilidade"),
        ),
        _tool(
            "reservar_sala",
            "Reserva uma sala. Se o intervalo estiver ocupado, pergunta qual alternativa usar.",
            _schema(_ReservarSalaArguments, "reservar_salaArguments"),
            _schema(ReservaOut, "ReservaOut"),
        ),
    ]
