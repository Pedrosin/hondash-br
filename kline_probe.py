"""Fase 0: sonda a ECU Honda (K-line, 10400 8N1) via ponte serial USB.

Uso (Mac): pip install pyserial; python3 kline_probe.py /dev/cu.usbserial-XXXX
Sem o carro: python -m emulador (outro terminal) e
             python3 kline_probe.py socket://127.0.0.1:35000
Opções: --duracao S (para sozinho), --saida ARQ.csv

Pressupõe um firmware de ponte no Nano que:
  - repassa bytes USB -> K-line e K-line -> USB a 10400 baud;
  - ao receber o byte 0x21 ('!') gera o pulso de wake-up (70 ms baixo, 120 ms alto).
A linha K é de um fio só: tudo que enviamos volta como eco; descartamos o eco.
Só leitura: nunca envia nada além de wake-up, init e requisições de tabela.
Protocolo (fonte pública, não validado no carro): ver FASE-0.md.
"""
import argparse
import csv
import time
from datetime import datetime

import serial

WAKE = bytes.fromhex("FE 04 72 8C")
WAKE_OK = bytes.fromhex("0E 04 72 7C")
INIT = bytes.fromhex("72 05 00 F0 99")
INIT_OK = bytes.fromhex("02 04 00 FA")
TABLES = [0x11, 0x13, 0x17]
PERIOD = 0.2
TIMEOUT = 0.4


def checksum(frame: bytes) -> int:
    return (0x100 - (sum(frame) & 0xFF)) & 0xFF


def request(table: int) -> bytes:
    body = bytes([0x72, 0x05, 0x71, table])
    return body + bytes([checksum(body)])


def read_frame(ser) -> bytes:
    """Lê um quadro inteiro pelo byte de tamanho (byte 1 = total, com checksum).

    Não depende de in_waiting: a resposta pode chegar em pedaços pela USB.
    No timeout devolve o que chegou (vazio = ECU calada).
    """
    head = ser.read(2)
    if len(head) < 2 or not 3 <= head[1] <= 64:
        return head
    return head + ser.read(head[1] - 2)


def exchange(ser, tx: bytes) -> bytes:
    """Envia tx, descarta o eco e devolve o quadro que a ECU respondeu."""
    ser.reset_input_buffer()
    ser.write(tx)
    ser.flush()
    echo = ser.read(len(tx))
    if echo != tx:
        print(f"  aviso: eco inesperado {echo.hex(' ')} (esperado {tx.hex(' ')})")
    resp = read_frame(ser)
    if resp and (len(resp) < 2 or len(resp) != resp[1] or sum(resp) & 0xFF):
        print(f"  aviso: quadro incompleto ou checksum errado: {resp.hex(' ')}")
    return resp


def wake_and_init(ser) -> bool:
    ser.reset_input_buffer()
    ser.write(b"!")
    time.sleep(0.25)
    ser.reset_input_buffer()
    resp = exchange(ser, WAKE)
    print(f"wake: {resp.hex(' ')}")
    if resp != WAKE_OK:
        return False
    resp = exchange(ser, INIT)
    print(f"init: {resp.hex(' ')}")
    return resp == INIT_OK


def main(argv=None) -> int:
    assert checksum(bytes.fromhex("72 05 00 F0")) == 0x99
    assert request(0x13)[-1] == 0x05 and request(0x11)[-1] == 0x07
    ap = argparse.ArgumentParser(description="Sonda a ECU Honda OBD1 pela ponte USB do Nano.")
    ap.add_argument("porta", help="/dev/cu.usbserial-XXXX, COMn ou socket://host:porta (emulador)")
    ap.add_argument("--duracao", type=float, help="segundos de log; sem isso roda até Ctrl+C")
    ap.add_argument("--saida", help="arquivo CSV (padrão: log-AAAA-MM-DD-HHMMSS.csv)")
    a = ap.parse_args(argv)
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    ser = serial.serial_for_url(a.porta, 115200, timeout=TIMEOUT)
    if "://" not in a.porta:
        time.sleep(2)  # Nano reinicia ao abrir a porta
    try:
        if not wake_and_init(ser):
            print("sem resposta de init: ver Diagnóstico em FASE-0.md")
            return 1
        with open(a.saida or f"log-{stamp}.csv", "w", newline="") as f:
            out = csv.writer(f)
            out.writerow(["t_s", "tabela", "bytes_hex"])
            t0 = time.time()
            try:
                while a.duracao is None or time.time() - t0 < a.duracao:
                    for t in TABLES:
                        resp = exchange(ser, request(t))
                        out.writerow([f"{time.time() - t0:.3f}", f"{t:02X}", resp.hex()])
                        print(f"{t:02X}: {resp.hex(' ')}")
                        valid = len(resp) >= 3 and len(resp) == resp[1] and not sum(resp) & 0xFF
                        if not valid and not wake_and_init(ser):
                            print("perdeu a ECU")
                            return 1
                    f.flush()
                    time.sleep(PERIOD)
            except KeyboardInterrupt:
                print("encerrado")
        return 0
    finally:
        ser.close()


if __name__ == "__main__":
    raise SystemExit(main())
