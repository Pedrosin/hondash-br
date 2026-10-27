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

## Fontes
- Protocolo K-line Keihin: https://github.com/AutotronicCommunity/Honda_Keihin_KLine_Protocol
- Adaptador Arduino→ELM327 (referência de hardware): https://github.com/mr-sneezy/ArduinoHondaOBD1_to_OBD2_BT
- Ligação no DLC e energia: https://www.hondash.net/2018/03/dlc-interface-power-management.html
- App (funcionalidades): https://www.hondash.net/p/app-for-android.html
