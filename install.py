"""Install both sibling projects without reading or replacing private config/data."""
import os
from pathlib import Path
import subprocess
import sys
import venv


def main():
    root = Path(__file__).resolve().parent
    userbot = root.parent / 'ZEI-Userbot'
    if not (userbot / 'pyproject.toml').is_file():
        raise SystemExit('Letakkan folder ZEI-Gate dan ZEI-Userbot berdampingan, lalu coba lagi.')
    if sys.version_info < (3,12): raise SystemExit('Gunakan Python 3.12 atau lebih baru.')
    env = root / '.venv'
    if not env.exists(): venv.create(env, with_pip=True)
    python = env / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(root / 'requirements.txt'), str(userbot)],check=True)
    print('Instalasi selesai. Atur config.env milikmu, lalu jalankan RUN.cmd (Windows) atau .venv/bin/python main.py (Linux).')


if __name__ == '__main__': main()
