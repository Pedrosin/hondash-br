"""Emulador em tempo real por TCP: kline_probe.py e o cliente Python conversando com ele."""
import csv
import time

import pytest
import serial

import kline_probe
from emulador import criar_servidor, mapa as m
from emulador import protocolo as p
from emulador.cliente import ClienteKLine


def ler_csv(caminho):
    with open(caminho, newline="") as f:
        return list(csv.DictReader(f))


def test_probe_contra_emulador_em_modo_ponte(tmp_path, capsys):
    saida = tmp_path / "log.csv"
    with criar_servidor("marcha_lenta", modo="ponte") as srv:
        rc = kline_probe.main([srv.url, "--duracao", "1.5", "--saida", str(saida)])
    assert rc == 0
    texto = capsys.readouterr().out
    assert "wake: 0e 04 72 7c" in texto and "init: 02 04 00 fa" in texto and "aviso" not in texto
    linhas = ler_csv(saida)
    assert {r["tabela"] for r in linhas} == {"11", "13", "17"}
    assert len(linhas) >= 9
    mp = m.carregar()
    for r in linhas:
        q = bytes.fromhex(r["bytes_hex"])
        tid, dados = p.dados_da_resposta(q)
        assert tid == int(r["tabela"], 16)
        if tid == 0x11:
            assert len(q) == 25
            assert 700 < mp.decodificar(0x11, dados)["rpm"] < 820


def test_log_do_probe_volta_identico_no_replay(tmp_path):
    log1, log2 = tmp_path / "a.csv", tmp_path / "b.csv"
    with criar_servidor("puxada", modo="ponte") as srv:
        assert kline_probe.main([srv.url, "--duracao", "1.0", "--saida", str(log1)]) == 0
    with criar_servidor(replay=log1, modo="ponte") as srv:
        assert kline_probe.main([srv.url, "--duracao", "0.8", "--saida", str(log2)]) == 0
    originais = {r["bytes_hex"] for r in ler_csv(log1) if r["tabela"] == "11"}
    repetidos = [r["bytes_hex"] for r in ler_csv(log2) if r["tabela"] == "11"]
    assert repetidos and set(repetidos) <= originais


def test_modo_kline_sem_pulso_da_ponte_e_ecu_dorme_apos_2s():
    with criar_servidor("marcha_lenta", modo="kline") as srv:
        ser = serial.serial_for_url(srv.url, timeout=0.4)
        try:
            cli = ClienteKLine(ser, modo="kline")
            assert cli.acordar()
            q, dados = cli.ler_tabela(0x11)
            assert dados is not None and len(q) == 25
            time.sleep(2.3)  # sem requisição: a ECU volta a dormir
            q, dados = cli.ler_tabela(0x11)
            assert q == b"" and dados is None
            assert srv.ecu.cont.sonos == 1
            assert cli.acordar()
            assert cli.ler_tabela(0x11)[1] is not None
            assert cli.erros_eco == 0
        finally:
            ser.close()


def test_conexao_nova_encontra_ecu_dormindo():
    with criar_servidor("marcha_lenta", modo="kline") as srv:
        for _ in range(2):
            ser = serial.serial_for_url(srv.url, timeout=0.3)
            cli = ClienteKLine(ser, modo="kline")
            assert cli.ler_tabela(0x11) == (b"", None)
            assert cli.acordar()
            ser.close()
            time.sleep(0.1)
        assert srv.conexoes == 2


@pytest.mark.parametrize("lixo", [b"\x00", b"!"])
def test_modo_kline_recusa_wake_logo_apos_ruido(lixo):
    with criar_servidor("marcha_lenta", modo="kline") as srv:
        ser = serial.serial_for_url(srv.url, timeout=0.3)
        try:
            ser.write(lixo)
            time.sleep(0.02)
            ser.write(p.WAKE)
            assert ser.read(len(lixo) + 4) == lixo + p.WAKE  # só eco
            assert ser.read(4) == b""
        finally:
            ser.close()
