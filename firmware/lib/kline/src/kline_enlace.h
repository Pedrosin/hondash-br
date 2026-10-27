// Enlace com a ECU: wake-up, init e polling de tabelas, sem bloquear.
// Chamar passo() a cada volta do loop. Todo acesso a hardware passa por Transporte,
// então a mesma máquina de estados roda no ESP32 e no host (testes nativos).
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "kline_quadro.h"

namespace kline {

class Transporte {
 public:
  virtual ~Transporte() {}
  virtual void escrever(const uint8_t* d, size_t n) = 0;
  virtual int ler() = 0;               // próximo byte recebido ou -1
  virtual void linhaBaixa() = 0;       // início do pulso de wake-up: K em nível baixo
  virtual void linhaLiberada() = 0;    // fim do nível baixo: K volta ao repouso (alto)
  virtual void uartPronta() = 0;       // fim do pulso: volta a falar UART a 10400
  virtual uint32_t agoraMs() = 0;
};

// Tempos do wake-up vêm da fonte pública; os demais são escolha nossa (HIPÓTESE até medir no carro).
const uint32_t PULSO_BAIXO_MS = 70;
const uint32_t PULSO_ALTO_MS = 120;
const uint32_t INTERVALO_QUADRO_MS = 10;  // silêncio maior que isso descarta quadro incompleto
const size_t MAX_TABELAS = 8;

struct Config {
  uint8_t tabelas[MAX_TABELAS];
  uint8_t nTabelas;
  uint16_t intervaloMs;          // pausa entre uma resposta e a próxima requisição
  uint16_t timeoutRespostaMs;
  uint8_t falhasParaCalar;       // tabela que não responde N vezes seguidas sai da rodada
  uint8_t falhasParaReconectar;  // N timeouts seguidos (qualquer tabela) = ECU perdida
  uint16_t esperaReconexaoMs;
  bool eco;                      // linha de 1 fio: o que sai volta na recepção

  static Config padrao();
};

enum Estado : uint8_t {
  OCIOSO = 0,
  PULSO_BAIXO = 1,
  PULSO_ALTO = 2,
  ESPERA_WAKE = 3,
  ESPERA_INIT = 4,
  ATIVO = 5,
  ESPERA_RECONEXAO = 6,
};

struct Contadores {
  uint32_t quadrosOk;
  uint32_t timeouts;
  uint32_t ecoErrado;
  uint32_t reconexoes;
  uint32_t ignorados;
};

typedef void (*AoQuadro)(void* ctx, const uint8_t* quadro, size_t n, uint32_t ms);

class Enlace {
 public:
  Enlace(Transporte& t, const Config& c);
  void configurar(const Config& c);  // vale a partir da próxima requisição
  const Config& config() const { return cfg_; }
  void aoQuadro(AoQuadro f, void* ctx) {
    cb_ = f;
    cbCtx_ = ctx;
  }
  void passo();
  Estado estado() const { return estado_; }
  const Contadores& contadores() const { return cont_; }
  bool tabelaCalada(uint8_t indice) const { return falhasTabela_[indice] >= cfg_.falhasParaCalar; }

 private:
  void irPara(Estado e);
  void enviar(const uint8_t* d, size_t n);
  void receber(uint8_t b, uint32_t agora);
  void tratarQuadro(const uint8_t* q, size_t n, uint32_t agora);
  void requisitarProxima(uint32_t agora);
  void timeoutNaTabela(uint32_t agora);
  void reconectar();
  void avancar();
  bool todasCaladas() const;

  Transporte& t_;
  Config cfg_;
  Estado estado_;
  uint32_t desde_;
  Montador montador_;
  uint8_t eco_[TAMANHO_MAX];
  size_t ecoN_, ecoI_;
  uint32_t ultimoByteMs_;
  bool aguardando_;
  uint8_t indice_;
  uint8_t pedida_;
  uint8_t falhasTabela_[MAX_TABELAS];
  uint8_t falhasSeguidas_;
  Contadores cont_;
  AoQuadro cb_;
  void* cbCtx_;
};

}  // namespace kline
