"""Gerador de valores físicos plausíveis para um motor 1.5 aspirado (Civic EH).

Cada cenário é uma função determinística do tempo (sem aleatoriedade), para
que os testes possam conferir valores. As constantes de calibração (corte,
relação de marcha, avanço) são estimativas para gerar dado verossímil, não
medidas do carro.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

CORTE_RPM = 7200          # limitador (estimativa)
MARCHA_LENTA = 760
KMH_POR_RPM_2A = 0.0118   # 2ª marcha (estimativa)
KMH_POR_RPM_3A = 0.0128   # 3ª marcha (estimativa)
AMBIENTE = 25.0

Valores = dict[str, float]


def _ondula(t: float, amp: float, freq: float, fase: float = 0.0) -> float:
    return amp * math.sin(2 * math.pi * freq * t + fase)


def _sonda_malha_fechada(t: float) -> float:
    """Sonda lambda oscilando rico/pobre ~1 Hz (malha fechada)."""
    return 0.45 + 0.4 * math.tanh(4 * math.sin(2 * math.pi * 1.1 * t))


def partida_fria(t: float) -> Valores:
    v = {"ect": AMBIENTE, "iat": AMBIENTE, "tps": 0.0, "o2": 0.45, "vss": 0.0}
    if t < 1.2:  # motor de arranque
        v |= {"rpm": 220 + _ondula(t, 40, 4), "tensao": 10.2 + _ondula(t, 0.3, 4),
              "map": 95 - 5 * t, "avanco": 5.0}
    else:
        u = t - 1.2
        rpm = 220 + 1230 * (1 - math.exp(-u / 0.2)) + 700 * (u / 0.5) * math.exp(1 - u / 0.5)
        v |= {"rpm": rpm + _ondula(t, 12, 2.3), "tensao": 13.8 + 0.4 * (1 - math.exp(-u)),
              "map": 35 + 60 * math.exp(-u / 0.4), "avanco": 10.0, "ect": AMBIENTE + 0.15 * u,
              "o2": 0.45 + _ondula(t, 0.01, 0.5)}
    return v


def aquecimento(t: float) -> Valores:
    ect = 90 - 65 * math.exp(-t / 70)
    frio = (90 - ect) / 65  # 1 = frio, 0 = quente
    return {
        "rpm": MARCHA_LENTA + 650 * frio + _ondula(t, 12, 0.7),
        "ect": ect,
        "iat": AMBIENTE + 7 * (1 - frio),
        "map": 34 + 4 * frio + _ondula(t, 0.6, 0.9),
        "tps": 0.0,
        "o2": 0.45 if ect < 55 else _sonda_malha_fechada(t),
        "vss": 0.0,
        "avanco": 12 + 3 * (1 - frio),
        "tensao": 14.1,
    }


def marcha_lenta(t: float) -> Valores:
    return {
        "rpm": MARCHA_LENTA + _ondula(t, 15, 0.7) + _ondula(t, 8, 3.1),
        "ect": 90 + _ondula(t, 2, 1 / 40),  # ventoinha liga/desliga
        "iat": 35.0,
        "map": 32 + _ondula(t, 0.8, 0.7),
        "tps": 0.0,
        "o2": _sonda_malha_fechada(t),
        "vss": 0.0,
        "avanco": 15 + _ondula(t, 0.5, 0.7),
        "tensao": 14.1 + _ondula(t, 0.05, 0.2),
    }


def puxada(t: float) -> Valores:
    """Acelerador a fundo em 2ª, de 2500 rpm até bater no corte."""
    tps = min(100.0, 100 * t / 0.2)
    rpm = 2500 + 1300 * max(0.0, t - 0.1)
    if rpm >= CORTE_RPM - 200:  # corte de injeção: serrote entre 7000 e 7200
        fase = (t * 8) % 1
        rpm = CORTE_RPM - 200 + 200 * fase
    return {
        "rpm": rpm,
        "ect": 90 + 0.3 * t,
        "iat": 35.0,
        "map": 33 + 66 * min(1.0, t / 0.25),
        "tps": tps,
        "o2": 0.86 + _ondula(t, 0.02, 3),
        "vss": rpm * KMH_POR_RPM_2A,
        "avanco": 16 + 12 * (rpm - 2500) / (CORTE_RPM - 2500),
        "tensao": 14.0,
    }


def desaceleracao(t: float) -> Valores:
    """Pé fora em 3ª a 6500 rpm; aos 6 s embreagem pressionada até a lenta."""
    if t < 6:
        rpm = 6500 - (6500 - 1300) * (t / 6) ** 0.8
        vss = rpm * KMH_POR_RPM_3A
        o2 = 0.05 if rpm > 1500 else _sonda_malha_fechada(t)  # corte em desaceleração
        mapa, avanco = 18.0, 28.0
    else:
        u = t - 6
        rpm = MARCHA_LENTA + (1300 - MARCHA_LENTA) * math.exp(-u / 0.5)
        vss = 1300 * KMH_POR_RPM_3A * max(0.0, 1 - u / 6)
        o2 = _sonda_malha_fechada(t)
        mapa, avanco = 32 - 14 * math.exp(-u / 0.5), 15.0
    return {"rpm": rpm, "ect": 91.0, "iat": 35.0, "map": mapa, "tps": 0.0, "o2": o2,
            "vss": vss, "avanco": avanco, "tensao": 14.1}


@dataclass(frozen=True)
class Trecho:
    nome: str
    duracao: float
    funcao: Callable[[float], Valores]


TRECHOS = {
    "partida_fria": Trecho("partida_fria", 20, partida_fria),
    "aquecimento": Trecho("aquecimento", 240, aquecimento),
    "marcha_lenta": Trecho("marcha_lenta", 60, marcha_lenta),
    "puxada": Trecho("puxada", 5.5, puxada),
    "desaceleracao": Trecho("desaceleracao", 12, desaceleracao),
}

# ciclo: partida e aquecimento uma vez; depois lenta -> puxada -> desaceleração em laço
CICLO_INICIO = ["partida_fria", "aquecimento"]
CICLO_LACO = ["marcha_lenta", "puxada", "desaceleracao"]
CENARIOS = [*TRECHOS, "ciclo"]


class Cenario:
    def __init__(self, nome: str) -> None:
        if nome not in CENARIOS:
            raise ValueError(f"cenário desconhecido {nome!r}; opções: {', '.join(CENARIOS)}")
        self.nome = nome
        if nome == "ciclo":
            self.inicio = [TRECHOS[n] for n in CICLO_INICIO]
            self.laco = [TRECHOS[n] for n in CICLO_LACO]
        else:
            self.inicio, self.laco = [], [TRECHOS[nome]]

    def trecho(self, t: float) -> tuple[Trecho, float]:
        """Trecho ativo no instante t e o tempo relativo dentro dele."""
        for tr in self.inicio:
            if t < tr.duracao:
                return tr, t
            t -= tr.duracao
        t %= sum(tr.duracao for tr in self.laco)
        for tr in self.laco:
            if t < tr.duracao:
                return tr, t
            t -= tr.duracao
        return self.laco[-1], self.laco[-1].duracao

    def valores(self, t: float) -> Valores:
        tr, u = self.trecho(t)
        return tr.funcao(u)
