"""Leitura do mapa de offsets (mapa_ecu.toml) e conversão bruto <-> físico."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CAMINHO_PADRAO = Path(__file__).with_name("mapa_ecu.toml")


@dataclass(frozen=True)
class Sensor:
    nome: str
    tabela: int
    offset: int
    bytes: int
    conversao: str
    unidade: str
    minimo: float
    maximo: float
    status: str
    escala: float = 1.0
    soma: float = 0.0
    k: float = 0.0

    def bruto_max(self) -> int:
        return (1 << (8 * self.bytes)) - 1

    def para_fisico(self, bruto: int) -> float:
        if self.conversao == "inverso":
            return self.k / bruto if bruto else 0.0
        return bruto * self.escala + self.soma

    def para_bruto(self, fisico: float) -> int:
        if self.conversao == "inverso":
            bruto = round(self.k / fisico) if fisico > 0 else 0
        else:
            bruto = round((fisico - self.soma) / self.escala)
        return max(0, min(self.bruto_max(), bruto))


@dataclass
class Tabela:
    id: int
    tamanho: int
    status: str
    fixo: bytes | None = None


@dataclass
class Mapa:
    tabelas: dict[int, Tabela]
    sensores: dict[str, Sensor]
    tempo: dict[str, float] = field(default_factory=dict)

    def sensores_da_tabela(self, tabela: int) -> list[Sensor]:
        return [s for s in self.sensores.values() if s.tabela == tabela]

    def codificar(self, tabela: int, valores: dict[str, float]) -> bytes:
        t = self.tabelas[tabela]
        if t.fixo is not None:
            return t.fixo
        dados = bytearray(t.tamanho)
        for s in self.sensores_da_tabela(tabela):
            if s.nome in valores:
                dados[s.offset:s.offset + s.bytes] = s.para_bruto(valores[s.nome]).to_bytes(s.bytes, "big")
        return bytes(dados)

    def decodificar(self, tabela: int, dados: bytes) -> dict[str, float]:
        saida = {}
        for s in self.sensores_da_tabela(tabela):
            fim = s.offset + s.bytes
            if fim <= len(dados):
                saida[s.nome] = s.para_fisico(int.from_bytes(dados[s.offset:fim], "big"))
        return saida


def carregar(caminho: str | Path = CAMINHO_PADRAO) -> Mapa:
    with open(caminho, "rb") as f:
        bruto = tomllib.load(f)
    tabelas = {}
    for chave, t in bruto["tabelas"].items():
        tid = int(chave, 16)
        fixo = bytes.fromhex(t["fixo"]) if "fixo" in t else None
        tamanho = len(fixo) if fixo is not None else int(t["tamanho"])
        tabelas[tid] = Tabela(tid, tamanho, t["status"], fixo)
    sensores = {}
    for nome, s in bruto["sensores"].items():
        sensores[nome] = Sensor(
            nome=nome, tabela=s["tabela"], offset=s["offset"], bytes=s["bytes"],
            conversao=s["conversao"], unidade=s["unidade"], minimo=s["min"], maximo=s["max"],
            status=s["status"], escala=s.get("escala", 1.0), soma=s.get("soma", 0.0), k=s.get("k", 0.0),
        )
    mapa = Mapa(tabelas, sensores, {k: v for k, v in bruto.get("tempo", {}).items() if k != "status"})
    validar(mapa)
    return mapa


def validar(mapa: Mapa) -> None:
    ocupado: dict[tuple[int, int], str] = {}
    for s in mapa.sensores.values():
        if s.conversao not in ("linear", "inverso"):
            raise ValueError(f"{s.nome}: conversão desconhecida {s.conversao!r}")
        if s.conversao == "inverso" and s.k <= 0:
            raise ValueError(f"{s.nome}: conversão inversa sem k")
        if s.conversao == "linear" and s.escala == 0:
            raise ValueError(f"{s.nome}: escala zero")
        if s.bytes not in (1, 2):
            raise ValueError(f"{s.nome}: bytes deve ser 1 ou 2")
        t = mapa.tabelas.get(s.tabela)
        if t is None:
            raise ValueError(f"{s.nome}: tabela {s.tabela:02X} não declarada")
        if t.fixo is not None or s.offset < 0 or s.offset + s.bytes > t.tamanho:
            raise ValueError(f"{s.nome}: offset {s.offset} fora da tabela {s.tabela:02X}")
        for b in range(s.offset, s.offset + s.bytes):
            if (s.tabela, b) in ocupado:
                raise ValueError(f"{s.nome} e {ocupado[(s.tabela, b)]} disputam o byte {b} da tabela {s.tabela:02X}")
            ocupado[(s.tabela, b)] = s.nome
