"""De onde a ECU virtual tira o conteúdo das tabelas: cenário sintético ou replay de log."""
from __future__ import annotations

import csv
from bisect import bisect_right
from pathlib import Path

from . import protocolo
from .mapa import Mapa
from .motor import Cenario


class FonteCenario:
    def __init__(self, cenario: Cenario, mapa: Mapa) -> None:
        self.cenario = cenario
        self.mapa = mapa

    def tabela(self, tid: int, t: float) -> bytes | None:
        if tid not in self.mapa.tabelas:
            return None
        return self.mapa.codificar(tid, self.cenario.valores(t))


class FonteReplay:
    """Repete um log no formato do kline_probe.py (t_s, tabela, bytes_hex).

    bytes_hex é o quadro de resposta inteiro; linhas com quadro inválido ou vazio
    são ignoradas. No instante t devolve o último quadro gravado até t, em laço.
    """

    def __init__(self, caminho: str | Path) -> None:
        self.series: dict[int, tuple[list[float], list[bytes]]] = {}
        with open(caminho, newline="") as f:
            for linha in csv.DictReader(f):
                q = bytes.fromhex(linha["bytes_hex"])
                r = protocolo.dados_da_resposta(q)
                if r is None or r[0] != int(linha["tabela"], 16):
                    continue
                tempos, dados = self.series.setdefault(r[0], ([], []))
                tempos.append(float(linha["t_s"]))
                dados.append(r[1])
        if not self.series:
            raise ValueError(f"{caminho}: nenhum quadro de tabela válido")
        self.duracao = max(ts[-1] for ts, _ in self.series.values()) or 1.0

    def tabela(self, tid: int, t: float) -> bytes | None:
        serie = self.series.get(tid)
        if serie is None:
            return None
        tempos, dados = serie
        i = bisect_right(tempos, t % self.duracao) - 1
        return dados[max(i, 0)]
