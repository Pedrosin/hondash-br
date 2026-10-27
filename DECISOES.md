# Decisões técnicas

Formato: o quê · alternativa descartada · motivo. Datas em 2026.

## Emulador (27/10)

1. **ECU virtual como máquina de estados pura com relógio injetado** (`emulador/ecu.py`), transporte separado (`servidor.py`). · Descartado: lógica dentro do loop do socket. · Teste de timing (sono de 2 s, latência, pulso) sem dormir e sem flutuação de rede; o mesmo núcleo serve TCP e testes.
2. **Transporte TCP (`socket://` do pyserial)**. · Descartado: `loop://` do pyserial e porta COM virtual (com0com). · `loop://` é um eco do próprio processo, não tem "outro lado"; COM virtual é driver/configuração de sistema (fora do escopo). TCP funciona igual no Windows e no Mac sem instalar nada.
3. **Dois modos de linha**: `ponte` (o que o `kline_probe.py` vê pela USB do Nano: `'!'` pede o pulso, não ecoa) e `kline` (linha crua, para o firmware). Padrão da CLI = `ponte`. · Descartado: um modo só. · O probe fala com o firmware de ponte do Nano, o ESP32 fala com a linha: protocolos de transporte diferentes.
4. **Pulso de wake-up modelado por silêncio** no modo kline: o FE só é aceito com ≥ 120 ms de linha quieta antes. · Descartado: byte especial em banda para "nível baixo". · Num fluxo de bytes não existe nível baixo de 70 ms; inventar um byte criaria um protocolo que o hardware não tem. O nível baixo só se prova no carro/osciloscópio (HIPÓTESE).
5. **Silêncio > 10 ms descarta quadro incompleto** (emulador e firmware). · Descartado: só ressincronização por checksum. · Achado nos testes: um quadro com checksum errado deixava o montador esperando bytes que não vinham e engolia as requisições seguintes. 10 ms ≈ 10 bytes de silêncio a 10400 baud (HIPÓTESE quanto à ECU real).
6. **Montador filtra o tipo do primeiro byte** (respostas `02`/`0E`; requisições `72`/`FE`). · Descartado: aceitar qualquer byte inicial. · Achado no teste: lixo + checksum de 8 bits formou um quadro falso que comeu o começo do quadro bom.
7. **Cenários como funções fechadas do tempo, sem aleatoriedade** (`motor.py`). · Descartado: simulação física integrada com ruído aleatório. · Testes conferem valores exatos; a ondulação (seno) basta para parecer vivo no painel.
8. **Replay lê o CSV que o próprio `kline_probe.py` grava**. · Descartado: formato próprio de log. · O log real do carro vira entrada do emulador sem conversão.
9. **Mapa de offsets num único TOML** (`emulador/mapa_ecu.toml`), cada entrada com `status = "HIPOTESE"`, inclusive tamanhos de tabela e tempos. · Descartado: JSON (sem comentário) e constantes no código. · Trocar o mapa depois do log real é editar um arquivo; o loader valida sobreposição e offset fora da tabela.
10. **Fórmulas do mapa provisório escolhidas para serem inversíveis e plausíveis** (rpm = 1875000/bruto, demais lineares). · Descartado: copiar tabelas de termistor/fórmulas de ECUs Honda conhecidas. · Não valem automaticamente para o EH (FASE-0.md) e não temos fonte com licença clara; o que importa agora é o encanamento, não o número.
11. **Tabelas 0x13/0x17 com 16 bytes zerados e 0x00 com 4 bytes fixos**. · Descartado: deixar sem resposta. · A fonte não diz o tamanho; responder permite exercitar o rodízio de tabelas. HIPÓTESE pura.

## kline_probe.py (27/10)

12. **Ler a resposta pelo byte de tamanho** em vez de `in_waiting` 50 ms após o eco. · Descartado: manter e só aumentar o sleep. · Provado contra o emulador: o original gravava `13: 02` (resposta truncada) porque a resposta ainda não tinha chegado inteira; pela USB do Nano o risco é o mesmo com latência da ECU > ~25 ms. Ler por tamanho independe de tempo.
13. **`serial.serial_for_url` + `--duracao`/`--saida`**, sem `sleep(2)` quando a porta é URL. · Descartado: script separado para o emulador. · Uso no Mac continua `python3 kline_probe.py /dev/cu.usbserial-XXXX`; o mesmo arquivo roda contra o emulador e nos testes.

## Firmware (27/10)

14. **Lógica de protocolo em `firmware/lib/kline` sem Arduino**, hardware atrás da interface `Transporte`. · Descartado: código direto no `main.cpp`. · Permite `pio test -e native` com a mesma máquina de estados que vai no ESP32.
15. **Enlace não bloqueante** (`passo()` no loop, tempos por `millis` com subtração sem sinal). · Descartado: `delay()` no wake-up. · O BLE e o envio de estado não podem parar 190 ms; e o teste com ECU falsa roda com relógio simulado.
16. **Tabela que falha 3 vezes seguidas sai da rodada; 4 timeouts seguidos de qualquer tabela = reconexão**. · Descartado: reconectar a cada timeout. · Se o EH não tiver 0x13/0x17, o adaptador não pode entrar em laço de wake-up; e ECU que dormiu precisa ser detectada rápido.
17. **Firmware repassa o quadro cru por BLE; quem decodifica é o app/painel**. · Descartado: decodificar no ESP32. · Os offsets são hipótese; mudar o mapa não pode exigir regravar o adaptador. Formato em `firmware/BLE.md`.
18. **UUIDs próprios aleatórios (base `6b1f….-3c5e-4d8a-9b2e-7a41c0d9e5f1`) e nome `KLink-BR`**. · Descartado: Nordic UART Service. · NUS é genérico e não diz o que é cada byte; 3 características tipadas (tabela, estado, config) com versão no byte 0.
19. **BLE do core (Bluedroid)**. · Descartado: NimBLE-Arduino. · Zero dependência extra. Custo: flash em 86 % da partição padrão. Se faltar espaço (OTA, logs), trocar para NimBLE ou partição `huge_app` — decisão para a Fase 1.
20. **Plataforma fixada em `espressif32@6.13.0`** (Arduino core 2.0.17). · Descartado: versão flutuante. · Build reprodutível; o `onWrite` da config compila tanto com `std::string` (2.x) quanto `String` (3.x).
21. **Testes nativos no Windows com o zig (`pip install ziglang`) como gcc**, via wrappers gerados em `.pio/`. · Descartado: instalar MinGW/MSYS2 no sistema. · Fica tudo no venv; no Mac o env native usa o clang do Xcode e o script não faz nada.
22. **Suite `test_emulador` sobe o emulador Python pelo runner customizado do PlatformIO** (`test/test_custom_runner.py`). · Descartado: transcrições gravadas do emulador como fixture. · O pedido era testar contra o emulador de verdade, em tempo real, inclusive a ECU dormindo e o enlace reconectando.
23. **Pinos 16 (RX) / 17 (TX) da UART2 e transceiver tipo L9637D** (TX baixo = K baixo). · Descartado: nada ainda (sem hardware). · HIPÓTESE: um circuito discreto com transistor pode inverter o nível do pulso.

## Painel de teste (27/10)

24. **Ponte Python (pyserial → websockets) que serve também o HTML na mesma porta**. · Descartado: servidor HTTP separado ou Node. · Um processo, reaproveita `emulador.cliente` e o mapa; `websockets` já estava no venv.
25. **Render como função pura que devolve string** (`painel.mjs`), testada com `node --test` e WebSocket falso. · Descartado: jsdom/Playwright e screenshot. · Prova o que aparece na tela sem dependência nova nem navegador.

## Repositório (27/10)

26. **git na raiz, commits só das minhas pastas**; `.venv` ignorado em `.git/info/exclude`, `.gitignore` por pasta. · Descartado: `.gitignore` na raiz. · A raiz é compartilhada com `leitor-pisca/` (outra sessão), que fica fora dos meus commits.
