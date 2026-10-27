// Enlace real (mesmo código do ESP32) contra a ECU virtual Python por TCP, em tempo real.
// O runner (test/test_custom_runner.py) sobe "python -m emulador --modo kline" e passa a porta em EMU_PORTA.
#include <stdlib.h>
#include <unity.h>

#include <chrono>
#include <thread>
#include <vector>

#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
typedef SOCKET Sock;
static const Sock SEM_SOCK = INVALID_SOCKET;
static void fechar(Sock s) { closesocket(s); }
#else
#include <arpa/inet.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <unistd.h>
typedef int Sock;
static const Sock SEM_SOCK = -1;
static void fechar(Sock s) { close(s); }
#endif

#include "kline_enlace.h"

using namespace kline;

struct TransporteSocket : public Transporte {
  Sock s = SEM_SOCK;
  std::chrono::steady_clock::time_point t0 = std::chrono::steady_clock::now();
  int pulsos = 0;

  bool conectar(int porta) {
#ifdef _WIN32
    WSADATA w;
    WSAStartup(MAKEWORD(2, 2), &w);
#endif
    s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    sockaddr_in a = {};
    a.sin_family = AF_INET;
    a.sin_port = htons((unsigned short)porta);
    a.sin_addr.s_addr = htonl(0x7F000001);
    if (connect(s, (sockaddr*)&a, sizeof(a)) != 0) return false;
    int um = 1;
    setsockopt(s, IPPROTO_TCP, TCP_NODELAY, (const char*)&um, sizeof(um));
    return true;
  }
  void desconectar() {
    if (s != SEM_SOCK) fechar(s);
    s = SEM_SOCK;
  }
  void escrever(const uint8_t* d, size_t n) override { send(s, (const char*)d, (int)n, 0); }
  int ler() override {
    fd_set fs;
    FD_ZERO(&fs);
    FD_SET(s, &fs);
    timeval tv = {0, 0};
    if (select((int)s + 1, &fs, nullptr, nullptr, &tv) <= 0) return -1;
    unsigned char b;
    return recv(s, (char*)&b, 1, 0) == 1 ? b : -1;
  }
  // O nível baixo não existe num fluxo de bytes: o emulador modela o wake-up só pelo
  // silêncio de >= 120 ms antes do FE, que o próprio Enlace garante.
  void linhaBaixa() override { pulsos++; }
  void linhaLiberada() override {}
  void uartPronta() override {}
  uint32_t agoraMs() override {
    return (uint32_t)std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - t0)
        .count();
  }
};

static std::vector<std::vector<uint8_t>> quadros;
static void guardar(void*, const uint8_t* q, size_t n, uint32_t) { quadros.push_back(std::vector<uint8_t>(q, q + n)); }

static int porta() {
  const char* p = getenv("EMU_PORTA");
  return p ? atoi(p) : 0;
}

// Roda o enlace até cond() ou até estourar o prazo; devolve cond().
template <typename F>
static bool rodarAte(Enlace& e, TransporteSocket& t, uint32_t prazoMs, F cond) {
  uint32_t fim = t.agoraMs() + prazoMs;
  while (t.agoraMs() < fim) {
    e.passo();
    if (cond()) return true;
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }
  return cond();
}

static uint16_t be16(const std::vector<uint8_t>& q, size_t i) { return (uint16_t)(q[i] << 8 | q[i + 1]); }

void setUp() { quadros.clear(); }
void tearDown() {}

static void test_handshake_e_polling_contra_emulador() {
  if (!porta()) TEST_IGNORE_MESSAGE("EMU_PORTA ausente: rode via pio test -e native (o runner sobe o emulador)");
  TransporteSocket t;
  TEST_ASSERT_TRUE_MESSAGE(t.conectar(porta()), "não conectou no emulador");
  Enlace e(t, Config::padrao());
  e.aoQuadro(guardar, nullptr);
  TEST_ASSERT_TRUE(rodarAte(e, t, 2000, [&] { return e.estado() == ATIVO; }));
  TEST_ASSERT_TRUE(rodarAte(e, t, 3000, [&] { return quadros.size() >= 30; }));
  size_t n11 = 0;
  for (const auto& q : quadros) {
    TEST_ASSERT_TRUE(quadroValido(q.data(), q.size()));
    if (q[3] != 0x11) continue;
    n11++;
    TEST_ASSERT_EQUAL(25, q.size());
    // rpm pelo mapa provisório (offset 0, u16, rpm = 1875000 / bruto): marcha lenta ~760
    uint16_t bruto = be16(q, 4);
    TEST_ASSERT_TRUE(bruto > 0);
    uint32_t rpm = 1875000u / bruto;
    TEST_ASSERT_UINT32_WITHIN(60, 760, rpm);
  }
  TEST_ASSERT_TRUE(n11 >= 10);
  TEST_ASSERT_EQUAL(0, e.contadores().timeouts);
  TEST_ASSERT_EQUAL(0, e.contadores().ecoErrado);
  TEST_ASSERT_EQUAL(0, e.contadores().reconexoes);
  t.desconectar();
}

static void test_ecu_dorme_sem_polling_e_enlace_reconecta() {
  if (!porta()) TEST_IGNORE_MESSAGE("EMU_PORTA ausente");
  TransporteSocket t;
  TEST_ASSERT_TRUE(t.conectar(porta()));
  Enlace e(t, Config::padrao());
  e.aoQuadro(guardar, nullptr);
  TEST_ASSERT_TRUE(rodarAte(e, t, 2000, [&] { return e.estado() == ATIVO; }));
  // loop travado por 2,5 s (ex.: BLE ocupado): a ECU passa de 2 s sem requisição e dorme
  std::this_thread::sleep_for(std::chrono::milliseconds(2500));
  quadros.clear();
  TEST_ASSERT_TRUE(rodarAte(e, t, 5000, [&] { return e.contadores().reconexoes >= 1 && quadros.size() >= 5; }));
  TEST_ASSERT_EQUAL(ATIVO, e.estado());
  TEST_ASSERT_EQUAL(2, t.pulsos);
  t.desconectar();
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_handshake_e_polling_contra_emulador);
  RUN_TEST(test_ecu_dorme_sem_polling_e_enlace_reconecta);
  return UNITY_END();
}
