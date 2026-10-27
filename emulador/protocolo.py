"""Quadros do protocolo K-line Keihin (fonte pública, NÃO validado no carro).

Todo quadro tem a forma [tipo, tamanho, ..., checksum]: o byte 1 é o tamanho
total (incluindo o checksum) e a soma de todos os bytes fecha em 0 (mod 256).
Conferido nos quatro quadros fixos abaixo.
"""
from __future__ import annotations

BAUD = 10400
BITS_POR_BYTE = 10  # 8N1

WAKE = bytes.fromhex("FE 04 72 8C")
WAKE_OK = bytes.fromhex("0E 04 72 7C")
INIT = bytes.fromhex("72 05 00 F0 99")
INIT_OK = bytes.fromhex("02 04 00 FA")

TIPO_REQ = 0x72
TIPO_RESP = 0x02
CONSULTA_TABELA = 0x71
TAMANHO_MAX = 64
CMD_PULSO_PONTE = 0x21  # '!' pede o pulso de wake-up ao firmware de ponte do Nano


def checksum(corpo: bytes) -> int:
    return (0x100 - (sum(corpo) & 0xFF)) & 0xFF


def fechar(corpo: bytes) -> bytes:
    """Acrescenta o checksum."""
    return bytes(corpo) + bytes([checksum(corpo)])


def quadro_valido(q: bytes) -> bool:
    return len(q) >= 3 and q[1] == len(q) and sum(q) & 0xFF == 0


def requisicao(tabela: int) -> bytes:
    return fechar(bytes([TIPO_REQ, 0x05, CONSULTA_TABELA, tabela]))


def resposta_tabela(tabela: int, dados: bytes) -> bytes:
    n = 4 + len(dados) + 1
    if n > TAMANHO_MAX:
        raise ValueError(f"tabela {tabela:02X}: {len(dados)} bytes não cabem num quadro")
    return fechar(bytes([TIPO_RESP, n, CONSULTA_TABELA, tabela]) + bytes(dados))


def dados_da_resposta(q: bytes) -> tuple[int, bytes] | None:
    """(tabela, dados) de uma resposta de tabela válida; None se não for uma."""
    if not quadro_valido(q) or len(q) < 5 or q[0] != TIPO_RESP or q[2] != CONSULTA_TABELA:
        return None
    return q[3], q[4:-1]


def tempo_transmissao(n_bytes: int, baud: int = BAUD) -> float:
    return n_bytes * BITS_POR_BYTE / baud


class Montador:
    """Remonta quadros a partir de bytes soltos, usando o byte de tamanho.

    Byte que não pode iniciar um quadro (tipo fora de `tipos`, tamanho < 3 ou
    > máximo, ou checksum que não fecha) é descartado e a busca recomeça no
    byte seguinte. Filtrar o tipo corta a maior parte dos falsos quadros que
    lixo + checksum de 8 bits deixariam passar.
    """

    def __init__(self, tipos: frozenset[int] | None = None) -> None:
        self.tipos = tipos
        self.buf = bytearray()
        self.meta: list = []  # um valor por byte do buffer (ex.: silêncio antes do byte)
        self.descartados = 0

    def alimentar(self, dados: bytes) -> list[bytes]:
        return [q for q, _ in self.alimentar_com_meta(dados)]

    def alimentar_com_meta(self, dados: bytes, meta=None) -> list[tuple[bytes, object]]:
        """Como alimentar(), mas devolve cada quadro com o meta do seu primeiro byte."""
        self.buf.extend(dados)
        self.meta.extend([meta] * len(dados))
        saida = []
        while len(self.buf) >= 2:
            n = self.buf[1]
            if (self.tipos and self.buf[0] not in self.tipos) or n < 3 or n > TAMANHO_MAX:
                self._descartar()
                continue
            if len(self.buf) < n:
                break
            q = bytes(self.buf[:n])
            if sum(q) & 0xFF:
                self._descartar()
                continue
            saida.append((q, self.meta[0]))
            del self.buf[:n]
            del self.meta[:n]
        return saida

    def pendente(self) -> bool:
        return bool(self.buf)

    def limpar(self) -> None:
        self.buf.clear()
        self.meta.clear()

    def _descartar(self) -> None:
        del self.buf[0]
        del self.meta[0]
        self.descartados += 1
