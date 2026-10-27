#include "ble_formato.h"

#include <string.h>

namespace ble {

const char* const UUID_SERVICO = "6b1f0000-3c5e-4d8a-9b2e-7a41c0d9e5f1";
const char* const UUID_TABELA = "6b1f0001-3c5e-4d8a-9b2e-7a41c0d9e5f1";
const char* const UUID_ESTADO = "6b1f0002-3c5e-4d8a-9b2e-7a41c0d9e5f1";
const char* const UUID_CONFIG = "6b1f0003-3c5e-4d8a-9b2e-7a41c0d9e5f1";

namespace {
void le16(uint8_t* p, uint16_t v) {
  p[0] = (uint8_t)v;
  p[1] = (uint8_t)(v >> 8);
}
void le32(uint8_t* p, uint32_t v) {
  for (int i = 0; i < 4; i++) p[i] = (uint8_t)(v >> (8 * i));
}
uint16_t sat16(uint32_t v) { return v > 0xFFFF ? 0xFFFF : (uint16_t)v; }
}  // namespace

size_t codificarTabela(const uint8_t* quadro, size_t n, uint32_t ms, uint8_t* saida, size_t cap) {
  if (n > kline::TAMANHO_MAX || TAM_CAB_TABELA + n > cap) return 0;
  saida[0] = VERSAO;
  le32(saida + 1, ms);
  memcpy(saida + TAM_CAB_TABELA, quadro, n);
  return TAM_CAB_TABELA + n;
}

size_t codificarEstado(uint8_t estado, const kline::Contadores& c, uint8_t* saida, size_t cap) {
  if (cap < TAM_ESTADO) return 0;
  saida[0] = VERSAO;
  saida[1] = estado;
  le32(saida + 2, c.quadrosOk);
  le32(saida + 6, c.timeouts);
  le16(saida + 10, sat16(c.reconexoes));
  le16(saida + 12, sat16(c.ecoErrado));
  return TAM_ESTADO;
}

bool decodificarConfig(const uint8_t* d, size_t n, kline::Config& cfg) {
  if (n < 5 || d[0] != VERSAO) return false;
  uint8_t qtd = d[3];
  if (qtd == 0 || qtd > kline::MAX_TABELAS || n != 4u + qtd) return false;
  cfg.intervaloMs = (uint16_t)(d[1] | (d[2] << 8));
  cfg.nTabelas = qtd;
  memcpy(cfg.tabelas, d + 4, qtd);
  return true;
}

size_t codificarConfig(const kline::Config& cfg, uint8_t* saida, size_t cap) {
  size_t n = 4u + cfg.nTabelas;
  if (cap < n) return 0;
  saida[0] = VERSAO;
  le16(saida + 1, cfg.intervaloMs);
  saida[3] = cfg.nTabelas;
  memcpy(saida + 4, cfg.tabelas, cfg.nTabelas);
  return n;
}

}  // namespace ble
