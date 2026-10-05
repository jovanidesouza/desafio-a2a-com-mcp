"""Dominio: salas e reservas, carregados dos JSON em dados/ e mantidos em memoria."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


def localizar_dados() -> Path:
    """Acha a pasta dados/ do starter, subindo a arvore a partir deste arquivo.

    Pode ser sobrescrita com a variavel de ambiente DADOS_DIR (util para testes).
    """
    env = os.environ.get("DADOS_DIR")
    if env:
        return Path(env)
    atual = Path(__file__).resolve().parent
    for _ in range(6):
        candidato = atual / "dados"
        if (candidato / "salas.json").exists():
            return candidato
        atual = atual.parent
    raise RuntimeError("nao encontrei a pasta dados/ com salas.json (defina DADOS_DIR)")


@dataclass
class Sala:
    id: str
    nome: str
    capacidade: int
    recursos: list[str]


@dataclass
class Reserva:
    id: str
    sala: str
    inicio: datetime
    fim: datetime
    responsavel: str


def carregar_salas(dados_dir: Path) -> list[Sala]:
    bruto = json.loads((dados_dir / "salas.json").read_text(encoding="utf-8"))
    return [Sala(**item) for item in bruto]


def carregar_reservas(dados_dir: Path) -> list[Reserva]:
    bruto = json.loads((dados_dir / "reservas.json").read_text(encoding="utf-8"))
    return [
        Reserva(
            id=item["id"],
            sala=item["sala"],
            inicio=datetime.fromisoformat(item["inicio"]),
            fim=datetime.fromisoformat(item["fim"]),
            responsavel=item["responsavel"],
        )
        for item in bruto
    ]


def _sobrepoe(a_inicio: datetime, a_fim: datetime, b_inicio: datetime, b_fim: datetime) -> bool:
    return a_inicio < b_fim and b_inicio < a_fim


class Repositorio:
    """Estado em memoria do processo. Nao sobrevive a um restart (e nao precisa)."""

    def __init__(self, salas: list[Sala], reservas: list[Reserva]):
        self.salas: dict[str, Sala] = {s.id: s for s in salas}
        self.reservas: dict[str, Reserva] = {r.id: r for r in reservas}
        numeros = [int(r.id.split("-")[1]) for r in reservas if r.id.startswith("res-")]
        self._contador = max(numeros, default=0)

    def conflitos(self, sala_id: str, inicio: datetime, fim: datetime) -> list[Reserva]:
        return [
            r for r in self.reservas.values()
            if r.sala == sala_id and _sobrepoe(r.inicio, r.fim, inicio, fim)
        ]

    def criar(self, sala_id: str, inicio: datetime, fim: datetime, responsavel: str) -> Reserva:
        self._contador += 1
        reserva = Reserva(f"res-{self._contador:04d}", sala_id, inicio, fim, responsavel)
        self.reservas[reserva.id] = reserva
        return reserva
