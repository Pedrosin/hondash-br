import csv

import pytest

from emulador import mapa as m
from emulador import protocolo as p
from emulador.ecu import AGUARDA_INIT, ATIVA, DORMINDO, EcuVirtual
from emulador.fontes import FonteCenario, FonteReplay
from emulador.motor import Cenario


@pytest.fixture
def mapa():
    return m.carregar()


def ecu(mapa, modo="kline", cenario="marcha_lenta"):
    return EcuVirtual(FonteCenario(Cenario(cenario), mapa), mapa.tempo, modo, t0=100.0)


def respostas(saida):
    """Separa eco (entregue no mesmo instante) da resposta."""
    return [b for _, b in saida[1:]]


def handshake(e, t=100.0):
    assert respostas(e.receber(p.WAKE, t)) == [p.WAKE_OK]
    assert respostas(e.receber(p.INIT, t + 0.05)) == [p.INIT_OK]
    return t + 0.05


def test_handshake_completo_e_tabela_com_eco_e_latencia(mapa):
    e = ecu(mapa)
    t = handshake(e)
    assert e.estado == ATIVA
    saida = e.receber(p.requisicao(0x11), t + 0.1)
    assert saida[0] == (t + 0.1, p.requisicao(0x11))  # eco imediato
    entrega, q = saida[1]
    assert q[:4] == bytes.fromhex("02 19 71 11") and p.quadro_valido(q)
    esperado = 0.015 + p.tempo_transmissao(25)
    assert entrega - (t + 0.1) == pytest.approx(esperado)
    rpm = mapa.decodificar(0x11, q[4:-1])["rpm"]
    assert 700 < rpm < 820


def test_requisicao_byte_a_byte_tambem_funciona(mapa):
    e = ecu(mapa)
    t = handshake(e)
    resp = []
    for i, b in enumerate(p.requisicao(0x11)):
        resp += respostas(e.receber(bytes([b]), t + 0.1 + i * 0.001))
    assert len(resp) == 1 and p.quadro_valido(resp[0])


def test_dormindo_ignora_init_e_requisicao(mapa):
    e = ecu(mapa)
    e.receber(b"", 100.0)
    assert respostas(e.receber(p.INIT, 100.5)) == []
    assert respostas(e.receber(p.requisicao(0x11), 101.0)) == []
    assert e.estado == DORMINDO and e.cont.ignorados == 2


def test_tabela_antes_do_init_e_ignorada(mapa):
    e = ecu(mapa)
    e.receber(p.WAKE, 100.0)
    assert e.estado == AGUARDA_INIT
    assert respostas(e.receber(p.requisicao(0x11), 100.1)) == []


def test_checksum_errado_e_tabela_desconhecida_ficam_sem_resposta(mapa):
    e = ecu(mapa)
    t = handshake(e)
    ruim = bytearray(p.requisicao(0x11))
    ruim[-1] ^= 1
    assert respostas(e.receber(bytes(ruim), t + 0.1)) == []
    assert respostas(e.receber(p.requisicao(0x42), t + 0.2)) == []
    assert len(respostas(e.receber(p.requisicao(0x13), t + 0.3))) == 1


def test_dorme_apos_2s_sem_requisicao_e_precisa_de_novo_wake(mapa):
    e = ecu(mapa)
    t = handshake(e)
    e.receber(p.requisicao(0x11), t + 1.9)
    assert e.estado == ATIVA
    e.atualizar(t + 1.9 + 2.01)
    assert e.estado == DORMINDO and e.cont.sonos == 1
    assert respostas(e.receber(p.requisicao(0x11), t + 4.0)) == []
    handshake(e, t + 5.0)
    assert e.estado == ATIVA


def test_modo_kline_exige_silencio_antes_do_wake(mapa):
    e = ecu(mapa)
    e.receber(b"\x00", 100.0)  # ruído na linha
    assert respostas(e.receber(p.WAKE, 100.05)) == []  # só 50 ms de silêncio
    assert respostas(e.receber(p.WAKE, 100.3)) == [p.WAKE_OK]


def test_modo_ponte_exige_pulso_e_nao_ecoa_o_comando(mapa):
    e = ecu(mapa, modo="ponte")
    assert respostas(e.receber(p.WAKE, 100.0)) == []  # sem '!'
    assert e.receber(b"!", 100.5) == []  # comando da ponte não vai pra linha
    assert respostas(e.receber(p.WAKE, 100.6)) == []  # pulso (190 ms) ainda em curso
    e.receber(b"!", 101.0)
    assert respostas(e.receber(p.WAKE, 101.25)) == [p.WAKE_OK]
    e2 = ecu(mapa, modo="ponte")
    e2.receber(b"!", 100.0)
    assert respostas(e2.receber(p.WAKE, 101.5)) == []  # pulso velho demais


def test_replay_devolve_quadros_gravados(tmp_path, mapa):
    q1 = p.resposta_tabela(0x11, mapa.codificar(0x11, {"rpm": 800}))
    q2 = p.resposta_tabela(0x11, mapa.codificar(0x11, {"rpm": 3000}))
    arq = tmp_path / "log.csv"
    with open(arq, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "tabela", "bytes_hex"])
        w.writerow(["0.000", "11", q1.hex()])
        w.writerow(["0.500", "13", ""])  # tabela que não respondeu
        w.writerow(["1.000", "11", q2.hex()])
        w.writerow(["2.000", "11", q1.hex()])
    fonte = FonteReplay(arq)
    assert fonte.tabela(0x11, 0.4) == q1[4:-1]
    assert fonte.tabela(0x11, 1.2) == q2[4:-1]
    assert fonte.tabela(0x11, 2.5) == q1[4:-1]  # última amostra também sai
    assert fonte.tabela(0x11, 4.2) == q2[4:-1]  # laço de 3 s: 4.2 % 3.0 = 1.2
    assert fonte.tabela(0x13, 1.0) is None
    e = EcuVirtual(fonte, mapa.tempo, "kline", t0=100.0)
    t = handshake(e)
    assert respostas(e.receber(p.requisicao(0x11), 101.1))[0] == q2
    assert respostas(e.receber(p.requisicao(0x13), 101.2)) == []
