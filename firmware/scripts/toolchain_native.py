# Compilador do env native.
# Mac/Linux: usa o gcc/clang do sistema (Xcode CLT no Mac), sem mexer em nada.
# Windows sem gcc no PATH: usa o zig (pip install ziglang, no mesmo venv do PlatformIO)
# por trás de gcc.cmd/g++.cmd/ar.cmd/ranlib.cmd gerados em .pio/, para não instalar MinGW no sistema.
# Os wrappers entram só no PATH do build (env["ENV"]); o builder native chama "gcc"/"g++" pelo nome.
import os
import shutil
import sys

Import("env")  # noqa: F821

if sys.platform == "win32":
    env.Append(LIBS=["ws2_32"])  # noqa: F821 - socket do suite test_emulador
    if not shutil.which("gcc"):
        try:
            import ziglang  # noqa: F401
        except ImportError:
            sys.exit("env native no Windows: sem gcc no PATH. Rode: pip install ziglang (no venv do pio)")
        pasta = os.path.join(env.subst("$PROJECT_WORKSPACE_DIR"), "zig-bin")  # noqa: F821
        os.makedirs(pasta, exist_ok=True)
        for nome, sub in (("gcc", "cc"), ("g++", "c++"), ("ar", "ar"), ("ranlib", "ranlib")):
            with open(os.path.join(pasta, f"{nome}.cmd"), "w") as f:
                f.write(f'@"{sys.executable}" -m ziglang {sub} %*\r\n')
        env.PrependENVPath("PATH", pasta)  # noqa: F821
