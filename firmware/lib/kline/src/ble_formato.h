// Formato dos payloads do serviço BLE GATT (documentado em firmware/BLE.md).
// Puro: o main.cpp só copia esses bytes para as características.
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "kline_enlace.h"

namespace ble {

extern const char* const UUID_SERVICO;
extern const char* const UUID_TABELA;  // notify + read: um quadro de tabela por notificação
extern const char* const UUID_ESTADO;  // notify + read: estado do enlace e contadores
extern const char* const UUID_CONFIG;  // write + read: tabelas e intervalo do polling

const uint8_t VERSAO = 1;
const size_t TAM_CAB_TABELA = 5;  // versão + ms (u32 LE)
const size_t TAM_ESTADO = 14;
const size_t TAM_MAX_TABELA = TAM_CAB_TABELA + kline::TAMANHO_MAX;
const size_t TAM_MAX_CONFIG = 4 + kline::MAX_TABELAS;

// [versão][ms u32 LE][quadro cru da ECU, com cabeçalho e checksum]. Devolve 0 se não couber.
size_t codificarTabela(const uint8_t* quadro, size_t n, uint32_t ms, uint8_t* saida, size_t cap);

// [versão][estado][quadrosOk u32][timeouts u32][reconexoes u16][ecoErrado u16], tudo LE.
size_t codificarEstado(uint8_t estado, const kline::Contadores& c, uint8_t* saida, size_t cap);

// [versão][intervaloMs u16 LE][n][tabela x n], 1 <= n <= 8. Só altera cfg se o payload for válido.
bool decodificarConfig(const uint8_t* d, size_t n, kline::Config& cfg);
size_t codificarConfig(const kline::Config& cfg, uint8_t* saida, size_t cap);

}  // namespace ble
