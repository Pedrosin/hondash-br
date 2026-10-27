"""Fase 0: sonda a ECU Honda (K-line, 10400 8N1) via ponte serial USB.

Uso (Mac): pip install pyserial; python3 kline_probe.py /dev/cu.usbserial-XXXX

Pressupõe um firmware de ponte no Nano que:
  - repassa bytes USB -> K-line e K-line -> USB a 10400 baud;
  - ao receber o byte 0x21 ('!') gera o pulso de wake-up (70 ms baixo, 120 ms alto).
A linha K é de um fio só: tudo que enviamos volta como eco; descartamos o eco.
Só leitura: nunca envia nada além de wake-up, init e requisições de tabela.
Protocolo (fonte pública, não validado no carro): ver FASE-0.md.
"""
import csv
import sys
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


def exchange(ser: serial.Serial, tx: bytes, expect: int = 0) -> bytes:
    """Envia tx, descarta o eco e devolve o que a ECU respondeu."""
    ser.reset_input_buffer()
    ser.write(tx)
    ser.flush()
    echo = ser.read(len(tx))
    if echo != tx:
        print(f"  aviso: eco inesperado {echo.hex(' ')} (esperado {tx.hex(' ')})")
    time.sleep(0.05)
    return ser.read(expect or ser.in_waiting or 64)


def wake_and_init(ser: serial.Serial) -> bool:
    ser.reset_input_buffer()
    ser.write(b"!")
    time.sleep(0.25)
    ser.reset_input_buffer()
    resp = exchange(ser, WAKE, len(WAKE_OK))
    print(f"wake: {resp.hex(' ')}")
    if resp != WAKE_OK:
        return False
    resp = exchange(ser, INIT, len(INIT_OK))
    print(f"init: {resp.hex(' ')}")
    return resp == INIT_OK


def main() -> None:
    assert checksum(bytes.fromhex("72 05 00 F0")) == 0x99
    assert request(0x13)[-1] == 0x05 and request(0x11)[-1] == 0x07
    port = sys.argv[1]
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    ser = serial.Serial(port, 115200, timeout=TIMEOUT)
    time.sleep(2)  # Nano reinicia ao abrir a porta
    if not wake_and_init(ser):
        print("sem resposta de init: ver Diagnóstico em FASE-0.md")
        return
    with open(f"log-{stamp}.csv", "w", newline="") as f:
        out = csv.writer(f)
        out.writerow(["t_s", "tabela", "bytes_hex"])
        t0 = time.time()
        try:
            while True:
                for t in TABLES:
                    resp = exchange(ser, request(t))
                    out.writerow([f"{time.time() - t0:.3f}", f"{t:02X}", resp.hex()])
                    print(f"{t:02X}: {resp.hex(' ')}")
                    if not resp and not wake_and_init(ser):
                        print("perdeu a ECU")
                        return
                f.flush()
                time.sleep(PERIOD)
        except KeyboardInterrupt:
            print("encerrado")


if __name__ == "__main__":
    main()
