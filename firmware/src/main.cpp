// Adaptador K-line -> BLE (ESP32). Só leitura: wake-up, init e requisições de tabela.
// Hardware (HIPÓTESE até montar e medir): transceiver tipo L9637D, TX do ESP32 -> TX do
// transceiver (nível baixo no pino = K em nível baixo), RX do transceiver -> RX do ESP32 (3,3 V).
// Formato BLE: firmware/BLE.md.
#include <Arduino.h>
#include <BLE2902.h>
#include <BLEDevice.h>
#include <BLEServer.h>

#include "ble_formato.h"
#include "kline_enlace.h"

namespace {

const int PINO_K_RX = 16;
const int PINO_K_TX = 17;
const uint32_t ESTADO_A_CADA_MS = 500;
const char* const NOME_BLE = "KLink-BR";

HardwareSerial& linhaK = Serial2;

class TransporteEsp32 : public kline::Transporte {
 public:
  void iniciar() { linhaK.begin(kline::BAUD, SERIAL_8N1, PINO_K_RX, PINO_K_TX); }
  void escrever(const uint8_t* d, size_t n) override { linhaK.write(d, n); }
  int ler() override { return linhaK.available() ? linhaK.read() : -1; }
  void linhaBaixa() override {
    linhaK.end();
    pinMode(PINO_K_TX, OUTPUT);
    digitalWrite(PINO_K_TX, LOW);
  }
  void linhaLiberada() override { digitalWrite(PINO_K_TX, HIGH); }
  void uartPronta() override {
    iniciar();
    while (linhaK.available()) linhaK.read();
  }
  uint32_t agoraMs() override { return millis(); }
};

TransporteEsp32 transporte;
kline::Enlace enlace(transporte, kline::Config::padrao());

BLECharacteristic* chTabela = nullptr;
BLECharacteristic* chEstado = nullptr;
BLECharacteristic* chConfig = nullptr;
volatile bool conectado = false;

portMUX_TYPE trava = portMUX_INITIALIZER_UNLOCKED;
kline::Config cfgPendente;
bool temCfgPendente = false;

void publicarConfig(const kline::Config& c) {
  uint8_t buf[ble::TAM_MAX_CONFIG];
  size_t n = ble::codificarConfig(c, buf, sizeof(buf));
  chConfig->setValue(buf, n);
}

class CbServidor : public BLEServerCallbacks {
  void onConnect(BLEServer*) override { conectado = true; }
  void onDisconnect(BLEServer* s) override {
    conectado = false;
    s->getAdvertising()->start();
  }
};

class CbConfig : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic* c) override {
    auto v = c->getValue();  // std::string no core 2.x, String no 3.x: as duas têm c_str()/length()
    kline::Config nova = enlace.config();
    if (!ble::decodificarConfig(reinterpret_cast<const uint8_t*>(v.c_str()), v.length(), nova)) return;
    portENTER_CRITICAL(&trava);
    cfgPendente = nova;
    temCfgPendente = true;
    portEXIT_CRITICAL(&trava);
  }
};

void aoQuadro(void*, const uint8_t* q, size_t n, uint32_t ms) {
  uint8_t buf[ble::TAM_MAX_TABELA];
  size_t len = ble::codificarTabela(q, n, ms, buf, sizeof(buf));
  if (!len) return;
  chTabela->setValue(buf, len);
  if (conectado) chTabela->notify();
}

void publicarEstado() {
  uint8_t buf[ble::TAM_ESTADO];
  size_t n = ble::codificarEstado(enlace.estado(), enlace.contadores(), buf, sizeof(buf));
  chEstado->setValue(buf, n);
  if (conectado) chEstado->notify();
}

void iniciarBle() {
  BLEDevice::init(NOME_BLE);
  BLEDevice::setMTU(185);  // quadro de tabela + cabeçalho passa de 20 bytes: cliente deve pedir MTU >= 72
  BLEServer* srv = BLEDevice::createServer();
  srv->setCallbacks(new CbServidor());
  BLEService* svc = srv->createService(ble::UUID_SERVICO);
  chTabela = svc->createCharacteristic(ble::UUID_TABELA,
                                       BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY);
  chTabela->addDescriptor(new BLE2902());
  chEstado = svc->createCharacteristic(ble::UUID_ESTADO,
                                       BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY);
  chEstado->addDescriptor(new BLE2902());
  chConfig = svc->createCharacteristic(ble::UUID_CONFIG,
                                       BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_WRITE);
  chConfig->setCallbacks(new CbConfig());
  publicarConfig(enlace.config());
  svc->start();
  BLEAdvertising* adv = BLEDevice::getAdvertising();
  adv->addServiceUUID(ble::UUID_SERVICO);
  adv->setScanResponse(true);
  BLEDevice::startAdvertising();
}

}  // namespace

void setup() {
  Serial.begin(115200);
  transporte.iniciar();
  enlace.aoQuadro(aoQuadro, nullptr);
  iniciarBle();
}

void loop() {
  static uint32_t ultimoEstado = 0;
  bool aplicar = false;
  kline::Config nova;
  portENTER_CRITICAL(&trava);
  if (temCfgPendente) {
    nova = cfgPendente;
    temCfgPendente = false;
    aplicar = true;
  }
  portEXIT_CRITICAL(&trava);
  if (aplicar) {
    enlace.configurar(nova);
    publicarConfig(nova);
  }

  enlace.passo();

  if (millis() - ultimoEstado >= ESTADO_A_CADA_MS) {
    ultimoEstado = millis();
    publicarEstado();
  }
}
