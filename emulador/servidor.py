"""Transporte TCP em tempo real: o cliente abre socket://host:porta (pyserial) ou um socket cru.

Uma conexão por vez (a linha K é uma só). Cada conexão nova encontra a ECU
dormindo, como se o adaptador tivesse acabado de ser plugado.
"""
from __future__ import annotations

import heapq
import select
import socket
import threading
import time
from typing import Callable

from .ecu import EcuVirtual


class ServidorEcu:
    def __init__(self, fabrica_ecu: Callable[[float], EcuVirtual],
                 host: str = "127.0.0.1", porta: int = 0) -> None:
        self.fabrica_ecu = fabrica_ecu
        self._sock = socket.create_server((host, porta))
        self.host, self.porta = self._sock.getsockname()[:2]
        self._parar = threading.Event()
        self._thread: threading.Thread | None = None
        self.ecu: EcuVirtual | None = None
        self.conexoes = 0

    @property
    def url(self) -> str:
        return f"socket://{self.host}:{self.porta}"

    def iniciar(self) -> "ServidorEcu":
        self._thread = threading.Thread(target=self.servir, daemon=True, name="ecu-virtual")
        self._thread.start()
        return self

    def parar(self) -> None:
        self._parar.set()
        try:
            self._sock.close()
        except OSError:
            pass
        if self._thread:
            self._thread.join(timeout=2)

    def __enter__(self) -> "ServidorEcu":
        return self.iniciar()

    def __exit__(self, *exc) -> None:
        self.parar()

    def servir(self) -> None:
        while not self._parar.is_set():
            try:
                r, _, _ = select.select([self._sock], [], [], 0.1)
                if not r:
                    continue
                conn, _ = self._sock.accept()
            except OSError:
                return
            self.conexoes += 1
            with conn:
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self._atender(conn)

    def _atender(self, conn: socket.socket) -> None:
        self.ecu = ecu = self.fabrica_ecu(time.monotonic())
        fila: list[tuple[float, int, bytes]] = []
        seq = 0
        while not self._parar.is_set():
            agora = time.monotonic()
            espera = 0.05 if not fila else max(0.0, min(0.05, fila[0][0] - agora))
            try:
                r, _, _ = select.select([conn], [], [], espera)
            except OSError:
                return
            agora = time.monotonic()
            if r:
                try:
                    dados = conn.recv(4096)
                except OSError:
                    return
                if not dados:
                    return
                for entrega, b in ecu.receber(dados, agora):
                    heapq.heappush(fila, (entrega, seq, b))
                    seq += 1
            ecu.atualizar(agora)
            while fila and fila[0][0] <= time.monotonic():
                _, _, b = heapq.heappop(fila)
                try:
                    conn.sendall(b)
                except OSError:
                    return
