import pytest

from emulador import mapa as m
from emulador import protocolo as p


def test_checksum_confere_exemplos_da_fonte_publica():
    assert p.checksum(bytes.fromhex("72 05 00 F0")) == 0x99
    assert p.requisicao(0x00) == bytes.fromhex("72 05 71 00 18")
    assert p.requisicao(0x11) == bytes.fromhex("72 05 71 11 07")
    assert p.requisicao(0x13) == bytes.fromhex("72 05 71 13 05")
    for q in (p.WAKE, p.WAKE_OK, p.INIT, p.INIT_OK):
        assert p.quadro_valido(q)


def test_resposta_tabela_11_tem_25_bytes_e_cabecalho_da_fonte():
    q = p.resposta_tabela(0x11, bytes(20))
    assert len(q) == 25 and q[:4] == bytes.fromhex("02 19 71 11") and p.quadro_valido(q)
    assert p.dados_da_resposta(q) == (0x11, bytes(20))


def test_montador_ressincroniza_depois_de_lixo_e_checksum_errado():
    bom = p.resposta_tabela(0x11, bytes(range(20)))
    ruim = bytearray(bom)
    ruim[10] ^= 0xFF
    mt = p.Montador()
    saida = mt.alimentar(b"\x00\xff" + bytes(ruim) + bom[:7])
    saida += mt.alimentar(bom[7:])
    assert saida[-1] == bom
    assert mt.descartados > 0


def test_mapa_padrao_carrega_e_tudo_e_hipotese():
    mp = m.carregar()
    assert {"rpm", "ect", "iat", "map", "tps", "o2", "vss", "avanco", "tensao"} <= set(mp.sensores)
    assert all(s.status == "HIPOTESE" for s in mp.sensores.values())
    assert all(t.status == "HIPOTESE" for t in mp.tabelas.values())
    assert mp.tabelas[0x11].tamanho == 20


@pytest.mark.parametrize("nome,valor,tol", [
    ("rpm", 760, 1), ("rpm", 7150, 25), ("ect", 88, 0.5), ("map", 32.4, 0.25),
    ("tps", 47, 0.2), ("o2", 0.83, 0.01), ("avanco", 15.5, 0.25), ("tensao", 14.1, 0.05),
])
def test_ida_e_volta_bruto_fisico(nome, valor, tol):
    mp = m.carregar()
    dados = mp.codificar(0x11, {nome: valor})
    assert len(dados) == 20
    assert mp.decodificar(0x11, dados)[nome] == pytest.approx(valor, abs=tol)


def test_mapa_recusa_sobreposicao(tmp_path):
    texto = m.CAMINHO_PADRAO.read_text(encoding="utf-8").replace(
        "[sensores.iat]\nstatus = \"HIPOTESE\"\ntabela = 0x11\noffset = 3",
        "[sensores.iat]\nstatus = \"HIPOTESE\"\ntabela = 0x11\noffset = 2")
    arq = tmp_path / "mapa.toml"
    arq.write_text(texto, encoding="utf-8")
    with pytest.raises(ValueError, match="disputam"):
        m.carregar(arq)


def test_mapa_recusa_offset_negativo(tmp_path):
    texto = m.CAMINHO_PADRAO.read_text(encoding="utf-8").replace(
        "[sensores.iat]\nstatus = \"HIPOTESE\"\ntabela = 0x11\noffset = 3",
        "[sensores.iat]\nstatus = \"HIPOTESE\"\ntabela = 0x11\noffset = -1")
    arq = tmp_path / "mapa.toml"
    arq.write_text(texto, encoding="utf-8")
    with pytest.raises(ValueError, match="fora da tabela"):
        m.carregar(arq)
