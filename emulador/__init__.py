"""ECU Honda OBD1 virtual (K-line Keihin) para desenvolver sem o carro."""
from __future__ import annotations

from pathlib import Path

from . import mapa as _mapa
from .ecu import EcuVirtual
from .fontes import FonteCenario, FonteReplay
from .motor import Cenario
from .servidor import ServidorEcu


def criar_servidor(cenario: str = "marcha_lenta", replay: str | Path | None = None,
                   modo: str = "kline", host: str = "127.0.0.1", porta: int = 0,
                   caminho_mapa: str | Path = _mapa.CAMINHO_PADRAO, velocidade: float = 1.0,
                   tempo: dict | None = None) -> ServidorEcu:
    m = _mapa.carregar(caminho_mapa)
    fonte = FonteReplay(replay) if replay else FonteCenario(Cenario(cenario), m)
    t = {**m.tempo, **(tempo or {})}
    return ServidorEcu(lambda t0: EcuVirtual(fonte, t, modo, t0, velocidade), host, porta)
