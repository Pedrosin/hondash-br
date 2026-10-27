"""ECU virtual: máquina de estados pura, com relógio injetado.

Recebe bytes que o testador pôs na linha K e devolve o que deve voltar
(eco + resposta) com o instante de entrega, sem dormir nem usar socket.
Transportes reais ficam em servidor.py.

Modos:
  kline -> linha K crua (firmware ESP32): o wake-up exige silêncio na linha
           de pelo menos pulso_alto_ms antes do FE 04 72 8C. O nível baixo de
           70 ms não é representável num fluxo de bytes; só se prova no carro.
  ponte -> o que o kline_probe.py vê pela USB do Nano: o byte '!' pede o
           pulso (não vai para a linha, não ecoa) e o pulso dura baixo+alto.
Nos dois modos todo byte que chega na linha volta como eco (linha de 1 fio).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import protocolo as p

DORMINDO = "dormindo"
AGUARDA_INIT = "aguarda_init"
ATIVA = "ativa"

TEMPO_PADRAO = {
    "latencia_resposta_ms": 15,
    "sono_s": 2.0,
    "pulso_baixo_ms": 70,
    "pulso_alto_ms": 120,
    "janela_wake_s": 1.0,
    "intervalo_quadro_ms": 10,
}


@dataclass
class Contadores:
    wakes: int = 0
    inits: int = 0
    respostas: int = 0
    ignorados: int = 0
    sonos: int = 0
    por_tabela: dict[int, int] = field(default_factory=dict)


class EcuVirtual:
    def __init__(self, fonte, tempo: dict | None = None, modo: str = "kline",
                 t0: float = 0.0, velocidade: float = 1.0) -> None:
        if modo not in ("kline", "ponte"):
            raise ValueError(f"modo inválido {modo!r}")
        self.fonte = fonte
        self.tempo = {**TEMPO_PADRAO, **(tempo or {})}
        self.modo = modo
        self.t0 = t0
        self.velocidade = velocidade
        self.estado = DORMINDO
        self.cont = Contadores()
        self._montador = p.Montador()
        self._linha_ocupada_ate = t0 - 10.0  # linha em repouso desde "sempre"
        self._silencio_antes_do_quadro = 0.0
        self._pulso_fim: float | None = None
        self._ultima_atividade = t0

    # -- entrada ---------------------------------------------------------
    def receber(self, dados: bytes, agora: float) -> list[tuple[float, bytes]]:
        self.atualizar(agora)
        saida: list[tuple[float, bytes]] = []
        eco = bytearray()
        for b in dados:
            if self.modo == "ponte" and b == p.CMD_PULSO_PONTE and not self._montador.pendente():
                dur = (self.tempo["pulso_baixo_ms"] + self.tempo["pulso_alto_ms"]) / 1000
                self._pulso_fim = agora + dur
                self._linha_ocupada_ate = max(self._linha_ocupada_ate, agora)
                continue
            silencio = agora - self._linha_ocupada_ate
            if silencio > self.tempo["intervalo_quadro_ms"] / 1000:
                self._montador.limpar()  # silêncio na linha fecha quadro incompleto
            self._linha_ocupada_ate = max(self._linha_ocupada_ate, agora)
            eco.append(b)
            for quadro, silencio_antes in self._montador.alimentar_com_meta(bytes([b]), silencio):
                self._silencio_antes_do_quadro = silencio_antes
                resp = self._tratar(quadro, agora)
                if resp:
                    entrega = agora + self.tempo["latencia_resposta_ms"] / 1000 + p.tempo_transmissao(len(resp))
                    self._linha_ocupada_ate = max(self._linha_ocupada_ate, entrega)
                    saida.append((entrega, resp))
        if eco:
            saida.insert(0, (agora, bytes(eco)))
        return saida

    def atualizar(self, agora: float) -> None:
        if self.estado != DORMINDO and agora - self._ultima_atividade > self.tempo["sono_s"]:
            self.estado = DORMINDO
            self.cont.sonos += 1

    # -- lógica ----------------------------------------------------------
    def _wake_permitido(self, agora: float) -> bool:
        if self.modo == "ponte":
            return (self._pulso_fim is not None and self._pulso_fim <= agora
                    and agora - self._pulso_fim <= self.tempo["janela_wake_s"])
        return self._silencio_antes_do_quadro >= self.tempo["pulso_alto_ms"] / 1000

    def _tratar(self, q: bytes, agora: float) -> bytes | None:
        if q == p.WAKE:
            if not self._wake_permitido(agora):
                self.cont.ignorados += 1
                return None
            self._pulso_fim = None
            self.estado = AGUARDA_INIT
            self._ultima_atividade = agora
            self.cont.wakes += 1
            return p.WAKE_OK
        if self.estado == DORMINDO:
            self.cont.ignorados += 1
            return None
        if q == p.INIT:
            self.estado = ATIVA
            self._ultima_atividade = agora
            self.cont.inits += 1
            return p.INIT_OK
        if (self.estado == ATIVA and len(q) == 5 and q[0] == p.TIPO_REQ
                and q[2] == p.CONSULTA_TABELA):
            self._ultima_atividade = agora
            dados = self.fonte.tabela(q[3], (agora - self.t0) * self.velocidade)
            if dados is None:
                self.cont.ignorados += 1
                return None
            self.cont.respostas += 1
            self.cont.por_tabela[q[3]] = self.cont.por_tabela.get(q[3], 0) + 1
            return p.resposta_tabela(q[3], dados)
        self.cont.ignorados += 1
        return None
