# Serviço BLE do adaptador (KLink-BR)

O firmware não decodifica sensores: repassa o quadro cru de cada tabela. A conversão
(offset, fórmula) mora no app/painel, lida de `emulador/mapa_ecu.toml`, para que trocar
o mapa depois do log real do carro não exija regravar o ESP32.

Nome anunciado: `KLink-BR`. Campos do envelope BLE (ms, contadores, intervalo) são little-endian; os bytes do quadro cru seguem a ordem da ECU, definida em `mapa_ecu.toml` (hoje big-endian, HIPÓTESE). Byte 0 de todo payload = versão do formato (`0x01`).

| Característica | UUID | Propriedades |
|---|---|---|
| Serviço | `6b1f0000-3c5e-4d8a-9b2e-7a41c0d9e5f1` | — |
| Tabela | `6b1f0001-3c5e-4d8a-9b2e-7a41c0d9e5f1` | read, notify |
| Estado | `6b1f0002-3c5e-4d8a-9b2e-7a41c0d9e5f1` | read, notify (a cada 500 ms) |
| Config | `6b1f0003-3c5e-4d8a-9b2e-7a41c0d9e5f1` | read, write |

## Tabela (uma notificação por resposta da ECU)

| Bytes | Campo |
|---|---|
| 0 | versão (`0x01`) |
| 1–4 | instante em ms desde o boot do ESP32 (u32) |
| 5… | quadro cru da ECU: `02 LL 71 TT <dados> CS` (LL = tamanho total do quadro) |

A tabela 0x11 dá 30 bytes de payload, mais que os 20 do MTU padrão: **o cliente precisa
pedir MTU ≥ 72** (Android: `requestMtu(185)`; iOS negocia sozinho). Sem isso a notificação
chega truncada.

## Estado (14 bytes)

| Bytes | Campo |
|---|---|
| 0 | versão |
| 1 | estado do enlace: 0 ocioso, 1 pulso baixo, 2 pulso alto, 3 espera wake, 4 espera init, 5 ativo, 6 espera reconexão |
| 2–5 | quadros recebidos (u32) |
| 6–9 | timeouts (u32) |
| 10–11 | reconexões (u16, satura em 65535) |
| 12–13 | eco diferente do enviado (u16, satura) — sinal de problema elétrico na linha |

## Config (escrita; leitura devolve a config em uso)

| Bytes | Campo |
|---|---|
| 0 | versão |
| 1–2 | pausa entre resposta e próxima requisição, ms (u16) |
| 3 | n = quantidade de tabelas, 1 a 8 |
| 4… | n números de tabela, consultados em rodízio |

Payload inválido (versão, n fora de 1–8, tamanho ≠ 4+n) é ignorado. Padrão: tabelas
`11 13 17`, pausa 10 ms. Tabela que fica 3 vezes seguidas sem resposta sai da rodada até
a próxima reconexão; 4 timeouts seguidos (qualquer tabela) disparam novo wake-up.
