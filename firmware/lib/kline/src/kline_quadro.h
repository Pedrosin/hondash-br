// Quadros do protocolo K-line Keihin (fonte pública, NÃO validado no carro).
// Todo quadro: [tipo, tamanho total, ..., checksum]; a soma de todos os bytes fecha em 0 (mod 256).
// Sem dependência de Arduino: compila no ESP32 e no host (pio test -e native).
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace kline {

const uint32_t BAUD = 10400;
const size_t TAMANHO_MAX = 64;
const size_t TAMANHO_REQ = 5;

const uint8_t WAKE[4] = {0xFE, 0x04, 0x72, 0x8C};
const uint8_t WAKE_OK[4] = {0x0E, 0x04, 0x72, 0x7C};
const uint8_t INIT[5] = {0x72, 0x05, 0x00, 0xF0, 0x99};
const uint8_t INIT_OK[4] = {0x02, 0x04, 0x00, 0xFA};

const uint8_t TIPO_REQ = 0x72;
const uint8_t TIPO_RESP = 0x02;
const uint8_t CONSULTA_TABELA = 0x71;

uint8_t checksum(const uint8_t* d, size_t n);
bool quadroValido(const uint8_t* q, size_t n);
bool iguais(const uint8_t* a, size_t na, const uint8_t* b, size_t nb);

// Escreve "72 05 71 TT CS" em saida (5 bytes) e devolve 5.
size_t montarRequisicao(uint8_t tabela, uint8_t* saida);

// Resposta de tabela válida ("02 LL 71 TT ... CS")? Se sim, devolve o nº da tabela em *tabela.
bool respostaDeTabela(const uint8_t* q, size_t n, uint8_t* tabela);

// Remonta respostas da ECU a partir de bytes soltos usando o byte de tamanho.
// Byte que não pode iniciar quadro (tipo diferente de 0x02/0x0E, tamanho < 3 ou > máximo,
// checksum que não fecha) é descartado e a busca recomeça no seguinte. Filtrar o tipo corta
// a maior parte dos falsos quadros que lixo + checksum de 8 bits deixariam passar.
class Montador {
 public:
  Montador();
  // Devolve true quando um quadro completo e válido fica disponível em quadro()/tamanho().
  bool alimentar(uint8_t b);
  const uint8_t* quadro() const { return q_; }
  size_t tamanho() const { return qn_; }
  bool pendente() const { return n_ > 0; }
  void limpar() { n_ = 0; }
  uint32_t descartados() const { return desc_; }

 private:
  bool extrair();
  void descartar();
  uint8_t buf_[TAMANHO_MAX];
  size_t n_;
  uint8_t q_[TAMANHO_MAX];
  size_t qn_;
  uint32_t desc_;
};

}  // namespace kline
