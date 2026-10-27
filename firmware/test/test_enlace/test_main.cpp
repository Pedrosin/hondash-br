// Máquina de estados do enlace contra uma ECU falsa determinística (relógio simulado).
#include <unity.h>

#include <deque>
#include <set>
#include <vector>

#include "kline_enlace.h"

using namespace kline;

struct EcuFalsa : public Transporte {
  uint32_t ms = 0;
  std::deque<uint8_t> rx;
  std::vector<uint8_t> tx;
  int pulsos = 0;
  bool baixa = false;
  bool acordada = false;
  bool muda = false;          // não responde nada
  bool ecoNaLinha = true;
  int trocaTabela = -1;       // responde essa tabela no lugar da pedida
  std::set<uint8_t> semResposta;

  uint32_t msBaixa = 0, msLiberada = 0, msPrimeiraEscrita = 0;
  void escrever(const uint8_t* d, size_t n) override {
    if (tx.empty()) msPrimeiraEscrita = ms;
    tx.insert(tx.end(), d, d + n);
    if (ecoNaLinha) rx.insert(rx.end(), d, d + n);
    if (muda) return;
    if (iguais(d, n, WAKE, sizeof(WAKE))) {
      acordada = true;
      rx.insert(rx.end(), WAKE_OK, WAKE_OK + sizeof(WAKE_OK));
    } else if (acordada && iguais(d, n, INIT, sizeof(INIT))) {
      rx.insert(rx.end(), INIT_OK, INIT_OK + sizeof(INIT_OK));
    } else if (acordada && n == 5 && quadroValido(d, n) && d[0] == TIPO_REQ && d[2] == CONSULTA_TABELA &&
               !semResposta.count(d[3])) {
      responder(trocaTabela >= 0 ? (uint8_t)trocaTabela : d[3]);
    }
  }
  void responder(uint8_t tabela) {
    uint8_t q[25] = {TIPO_RESP, 25, CONSULTA_TABELA, tabela};
    for (int i = 4; i < 24; i++) q[i] = (uint8_t)i;
    q[24] = checksum(q, 24);
    rx.insert(rx.end(), q, q + 25);
  }
  int ler() override {
    if (rx.empty()) return -1;
    int b = rx.front();
    rx.pop_front();
    return b;
  }
  void linhaBaixa() override {
    pulsos++;
    baixa = true;
    msBaixa = ms;
  }
  void linhaLiberada() override {
    baixa = false;
    msLiberada = ms;
  }
  void uartPronta() override {}
  uint32_t agoraMs() override { return ms; }
};

static std::vector<uint8_t> recebidas;
static void anotar(void*, const uint8_t* q, size_t, uint32_t) { recebidas.push_back(q[3]); }

static void rodar(Enlace& e, EcuFalsa& f, uint32_t duracaoMs) {
  for (uint32_t i = 0; i < duracaoMs; i++) {
    e.passo();
    f.ms++;
  }
}

void setUp() { recebidas.clear(); }
void tearDown() {}

static void test_handshake_e_rodada_de_tabelas() {
  EcuFalsa f;
  Enlace e(f, Config::padrao());
  e.aoQuadro(anotar, nullptr);
  rodar(e, f, 60);
  TEST_ASSERT_EQUAL(PULSO_BAIXO, e.estado());
  TEST_ASSERT_TRUE(f.baixa);
  rodar(e, f, 15);  // 75 ms: nível baixo acabou
  TEST_ASSERT_FALSE(f.baixa);
  TEST_ASSERT_TRUE(f.tx.empty());  // nada sai antes de 70 + 120 ms
  rodar(e, f, 200);
  TEST_ASSERT_EQUAL(ATIVO, e.estado());
  TEST_ASSERT_EQUAL(1, f.pulsos);
  TEST_ASSERT_TRUE(f.msLiberada - f.msBaixa >= PULSO_BAIXO_MS);
  TEST_ASSERT_TRUE(f.msPrimeiraEscrita - f.msLiberada >= PULSO_ALTO_MS);
  TEST_ASSERT_EQUAL_HEX8_ARRAY(WAKE, f.tx.data(), 4);
  TEST_ASSERT_EQUAL_HEX8_ARRAY(INIT, f.tx.data() + 4, 5);
  TEST_ASSERT_TRUE(recebidas.size() >= 6);
  const uint8_t ordem[] = {0x11, 0x13, 0x17, 0x11, 0x13, 0x17};
  TEST_ASSERT_EQUAL_HEX8_ARRAY(ordem, recebidas.data(), 6);
  TEST_ASSERT_EQUAL(0, e.contadores().timeouts);
  TEST_ASSERT_EQUAL(0, e.contadores().ecoErrado);
}

static void test_tabela_que_nao_responde_sai_da_rodada_sem_derrubar_o_enlace() {
  EcuFalsa f;
  f.semResposta.insert(0x13);
  Enlace e(f, Config::padrao());
  e.aoQuadro(anotar, nullptr);
  rodar(e, f, 4000);
  TEST_ASSERT_EQUAL(ATIVO, e.estado());
  TEST_ASSERT_EQUAL(0, e.contadores().reconexoes);
  TEST_ASSERT_EQUAL(3, e.contadores().timeouts);
  TEST_ASSERT_TRUE(e.tabelaCalada(1));
  size_t n13 = 0, n17 = 0;
  for (uint8_t t : recebidas) {
    n13 += t == 0x13;
    n17 += t == 0x17;
  }
  TEST_ASSERT_EQUAL(0, n13);
  TEST_ASSERT_TRUE(n17 > 50);
}

static void test_ecu_que_some_provoca_reconexao_e_volta() {
  EcuFalsa f;
  Enlace e(f, Config::padrao());
  e.aoQuadro(anotar, nullptr);
  rodar(e, f, 500);
  TEST_ASSERT_EQUAL(ATIVO, e.estado());
  f.muda = true;
  rodar(e, f, 4 * 300 + 50);
  TEST_ASSERT_EQUAL(ESPERA_RECONEXAO, e.estado());
  TEST_ASSERT_EQUAL(1, e.contadores().reconexoes);
  f.muda = false;
  f.acordada = false;
  rodar(e, f, 1000);
  TEST_ASSERT_EQUAL(ATIVO, e.estado());
  TEST_ASSERT_EQUAL(2, f.pulsos);
}

static void test_sem_resposta_ao_wake_tenta_de_novo() {
  EcuFalsa f;
  f.muda = true;
  Enlace e(f, Config::padrao());
  rodar(e, f, 3000);
  TEST_ASSERT_TRUE(e.contadores().reconexoes >= 2);
  TEST_ASSERT_TRUE(f.pulsos >= 3);
  TEST_ASSERT_TRUE(e.estado() != ATIVO);
}

static void test_eco_ausente_conta_erro_mas_le_a_resposta() {
  EcuFalsa f;
  f.ecoNaLinha = false;
  Enlace e(f, Config::padrao());
  e.aoQuadro(anotar, nullptr);
  rodar(e, f, 400);
  TEST_ASSERT_EQUAL(ATIVO, e.estado());
  TEST_ASSERT_TRUE(e.contadores().ecoErrado > 0);
  TEST_ASSERT_TRUE(recebidas.size() > 3);
}

static void test_resposta_de_outra_tabela_e_ignorada() {
  EcuFalsa f;
  f.trocaTabela = 0x42;
  Enlace e(f, Config::padrao());
  e.aoQuadro(anotar, nullptr);
  rodar(e, f, 2000);  // 190 ms de wake + 4 timeouts de 300 ms
  TEST_ASSERT_EQUAL(0, recebidas.size());
  TEST_ASSERT_TRUE(e.contadores().ignorados > 0);
  TEST_ASSERT_TRUE(e.contadores().reconexoes >= 1);
}

static void test_silencio_descarta_quadro_pela_metade() {
  EcuFalsa f;
  Config c = Config::padrao();
  c.nTabelas = 1;
  Enlace e(f, c);
  e.aoQuadro(anotar, nullptr);
  rodar(e, f, 300);
  TEST_ASSERT_EQUAL(ATIVO, e.estado());
  size_t antes = recebidas.size();
  f.muda = true;  // a requisição seguinte fica sem resposta automática
  rodar(e, f, 20);
  // começo de uma resposta longa (48 bytes) que se perdeu, 15 ms de silêncio, depois a resposta
  // inteira. Sem descartar no silêncio, o montador ficaria esperando os 48 bytes e perderia esta.
  const uint8_t cortada[] = {TIPO_RESP, 48, CONSULTA_TABELA};
  uint8_t q[25] = {TIPO_RESP, 25, CONSULTA_TABELA, 0x11};
  q[24] = checksum(q, 24);
  f.rx.insert(f.rx.end(), cortada, cortada + 3);
  rodar(e, f, 15);
  f.rx.insert(f.rx.end(), q, q + 25);
  rodar(e, f, 2);
  TEST_ASSERT_EQUAL(antes + 1, recebidas.size());
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_handshake_e_rodada_de_tabelas);
  RUN_TEST(test_tabela_que_nao_responde_sai_da_rodada_sem_derrubar_o_enlace);
  RUN_TEST(test_ecu_que_some_provoca_reconexao_e_volta);
  RUN_TEST(test_sem_resposta_ao_wake_tenta_de_novo);
  RUN_TEST(test_eco_ausente_conta_erro_mas_le_a_resposta);
  RUN_TEST(test_resposta_de_outra_tabela_e_ignorada);
  RUN_TEST(test_silencio_descarta_quadro_pela_metade);
  return UNITY_END();
}
