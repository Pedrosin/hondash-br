#include <string.h>
#include <unity.h>

#include "ble_formato.h"
#include "kline_quadro.h"

using namespace kline;

void setUp() {}
void tearDown() {}

static void test_checksum_exemplos_da_fonte_publica() {
  const uint8_t init[] = {0x72, 0x05, 0x00, 0xF0};
  TEST_ASSERT_EQUAL_HEX8(0x99, checksum(init, 4));
  uint8_t req[5];
  montarRequisicao(0x00, req);
  const uint8_t id[] = {0x72, 0x05, 0x71, 0x00, 0x18};
  TEST_ASSERT_EQUAL_HEX8_ARRAY(id, req, 5);
  montarRequisicao(0x11, req);
  TEST_ASSERT_EQUAL_HEX8(0x07, req[4]);
  montarRequisicao(0x13, req);
  TEST_ASSERT_EQUAL_HEX8(0x05, req[4]);
  TEST_ASSERT_TRUE(quadroValido(WAKE, 4));
  TEST_ASSERT_TRUE(quadroValido(WAKE_OK, 4));
  TEST_ASSERT_TRUE(quadroValido(INIT, 5));
  TEST_ASSERT_TRUE(quadroValido(INIT_OK, 4));
}

static size_t resposta(uint8_t tabela, uint8_t semente, uint8_t* q) {
  q[0] = TIPO_RESP;
  q[1] = 25;
  q[2] = CONSULTA_TABELA;
  q[3] = tabela;
  for (int i = 0; i < 20; i++) q[4 + i] = (uint8_t)(semente + i);
  q[24] = checksum(q, 24);
  return 25;
}

static void test_montador_ressincroniza() {
  uint8_t bom[25], ruim[25];
  resposta(0x11, 7, bom);
  memcpy(ruim, bom, 25);
  ruim[10] ^= 0xFF;
  Montador m;
  uint8_t fluxo[2 + 25 + 25];
  fluxo[0] = 0x00;
  fluxo[1] = 0xFF;
  memcpy(fluxo + 2, ruim, 25);
  memcpy(fluxo + 27, bom, 25);
  int quadros = 0;
  for (size_t i = 0; i < sizeof(fluxo); i++) {
    if (m.alimentar(fluxo[i])) {
      quadros++;
      TEST_ASSERT_EQUAL_HEX8_ARRAY(bom, m.quadro(), 25);
    }
  }
  TEST_ASSERT_EQUAL(1, quadros);
  TEST_ASSERT_TRUE(m.descartados() > 0);
  uint8_t t = 0;
  TEST_ASSERT_TRUE(respostaDeTabela(bom, 25, &t));
  TEST_ASSERT_EQUAL_HEX8(0x11, t);
  TEST_ASSERT_FALSE(respostaDeTabela(ruim, 25, &t));
}

static void test_ble_tabela_e_estado() {
  uint8_t q[25];
  resposta(0x11, 1, q);
  uint8_t buf[ble::TAM_MAX_TABELA];
  size_t n = ble::codificarTabela(q, 25, 0x01020304, buf, sizeof(buf));
  TEST_ASSERT_EQUAL(30, n);
  TEST_ASSERT_EQUAL_HEX8(ble::VERSAO, buf[0]);
  TEST_ASSERT_EQUAL_HEX8(0x04, buf[1]);  // ms little-endian
  TEST_ASSERT_EQUAL_HEX8(0x01, buf[4]);
  TEST_ASSERT_EQUAL_HEX8_ARRAY(q, buf + 5, 25);
  TEST_ASSERT_EQUAL(0, ble::codificarTabela(q, 25, 0, buf, 29));  // não cabe

  Contadores c = {100000, 7, 3, 70000, 0};
  uint8_t e[ble::TAM_ESTADO];
  TEST_ASSERT_EQUAL(14, ble::codificarEstado(ATIVO, c, e, sizeof(e)));
  TEST_ASSERT_EQUAL_HEX8(ATIVO, e[1]);
  TEST_ASSERT_EQUAL_HEX8(0xA0, e[2]);  // 100000 = 0x000186A0
  TEST_ASSERT_EQUAL_HEX8(0x86, e[3]);
  TEST_ASSERT_EQUAL_HEX8(0x07, e[6]);
  TEST_ASSERT_EQUAL_HEX8(0xFF, e[10]);  // reconexões saturam em 0xFFFF
  TEST_ASSERT_EQUAL_HEX8(0xFF, e[11]);
  TEST_ASSERT_EQUAL_HEX8(0x03, e[12]);
}

static void test_ble_config_valida_e_recusa() {
  Config cfg = Config::padrao();
  const uint8_t ok[] = {ble::VERSAO, 0x32, 0x00, 2, 0x11, 0x00};
  TEST_ASSERT_TRUE(ble::decodificarConfig(ok, sizeof(ok), cfg));
  TEST_ASSERT_EQUAL(50, cfg.intervaloMs);
  TEST_ASSERT_EQUAL(2, cfg.nTabelas);
  TEST_ASSERT_EQUAL_HEX8(0x00, cfg.tabelas[1]);
  uint8_t ida[ble::TAM_MAX_CONFIG];
  TEST_ASSERT_EQUAL(sizeof(ok), ble::codificarConfig(cfg, ida, sizeof(ida)));
  TEST_ASSERT_EQUAL_HEX8_ARRAY(ok, ida, sizeof(ok));

  Config antes = cfg;
  const uint8_t versao_errada[] = {9, 0x32, 0x00, 1, 0x11};
  const uint8_t zero_tabelas[] = {ble::VERSAO, 0x32, 0x00, 0};
  const uint8_t tamanho_errado[] = {ble::VERSAO, 0x32, 0x00, 3, 0x11, 0x13};
  const uint8_t demais[] = {ble::VERSAO, 0, 0, 9, 1, 2, 3, 4, 5, 6, 7, 8, 9};
  TEST_ASSERT_FALSE(ble::decodificarConfig(versao_errada, sizeof(versao_errada), cfg));
  TEST_ASSERT_FALSE(ble::decodificarConfig(zero_tabelas, sizeof(zero_tabelas), cfg));
  TEST_ASSERT_FALSE(ble::decodificarConfig(tamanho_errado, sizeof(tamanho_errado), cfg));
  TEST_ASSERT_FALSE(ble::decodificarConfig(demais, sizeof(demais), cfg));
  TEST_ASSERT_EQUAL_MEMORY(&antes, &cfg, sizeof(cfg));
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_checksum_exemplos_da_fonte_publica);
  RUN_TEST(test_montador_ressincroniza);
  RUN_TEST(test_ble_tabela_e_estado);
  RUN_TEST(test_ble_config_valida_e_recusa);
  return UNITY_END();
}
