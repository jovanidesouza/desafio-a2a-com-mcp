"""O resource politica://uso."""

from __future__ import annotations

POLITICA_URI = "politica://uso"


def extrair_versao(conteudo: str) -> str:
    """A primeira linha do markdown declara 'versao: <valor>'."""
    primeira_linha = conteudo.splitlines()[0]
    return primeira_linha.split(":", 1)[1].strip()
