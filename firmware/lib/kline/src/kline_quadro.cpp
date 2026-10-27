#include "kline_quadro.h"

#include <string.h>

namespace kline {

uint8_t checksum(const uint8_t* d, size_t n) {
  uint32_t soma = 0;
  for (size_t i = 0; i < n; i++) soma += d[i];
  return (uint8_t)((0x100 - (soma & 0xFF)) & 0xFF);
}

bool quadroValido(const uint8_t* q, size_t n) {
  if (n < 3 || q[1] != n) return false;
  uint32_t soma = 0;
  for (size_t i = 0; i < n; i++) soma += q[i];
  return (soma & 0xFF) == 0;
}

bool iguais(const uint8_t* a, size_t na, const uint8_t* b, size_t nb) {
  return na == nb && memcmp(a, b, na) == 0;
}

size_t montarRequisicao(uint8_t tabela, uint8_t* saida) {
  saida[0] = TIPO_REQ;
  saida[1] = (uint8_t)TAMANHO_REQ;
  saida[2] = CONSULTA_TABELA;
  saida[3] = tabela;
  saida[4] = checksum(saida, 4);
  return TAMANHO_REQ;
}

bool respostaDeTabela(const uint8_t* q, size_t n, uint8_t* tabela) {
  if (n < 5 || !quadroValido(q, n) || q[0] != TIPO_RESP || q[2] != CONSULTA_TABELA) return false;
  if (tabela) *tabela = q[3];
  return true;
}

Montador::Montador() : n_(0), qn_(0), desc_(0) {}

bool Montador::alimentar(uint8_t b) {
  if (n_ == TAMANHO_MAX) descartar();  // não acontece com tamanho <= máximo, mas protege o buffer
  buf_[n_++] = b;
  return extrair();
}

bool Montador::extrair() {
  while (n_ >= 2) {
    size_t t = buf_[1];
    if ((buf_[0] != TIPO_RESP && buf_[0] != WAKE_OK[0]) || t < 3 || t > TAMANHO_MAX) {
      descartar();
      continue;
    }
    if (n_ < t) return false;
    if (!quadroValido(buf_, t)) {
      descartar();
      continue;
    }
    memcpy(q_, buf_, t);
    qn_ = t;
    memmove(buf_, buf_ + t, n_ - t);
    n_ -= t;
    return true;
  }
  return false;
}

void Montador::descartar() {
  memmove(buf_, buf_ + 1, n_ - 1);
  n_--;
  desc_++;
}

}  // namespace kline
