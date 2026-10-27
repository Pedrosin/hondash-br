#include "kline_enlace.h"

#include <string.h>

namespace kline {

Config Config::padrao() {
  Config c;
  memset(&c, 0, sizeof(c));
  c.tabelas[0] = 0x11;
  c.tabelas[1] = 0x13;
  c.tabelas[2] = 0x17;
  c.nTabelas = 3;
  c.intervaloMs = 10;
  c.timeoutRespostaMs = 300;
  c.falhasParaCalar = 3;
  c.falhasParaReconectar = 4;
  c.esperaReconexaoMs = 500;
  c.eco = true;
  return c;
}

Enlace::Enlace(Transporte& t, const Config& c)
    : t_(t), cfg_(c), estado_(OCIOSO), desde_(0), ecoN_(0), ecoI_(0), ultimoByteMs_(0),
      aguardando_(false), indice_(0), pedida_(0), falhasSeguidas_(0), cb_(0), cbCtx_(0) {
  memset(falhasTabela_, 0, sizeof(falhasTabela_));
  memset(&cont_, 0, sizeof(cont_));
}

void Enlace::configurar(const Config& c) {
  cfg_ = c;
  if (cfg_.nTabelas > MAX_TABELAS) cfg_.nTabelas = MAX_TABELAS;
  memset(falhasTabela_, 0, sizeof(falhasTabela_));
  indice_ = 0;
}

void Enlace::irPara(Estado e) {
  estado_ = e;
  desde_ = t_.agoraMs();
}

void Enlace::enviar(const uint8_t* d, size_t n) {
  if (cfg_.eco) {
    memcpy(eco_, d, n);
    ecoN_ = n;
    ecoI_ = 0;
  }
  t_.escrever(d, n);
}

void Enlace::passo() {
  uint32_t agora = t_.agoraMs();
  for (int b = t_.ler(); b >= 0; b = t_.ler()) receber((uint8_t)b, agora);
  agora = t_.agoraMs();
  uint32_t dt = agora - desde_;

  switch (estado_) {
    case OCIOSO:
      t_.linhaBaixa();
      irPara(PULSO_BAIXO);
      break;
    case PULSO_BAIXO:
      if (dt >= PULSO_BAIXO_MS) {
        t_.linhaLiberada();
        irPara(PULSO_ALTO);
      }
      break;
    case PULSO_ALTO:
      if (dt >= PULSO_ALTO_MS) {
        t_.uartPronta();
        montador_.limpar();
        enviar(WAKE, sizeof(WAKE));
        irPara(ESPERA_WAKE);
      }
      break;
    case ESPERA_WAKE:
    case ESPERA_INIT:
      if (dt >= cfg_.timeoutRespostaMs) {
        cont_.timeouts++;
        reconectar();
      }
      break;
    case ATIVO:
      if (aguardando_) {
        if (dt >= cfg_.timeoutRespostaMs) timeoutNaTabela(agora);
      } else if (dt >= cfg_.intervaloMs) {
        requisitarProxima(agora);
      }
      break;
    case ESPERA_RECONEXAO:
      if (dt >= cfg_.esperaReconexaoMs) irPara(OCIOSO);
      break;
  }
}

void Enlace::receber(uint8_t b, uint32_t agora) {
  if (ecoI_ < ecoN_) {
    if (b == eco_[ecoI_]) {
      ecoI_++;
      ultimoByteMs_ = agora;
      return;
    }
    cont_.ecoErrado++;
    ecoN_ = ecoI_ = 0;  // segue tratando o byte como dado da ECU
  }
  if (montador_.pendente() && agora - ultimoByteMs_ > INTERVALO_QUADRO_MS) montador_.limpar();
  ultimoByteMs_ = agora;
  if (montador_.alimentar(b)) tratarQuadro(montador_.quadro(), montador_.tamanho(), agora);
}

void Enlace::tratarQuadro(const uint8_t* q, size_t n, uint32_t agora) {
  if (estado_ == ESPERA_WAKE && iguais(q, n, WAKE_OK, sizeof(WAKE_OK))) {
    enviar(INIT, sizeof(INIT));
    irPara(ESPERA_INIT);
    return;
  }
  if (estado_ == ESPERA_INIT && iguais(q, n, INIT_OK, sizeof(INIT_OK))) {
    memset(falhasTabela_, 0, sizeof(falhasTabela_));
    falhasSeguidas_ = 0;
    aguardando_ = false;
    indice_ = 0;
    irPara(ATIVO);
    desde_ = agora - cfg_.intervaloMs;  // primeira requisição já no próximo passo
    return;
  }
  uint8_t tabela;
  if (estado_ == ATIVO && aguardando_ && respostaDeTabela(q, n, &tabela) && tabela == pedida_) {
    aguardando_ = false;
    falhasSeguidas_ = 0;
    falhasTabela_[indice_] = 0;
    avancar();
    cont_.quadrosOk++;
    desde_ = agora;
    if (cb_) cb_(cbCtx_, q, n, agora);
    return;
  }
  cont_.ignorados++;
}

void Enlace::requisitarProxima(uint32_t agora) {
  if (cfg_.nTabelas == 0) return;
  for (uint8_t i = 0; i < cfg_.nTabelas && tabelaCalada(indice_); i++) {
    avancar();
  }
  uint8_t req[TAMANHO_REQ];
  pedida_ = cfg_.tabelas[indice_];
  montarRequisicao(pedida_, req);
  enviar(req, sizeof(req));
  aguardando_ = true;
  desde_ = agora;
}

void Enlace::timeoutNaTabela(uint32_t agora) {
  cont_.timeouts++;
  aguardando_ = false;
  if (falhasTabela_[indice_] < 255) falhasTabela_[indice_]++;
  falhasSeguidas_++;
  avancar();
  desde_ = agora;
  if (falhasSeguidas_ >= cfg_.falhasParaReconectar || todasCaladas()) reconectar();
}

void Enlace::avancar() {
  indice_ = cfg_.nTabelas ? (uint8_t)((indice_ + 1) % cfg_.nTabelas) : 0;
}

bool Enlace::todasCaladas() const {
  for (uint8_t i = 0; i < cfg_.nTabelas; i++) {
    if (!tabelaCalada(i)) return false;
  }
  return true;
}

void Enlace::reconectar() {
  cont_.reconexoes++;
  aguardando_ = false;
  ecoN_ = ecoI_ = 0;
  montador_.limpar();
  irPara(ESPERA_RECONEXAO);
}

}  // namespace kline
