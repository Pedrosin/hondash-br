"""Runner do env native: Unity normal; para o suite test_emulador, sobe a ECU virtual Python.

O emulador roda em modo kline (sem o '!' da ponte do Nano) numa porta livre,
passada ao binário de teste pela variável EMU_PORTA.
"""
import os
import subprocess
import sys
from pathlib import Path

from platformio.public import UnityTestRunner

RAIZ = Path(__file__).resolve().parents[2]  # Hondash-BR/


class CustomTestRunner(UnityTestRunner):
    emulador = None

    def setup(self):
        if self.test_suite.test_name != "test_emulador":
            return
        python = os.environ.get("EMU_PYTHON", sys.executable)
        self.emulador = subprocess.Popen(
            [python, "-m", "emulador", "--porta", "0", "--modo", "kline", "--cenario", "marcha_lenta"],
            cwd=RAIZ, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
        linha = self.emulador.stdout.readline().strip()
        if not linha.startswith("PORTA="):
            self.teardown()
            raise RuntimeError(f"emulador não subiu (saída: {linha!r}); confira o venv com pyserial")
        os.environ["EMU_PORTA"] = linha.split("=", 1)[1]

    def teardown(self):
        if self.emulador:
            self.emulador.kill()
            self.emulador.wait(timeout=5)
            self.emulador = None
        os.environ.pop("EMU_PORTA", None)
