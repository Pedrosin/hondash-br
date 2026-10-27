"""python -m emulador [--modo ponte|kline] [--cenario X | --replay log.csv] [--porta N]"""
from __future__ import annotations

import argparse
import sys
import time

from . import criar_servidor
from .motor import CENARIOS


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m emulador", description="ECU Honda OBD1 virtual (K-line Keihin)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--porta", type=int, default=35000, help="0 = porta livre (impressa como PORTA=n)")
    ap.add_argument("--modo", choices=["kline", "ponte"], default="ponte",
                    help="ponte = como o kline_probe.py vê o Nano ('!' gera o pulso); kline = linha crua (firmware)")
    origem = ap.add_mutually_exclusive_group()
    origem.add_argument("--cenario", choices=CENARIOS, default="ciclo")
    origem.add_argument("--replay", help="CSV gravado pelo kline_probe.py")
    ap.add_argument("--mapa", help="mapa de offsets (padrão: emulador/mapa_ecu.toml)")
    ap.add_argument("--velocidade", type=float, default=1.0, help="multiplica o relógio do cenário")
    a = ap.parse_args(argv)

    extra = {"caminho_mapa": a.mapa} if a.mapa else {}
    srv = criar_servidor(a.cenario, a.replay, a.modo, a.host, a.porta, velocidade=a.velocidade, **extra)
    print(f"PORTA={srv.porta}", flush=True)
    origem_txt = f"replay {a.replay}" if a.replay else f"cenário {a.cenario}"
    print(f"ECU virtual ({a.modo}, {origem_txt}) em {srv.url}", file=sys.stderr, flush=True)
    srv.iniciar()
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        srv.parar()


if __name__ == "__main__":
    main()
