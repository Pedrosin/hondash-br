"""Ponte K-line -> WebSocket para o painel de teste.

Lê a ECU (emulador por socket://, ou a ponte USB do Nano no Mac), decodifica com o
mapa provisório e publica JSON em ws://host:porta/ws. Também serve o painel em http://host:porta/.

  python painel-teste/ponte.py socket://127.0.0.1:35000          (emulador em modo ponte, o padrão dele)
  python painel-teste/ponte.py /dev/cu.usbserial-XXXX             (Nano no carro)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import threading
import time
from http import HTTPStatus
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))

import serial  # noqa: E402
from websockets.asyncio.server import broadcast, serve  # noqa: E402

from emulador import mapa as mapa_ecu  # noqa: E402
from emulador.cliente import ClienteKLine  # noqa: E402

ARQUIVOS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/painel.mjs": ("painel.mjs", "text/javascript; charset=utf-8"),
}
FALHAS_PARA_RECONECTAR = 4


def mensagem_tabela(mapa: mapa_ecu.Mapa, tabela: int, quadro: bytes, dados: bytes, t: float) -> dict:
    valores = {}
    for nome, v in mapa.decodificar(tabela, dados).items():
        s = mapa.sensores[nome]
        valores[nome] = {"valor": round(v, 3), "unidade": s.unidade, "status": s.status,
                         "min": s.minimo, "max": s.maximo}
    return {"tipo": "tabela", "t": round(t, 3), "tabela": f"{tabela:02X}", "bruto": quadro.hex(), "valores": valores}


class LeitorKLine(threading.Thread):
    """Laço bloqueante (pyserial) numa thread; cada mensagem vai para publicar()."""

    def __init__(self, url: str, modo: str, tabelas: list[int], mapa: mapa_ecu.Mapa,
                 publicar, pausa: float = 0.02) -> None:
        super().__init__(daemon=True, name="leitor-kline")
        self.url, self.modo, self.tabelas, self.mapa = url, modo, tabelas, mapa
        self.publicar, self.pausa = publicar, pausa
        self.parar = threading.Event()

    def estado(self, estado: str, detalhe: str = "") -> None:
        self.publicar({"tipo": "estado", "estado": estado, "detalhe": detalhe})

    def run(self) -> None:
        t0 = time.monotonic()
        while not self.parar.is_set():
            try:
                baud = 115200 if self.modo == "ponte" else 10400  # USB do Nano x linha K direta
                ser = serial.serial_for_url(self.url, baud, timeout=0.4)
            except (serial.SerialException, OSError) as e:
                self.estado("erro", str(e))
                self.parar.wait(1.0)
                continue
            if "://" not in self.url:
                time.sleep(2)  # Nano reinicia ao abrir a porta
            try:
                self._sessao(ser, t0)
            except (serial.SerialException, OSError) as e:
                self.estado("erro", str(e))
                self.parar.wait(1.0)
            finally:
                ser.close()

    def _sessao(self, ser, t0: float) -> None:
        cli = ClienteKLine(ser, self.modo)
        while not self.parar.is_set():
            if not cli.acordar():
                self.estado("sem_resposta", "wake-up/init sem resposta")
                self.parar.wait(0.5)
                continue
            self.estado("ativo")
            falhas = 0
            while not self.parar.is_set() and falhas < FALHAS_PARA_RECONECTAR:
                for tab in self.tabelas:
                    quadro, dados = cli.ler_tabela(tab)
                    if dados is None:
                        falhas += 1
                        continue
                    falhas = 0
                    self.publicar(mensagem_tabela(self.mapa, tab, quadro, dados, time.monotonic() - t0))
                self.parar.wait(self.pausa)
            self.estado("reconectando")


class Ponte:
    def __init__(self, url: str, modo: str = "ponte", tabelas: list[int] | None = None,
                 caminho_mapa: str | Path = mapa_ecu.CAMINHO_PADRAO) -> None:
        self.mapa = mapa_ecu.carregar(caminho_mapa)
        self.url, self.modo = url, modo
        self.tabelas = tabelas or [0x11]
        self.conexoes: set = set()
        self.ultimo_estado = {"tipo": "estado", "estado": "iniciando", "detalhe": ""}
        self.porta = 0
        self._loop: asyncio.AbstractEventLoop | None = None
        self._leitor: LeitorKLine | None = None
        self._servidor = None

    def _publicar_da_thread(self, msg: dict) -> None:
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._enviar, msg)

    def _enviar(self, msg: dict) -> None:
        if msg["tipo"] == "estado":
            self.ultimo_estado = msg
        broadcast(self.conexoes, json.dumps(msg, ensure_ascii=False))

    async def _cliente(self, ws) -> None:
        self.conexoes.add(ws)
        try:
            await ws.send(json.dumps(self.ultimo_estado, ensure_ascii=False))
            await ws.wait_closed()
        finally:
            self.conexoes.discard(ws)

    @staticmethod
    def _http(conexao, req):
        if req.path in ARQUIVOS:
            nome, tipo = ARQUIVOS[req.path]
            resp = conexao.respond(HTTPStatus.OK, (AQUI / nome).read_text(encoding="utf-8"))
            del resp.headers["Content-Type"]
            resp.headers["Content-Type"] = tipo
            return resp
        if req.path != "/ws":
            return conexao.respond(HTTPStatus.NOT_FOUND, "não encontrado\n")
        return None  # segue o handshake do websocket

    async def iniciar(self, host: str = "127.0.0.1", porta: int = 8765) -> int:
        self._loop = asyncio.get_running_loop()
        self._servidor = await serve(self._cliente, host, porta, process_request=self._http)
        self.porta = self._servidor.sockets[0].getsockname()[1]
        self._leitor = LeitorKLine(self.url, self.modo, self.tabelas, self.mapa, self._publicar_da_thread)
        self._leitor.start()
        return self.porta

    async def parar(self) -> None:
        if self._leitor:
            self._leitor.parar.set()
            await asyncio.to_thread(self._leitor.join, 3)
        if self._servidor:
            self._servidor.close()
            await self._servidor.wait_closed()


async def _main(a) -> None:
    ponte = Ponte(a.url, a.modo, [int(t, 16) for t in a.tabelas.split(",")])
    porta = await ponte.iniciar(a.host, a.porta)
    print(f"painel em http://{a.host}:{porta}/  (lendo {a.url}, modo {a.modo})", flush=True)
    try:
        await asyncio.Future()
    finally:
        await ponte.parar()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Ponte K-line -> WebSocket do painel de teste")
    ap.add_argument("url", nargs="?", default="socket://127.0.0.1:35000",
                    help="socket://host:porta do emulador, ou porta serial da ponte USB")
    ap.add_argument("--modo", choices=["ponte", "kline"], default="ponte",
                    help="ponte = Nano/emulador com '!' para o pulso; kline = linha crua")
    ap.add_argument("--tabelas", default="11", help="tabelas em hexa separadas por vírgula (padrão 11)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--porta", type=int, default=8765)
    try:
        asyncio.run(_main(ap.parse_args(argv)))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
