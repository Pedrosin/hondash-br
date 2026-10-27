import pytest

from emulador.motor import CENARIOS, CORTE_RPM, MARCHA_LENTA, Cenario

FAIXAS = {"rpm": (0, 9000), "ect": (-40, 140), "iat": (-40, 100), "map": (0, 110), "tps": (0, 100),
          "o2": (0, 1.1), "vss": (0, 220), "avanco": (-10, 50), "tensao": (8, 16)}


def amostras(nome, passo=0.05, ate=None):
    c = Cenario(nome)
    fim = ate or (400 if nome == "ciclo" else sum(t.duracao for t in c.inicio + c.laco))
    return [c.valores(i * passo) for i in range(int(fim / passo))]


@pytest.mark.parametrize("nome", CENARIOS)
def test_todos_os_valores_ficam_em_faixa_fisica(nome):
    for v in amostras(nome):
        assert set(v) == set(FAIXAS)
        for k, (lo, hi) in FAIXAS.items():
            assert lo <= v[k] <= hi, (nome, k, v[k])


def test_partida_fria_arranca_baixo_e_sobe_para_lenta_acelerada():
    c = Cenario("partida_fria")
    assert 150 < c.valores(0.5)["rpm"] < 300 and c.valores(0.5)["tensao"] < 11
    assert 1300 < c.valores(10)["rpm"] < 1600
    assert c.valores(10)["ect"] < 30


def test_aquecimento_ect_sobe_e_lenta_cai():
    c = Cenario("aquecimento")
    assert c.valores(0)["ect"] < 30 and c.valores(239)["ect"] > 85
    assert c.valores(0)["rpm"] > 1300 and c.valores(239)["rpm"] < 850


def test_marcha_lenta_estavel_e_sonda_oscila():
    vs = amostras("marcha_lenta")
    rpms = [v["rpm"] for v in vs]
    assert MARCHA_LENTA - 30 < min(rpms) and max(rpms) < MARCHA_LENTA + 30
    o2 = [v["o2"] for v in vs]
    assert min(o2) < 0.2 and max(o2) > 0.7


def test_puxada_bate_no_corte_e_nao_passa():
    vs = amostras("puxada", passo=0.01)
    rpms = [v["rpm"] for v in vs]
    assert max(rpms) <= CORTE_RPM and max(rpms) > CORTE_RPM - 50
    assert vs[-1]["tps"] == 100 and vs[-1]["map"] > 95


def test_desaceleracao_corta_combustivel_e_volta_a_lenta():
    c = Cenario("desaceleracao")
    assert c.valores(2)["o2"] < 0.1 and c.valores(2)["map"] < 20
    assert abs(c.valores(11.9)["rpm"] - MARCHA_LENTA) < 20


def test_ciclo_passa_pelos_trechos_na_ordem():
    c = Cenario("ciclo")
    assert c.trecho(5)[0].nome == "partida_fria"
    assert c.trecho(100)[0].nome == "aquecimento"
    assert c.trecho(261)[0].nome == "marcha_lenta"
    assert c.trecho(321)[0].nome == "puxada"
    assert c.trecho(327)[0].nome == "desaceleracao"
    assert c.trecho(338)[0].nome == "marcha_lenta"  # laço recomeça


def test_cenario_desconhecido():
    with pytest.raises(ValueError):
        Cenario("drift")
