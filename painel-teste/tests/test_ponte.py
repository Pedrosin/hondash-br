"""Ponte do painel ponta a ponta: emulador TCP -> ponte -> websocket/http."""
import asyncio
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from websockets.asyncio.client import connect

PAINEL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PAINEL.parent))
sys.path.insert(0, str(PAINEL))

import ponte  # noqa: E402
from emulador import criar_servidor, mapa as m  # noqa: E402

SENSORES = {"rpm", "ect", "iat", "map", "tps", "o2", "vss", "avanco", "tensao"}


async def coletar(porta, quantas, prazo=5.0):
    msgs = []
    async with connect(f"ws://127.0.0.1:{porta}/ws") as ws:
        async with asyncio.timeout(prazo):
            while sum(1 for x in msgs if x["tipo"] == "tabela") < quantas:
                msgs.append(json.loads(await ws.recv()))
    return msgs


def get(porta, caminho):
    with urllib.request.urlopen(f"http://127.0.0.1:{porta}{caminho}", timeout=3) as r:
        return r.status, r.headers["Content-Type"], r.read().decode("utf-8")


def test_ponte_entrega_valores_decodificados_do_emulador():
    async def rodar():
        with criar_servidor("marcha_lenta", modo="ponte") as emu:
            p = ponte.Ponte(emu.url, "ponte", [0x11, 0x13])
            porta = await p.iniciar(porta=0)
            try:
                return await coletar(porta, 8)
            finally:
                await p.parar()

    msgs = asyncio.run(rodar())
    assert msgs[0]["tipo"] == "estado"
    assert {"tipo": "estado", "estado": "ativo", "detalhe": ""} in msgs
    tabelas = [x for x in msgs if x["tipo"] == "tabela"]
    assert {x["tabela"] for x in tabelas} == {"11", "13"}
    mapa = m.carregar()
    for x in tabelas:
        if x["tabela"] != "11":
            assert x["valores"] == {}  # mapa provisório não põe sensor na 0x13
            continue
        v = x["valores"]
        assert set(v) == SENSORES
        assert all(s["status"] == "HIPOTESE" for s in v.values())
        assert 700 < v["rpm"]["valor"] < 820 and v["rpm"]["unidade"] == "rpm"
        assert 85 < v["ect"]["valor"] < 95 and v["vss"]["valor"] == 0
        assert v["tensao"]["valor"] == pytest.approx(14.1, abs=0.15)
        bruto = bytes.fromhex(x["bruto"])
        esperado = mapa.decodificar(0x11, bruto[4:-1])
        assert v["map"]["valor"] == pytest.approx(esperado["map"], abs=1e-3)


def test_ponte_serve_painel_e_404():
    async def rodar():
        p = ponte.Ponte("socket://127.0.0.1:9", "ponte")  # sem ECU: não importa aqui
        porta = await p.iniciar(porta=0)
        try:
            html = await asyncio.to_thread(get, porta, "/")
            js = await asyncio.to_thread(get, porta, "/painel.mjs")
            with pytest.raises(urllib.error.HTTPError) as erro:
                await asyncio.to_thread(get, porta, "/../ponte.py")
            return html, js, erro.value.code
        finally:
            await p.parar()

    (st, tipo, corpo), (st2, tipo2, corpo2), cod = asyncio.run(rodar())
    assert st == 200 and tipo.startswith("text/html") and 'id="painel"' in corpo and "./painel.mjs" in corpo
    assert st2 == 200 and tipo2.startswith("text/javascript") and "export function renderizar" in corpo2
    assert cod == 404


def test_ponte_sem_ecu_avisa_erro_e_nao_cai():
    async def rodar():
        p = ponte.Ponte("socket://127.0.0.1:9", "ponte")  # porta fechada
        porta = await p.iniciar(porta=0)
        try:
            async with connect(f"ws://127.0.0.1:{porta}/ws") as ws:
                async with asyncio.timeout(5):
                    while True:
                        msg = json.loads(await ws.recv())
                        if msg["estado"] == "erro":
                            return msg
        finally:
            await p.parar()

    msg = asyncio.run(rodar())
    assert msg["tipo"] == "estado" and msg["detalhe"]


def test_ponte_reacorda_ecu_que_dormiu(monkeypatch):
    """Leitor parado > 2 s (ECU dorme): a ponte detecta e refaz wake-up + init."""
    monkeypatch.setattr(ponte, "FALHAS_PARA_RECONECTAR", 1)  # 1 tabela x 2,5 s por rodada: não esperar 4 rodadas

    async def rodar():
        with criar_servidor("marcha_lenta", modo="ponte") as emu:
            p = ponte.Ponte(emu.url, "ponte")
            porta = await p.iniciar(porta=0)
            p._leitor.pausa = 2.5  # entre rodadas a ECU passa de 2 s sem requisição
            try:
                msgs = await coletar(porta, 2, prazo=12)
                return msgs, emu.ecu.cont.sonos, emu.ecu.cont.wakes
            finally:
                await p.parar()

    msgs, sonos, wakes = asyncio.run(rodar())
    assert sonos >= 1 and wakes >= 2
    assert [x["estado"] for x in msgs if x["tipo"] == "estado"].count("ativo") >= 2
