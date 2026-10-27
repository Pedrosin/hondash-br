# Fase 0 — Prova de protocolo

**Objetivo:** com o Civic EH, conseguir (1) acordar a ECU, (2) receber a resposta de init, (3) puxar as tabelas de dados e salvar os bytes crus num arquivo no Mac.
**Pronto quando:** existe um log de ≥60 s com a tabela 0x11 (e 0x13/0x17 se responderem) em 3 situações: ignição ligada/motor parado, marcha lenta, e rotação variando — com as mudanças anotadas, pra decodificar RPM/ECT/etc. por correlação.
Nada aqui escreve na ECU. Só leitura.

## O que o protocolo diz (fonte pública, ainda NÃO validado no seu carro)
Fonte: [Honda_Keihin_KLine_Protocol](https://github.com/AutotronicCommunity/Honda_Keihin_KLine_Protocol)

| Item | Valor |
|---|---|
| Baud | 10400, 8N1 |
| Wake-up | linha K em nível baixo 70 ms, depois alto 120 ms, e então envia `FE 04 72 8C` |
| Resposta do wake-up | `0E 04 72 7C` |
| Init | envia `72 05 00 F0 99` → ECU responde `02 04 00 FA` |
| Requisição | `72 AA BB CC CS` (AA = nº de bytes incluindo checksum, BB = tabela de consulta, CC = tabela de dados) |
| Checksum | `CS = (0x100 − (soma dos bytes anteriores & 0xFF)) & 0xFF` |
| Exemplos | ID da ECU: `72 05 71 00 18`; tabela 0x11: `72 05 71 11 07`; tabela 0x13: `72 05 71 13 05` |
| Resposta tabela 0x11 | começa com `02 19 71 11` + dados (25 bytes no total) |
| Timeout | se passar ~2 s sem requisição, a ECU volta a dormir: refazer wake-up + init |

Conferi o checksum à mão nos exemplos acima (`72 05 00 F0` → `99`; `72 05 71 13` → `05`). O repositório NÃO documenta o que cada byte da tabela significa, nem DTC. Isso é trabalho da Fase 0: decodificar por correlação com o carro.
A linha K é de um fio só: tudo que você transmite volta como eco. O script descarta o eco.

## Passo 1 — Medir no carro (só multímetro, sem comprar nada)
1. Localizar o conector de 3 pinos (geralmente sob o painel, lado do passageiro, perto da caixa de fusíveis).
2. Ignição OFF: medir continuidade entre cada pino e o chassi → o que tiver continuidade é **GND**.
3. Ignição ON (motor parado): tensão dos outros dois contra GND.
   - ~12 V (pode ser só com ignição ON) = **+12V**
   - ~5 V ou flutuando = candidato a **K-line**
4. Anotar a ordem física dos pinos e as tensões. Não ligar nada ainda.
Qualquer coisa fora disso (ex.: nenhum pino a ~5 V): parar e me mandar as medidas. Um módulo de 3,3 V ou 5 V ligado em 12 V queima na hora.

## Passo 2 — Lista de compras (Fase 0)
| Item | Para quê |
|---|---|
| Arduino Nano (clone, CH340) | MCU de 5 V: casa com o nível da K-line sem conversão. ESP32 (3,3 V) fica pra Fase 1 |
| Cabo USB-A→mini/micro (conforme o Nano) + adaptador USB-C no Mac | ligar no MacBook M1 |
| Transceiver K-line: L9637D (SO-8, precisa de placa adaptadora) **ou** o circuito discreto do repositório de referência | interface elétrica com a K-line |
| Protoboard, jumpers, resistores 510 Ω / 1 kΩ / 10 kΩ, diodos 1N4148, 1 diodo 1N4007 | circuito e proteção |
| Conversor 12 V → 5 V (módulo LM2596 ou 7805) | alimentar o Nano pelo carro. Para a bancada, dá pra usar só a USB do Mac |
| Chicote/pigtail de 3 pinos Honda (ou fios + terminais) | conectar ao DLC sem improvisar |
Custo esperado: baixo (estimativa minha, dezenas de reais).
**Antes de montar:** conferir o esquema discreto do [ArduinoHondaOBD1_to_OBD2_BT](https://github.com/mr-sneezy/ArduinoHondaOBD1_to_OBD2_BT) (versão compacta usa 2 resistores e 2 diodos, K-line no pino 12 do Nano). Eu não validei os valores de componente: confirmar no repositório (pasta Fritzing) ou comigo antes de soldar.

## Passo 3 — Montagem e teste de bancada
1. Mac: instalar o driver CH340 (se o clone precisar) e o Arduino IDE ou `arduino-cli`.
2. Montar o circuito. Testar primeiro **sem o carro**: alimentar pela USB, conferir com o multímetro que a K-line fica em ~5 V em repouso.
3. Firmware do Nano: ponte transparente USB⇄K-line a 10400 baud + comando para gerar o pulso de wake-up (70 ms baixo / 120 ms alto). Escrevo depois que o circuito estiver confirmado (a forma de fazer TX/RX numa linha só depende do circuito escolhido).

## Passo 4 — Primeira conversa com a ECU (no carro)
1. Ignição ON, motor parado. Conectar o chicote (GND, +12V, K) com tudo desligado, então ligar a ignição.
2. Rodar `kline_probe.py` (mesma pasta): wake-up → `FE 04 72 8C`, espera `0E 04 72 7C` → init `72 05 00 F0 99`, espera `02 04 00 FA`.
3. Se não responder: ver "Diagnóstico" abaixo.
4. Se responder: pedir o ID da ECU (`72 05 71 00 18`) e as tabelas 0x11, 0x13, 0x17 em laço, a cada ~200 ms, com marcação de tempo.

## Passo 5 — Logs para decodificar
Gravar 3 sessões, anotando em voz alta/num papel o que muda e a hora:
- A: ignição ON, motor parado, 30 s.
- B: marcha lenta, 60 s (anotar temperatura do motor no painel).
- C: acelerar devagar 1000 → 3000 → 1000 rpm (anotar valores do conta-giros), sem passar de 3000.
Com isso eu cruzo os bytes que variam com RPM, ECT, TPS e tensão e proponho a decodificação. Fórmulas conhecidas de outras ECUs Honda não valem automaticamente: confirmar por comparação com o painel.

## Diagnóstico (se não responder)
| Sintoma | Causa provável |
|---|---|
| Silêncio total | pino errado, GND ausente, wake-up fora de tempo, ECU sem alimentação |
| Só eco, sem resposta | wake-up com timing errado; ECU de outro protocolo/ano (a sua pode ser pré-Keihin K-line, ex. 92) |
| Resposta de wake-up mas init falha | checksum/baud (testar 9600) |
| Responde e some após ~2 s | faltou manter requisições em laço |
Se nada disso resolver, a leitura direta pelo DLC pode não existir nessa ECU. Nesse caso o plano muda: header de 4 pinos do CN2 (ECU com chip) ou ECU diferente. Esse é o risco que a Fase 0 existe pra revelar.

## Saídas da Fase 0
- `logs/AAAA-MM-DD-sessao-{A,B,C}.bin` + `.csv` (tempo, tabela, bytes hex).
- Decodificação proposta de RPM, ECT, IAT, TPS, tensão, flags — com a evidência de cada uma.
- Esquema do circuito validado no carro (vira o da Fase 1).
- Decisão go/no-go para a Fase 1.

## Segurança
- Nunca ligar a K-line a mais de 5 V.
- Dois alimentadores ao mesmo tempo (USB do Mac + 12 V do carro no Nano) sem diodo/isolamento podem queimar a porta ou o Nano. Em carro, desconectar a USB.
- Fusível de 1 A no +12V do chicote.
- Tudo é leitura: o script só envia requisições `72 .. 71 ..` e o init.
