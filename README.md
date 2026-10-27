# Hondash-BR — painel digital nacional para Honda OBD1

Projeto pessoal.
Meta: app Android (PT-BR) + adaptador próprio, inspirado no conceito do app Hondash. Se ficar bom e barato, vender.

## Contexto
- Carro de teste: Honda Civic EH 93/94, conector de diagnóstico de 3 pinos (OBD1). O Victor tem o carro.
- Ferramentas: multímetro, MacBook Pro M1.
- Preferência: construir só o app se possível; adaptador próprio também desejado. Decisão: fazer os dois, em fases.

## Como funciona (resumo)
ECU Honda (Keihin) ⇄ K-line (1 fio, 5V) ⇄ adaptador (MCU + transceiver) ⇄ Bluetooth ⇄ app.
O protocolo é Honda proprietário, NÃO é OBD2: ELM327 comum não lê. Detalhe em FASE-0.md.

## Fases
0. Prova de protocolo: ler a ECU do EH e logar bytes crus no Mac. **Decide o resto.**
1. Firmware próprio (ESP32, protocolo bruto, BLE — BLE porque SPP não funciona em iPhone).
2. App Android (Kotlin + Compose): gauges, alarmes, datalog CSV+GPS, DTC, PT-BR.
3. Produto: caixa, homologação Anatel (rádio BT), iOS se houver venda.

## Regras do projeto
- Não copiar código, nome, marca ou layout do Hondash. Reimplementar o protocolo a partir de documentação pública e dos logs do próprio carro. Nome do produto sem "Honda"/"Hondash".
- Licença do projeto Arduino de referência não é declarada: usar como referência de hardware, não copiar código.
- Quem valida no carro é o Victor; o agente não tem acesso ao veículo.

## Estado
- 2026-10-01: projeto aberto, Fase 0 detalhada. Nada comprado/testado ainda.
- 2026-10-27: emulador da ECU, firmware ESP32 (compila; lógica testada no host contra o emulador) e painel de teste prontos. Nada validado no carro: offsets, fórmulas, tamanhos de tabela e tempos da ECU são HIPÓTESE (`emulador/mapa_ecu.toml`). Decisões em `DECISOES.md`.

## Pastas
| Pasta | O quê |
|---|---|
| `kline_probe.py` | sonda da Fase 0 (Mac + Nano), também roda contra o emulador |
| `emulador/` | ECU virtual em Python: handshake, tabelas, sono de 2 s, cenários e replay de log |
| `emulador/mapa_ecu.toml` | **único** arquivo de offsets/fórmulas (tudo HIPÓTESE): trocar quando sair o log real |
| `firmware/` | adaptador ESP32 (PlatformIO): K-line + BLE GATT (`firmware/BLE.md`) |
| `painel-teste/` | ponte (serial/socket → websocket) + página que mostra os valores |
| `leitor-pisca/` | outro subprojeto (não mexer a partir daqui) |

## Sem o carro (emulador)
Preparar uma vez (Mac: `python3`; Windows: `py -3.12`):
```
python3 -m venv .venv && .venv/bin/pip install pyserial pytest websockets platformio
```
(no Windows sem gcc, somar `ziglang`; caminhos em `.venv\Scripts\`.)

Terminal 1 — ECU virtual (porta 35000, modo da ponte do Nano):
```
.venv/bin/python -m emulador --cenario ciclo        # ou marcha_lenta, puxada, ... ou --replay log.csv
```
Terminal 2 — a sonda, igual seria no carro:
```
.venv/bin/python kline_probe.py socket://127.0.0.1:35000 --duracao 10
```
Ou o painel: `.venv/bin/python painel-teste/ponte.py` e abrir http://127.0.0.1:8765/.

Cenários: `partida_fria`, `aquecimento`, `marcha_lenta`, `puxada` (até o corte), `desaceleracao`, `ciclo` (todos em sequência).

## Testes
```
.venv/bin/python -m pytest emulador painel-teste      # emulador, probe, ponte
node --test "painel-teste/tests/*.test.mjs"           # render do painel
cd firmware && ../.venv/bin/pio test -e native         # lógica do firmware, inclusive contra o emulador
cd firmware && ../.venv/bin/pio run -e esp32dev        # compila o alvo
```

## Validar no carro (o que só o Victor pode fazer)
1. Fase 0 como está em `FASE-0.md` (multímetro, Nano, `kline_probe.py` no Mac). O probe já lê a resposta pelo tamanho; o firmware de ponte do Nano ainda precisa ser escrito depois do circuito confirmado.
2. Se o init responder: gravar as sessões A/B/C. Os CSV entram direto no emulador (`--replay`) e servem para corrigir `emulador/mapa_ecu.toml`.
3. Medir o que hoje é suposição: se 0x13/0x17 respondem e com quantos bytes, a latência da resposta, se a ECU dorme mesmo em ~2 s.
4. Fase 1 (ESP32): conferir no osciloscópio/multímetro o pulso de 70 ms baixo na K-line (polaridade depende do transceiver) antes de ligar no carro.

## Fontes
- Protocolo K-line Keihin: https://github.com/AutotronicCommunity/Honda_Keihin_KLine_Protocol
- Adaptador Arduino→ELM327 (referência de hardware): https://github.com/mr-sneezy/ArduinoHondaOBD1_to_OBD2_BT
- Ligação no DLC e energia: https://www.hondash.net/2018/03/dlc-interface-power-management.html
- App (funcionalidades): https://www.hondash.net/p/app-for-android.html
