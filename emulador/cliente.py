"""Testador K-line em Python sobre qualquer objeto estilo pyserial (usado pela ponte do painel)."""
from __future__ import annotations

import time

from . import protocolo as p


def ler_quadro(ser) -> bytes:
    """Lê um quadro pelo byte de tamanho; devolve o que chegou (pode vir incompleto no timeout)."""
    cab = ser.read(2)
    if len(cab) < 2 or not 3 <= cab[1] <= p.TAMANHO_MAX:
        return bytes(cab)
    return bytes(cab) + bytes(ser.read(cab[1] - 2))


class ClienteKLine:
    def __init__(self, ser, modo: str = "ponte") -> None:
        self.ser = ser
        self.modo = modo
        self.erros_eco = 0

    def trocar(self, tx: bytes) -> bytes:
        self.ser.reset_input_buffer()
        self.ser.write(tx)
        self.ser.flush()
        if self.ser.read(len(tx)) != tx:
            self.erros_eco += 1
        return ler_quadro(self.ser)

    def acordar(self) -> bool:
        if self.modo == "ponte":
            self.ser.write(bytes([p.CMD_PULSO_PONTE]))
            time.sleep(0.25)
        else:
            time.sleep(0.2)  # silêncio >= 120 ms antes do FE
        if self.trocar(p.WAKE) != p.WAKE_OK:
            return False
        return self.trocar(p.INIT) == p.INIT_OK

    def ler_tabela(self, tabela: int) -> tuple[bytes, bytes | None]:
        """(quadro cru, dados) — dados None se a resposta não for válida para essa tabela."""
        q = self.trocar(p.requisicao(tabela))
        r = p.dados_da_resposta(q)
        if r is None or r[0] != tabela:
            return q, None
        return q, r[1]
