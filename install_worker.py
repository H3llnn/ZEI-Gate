"""Bootstrap a new Worker from Gate main and its pinned runtime versions."""
import io
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys
import tarfile
import tempfile
from urllib.request import Request, urlopen

PACKAGES = {'ZEI-Gate': 'subgate', 'ZEI-ForceSubs': 'zei_forcesubs',
            'ZEI-Payment': 'zei_payment', 'ZEI-Userbot': 'zei_userbot'}
SHA = re.compile(r'[0-9a-f]{40}')
LIMIT = 32 * 1024 * 1024


def download(url, limit):
    request = Request(url, headers={'User-Agent': 'ZEI-Worker-Installer'})
    with urlopen(request, timeout=60) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Source download exceeds size limit.')
    return data


def extract(stage, repo, revision):
    if repo not in PACKAGES or not SHA.fullmatch(revision):
        raise ValueError('Invalid runtime version.')
    payload = download(f'https://codeload.github.com/H3llnn/{repo}/tar.gz/{revision}', 8 * 1024 * 1024)
    total = 0
    with tarfile.open(fileobj=io.BytesIO(payload), mode='r:gz') as archive:
        for member in archive.getmembers():
            relative = Path(*Path(member.name).parts[1:])
            if not relative.parts or not member.isfile():
                continue
            package = relative.parts[0] == PACKAGES[repo]
            entry = repo == 'ZEI-Gate' and relative.as_posix() in ('main.py', 'requirements.txt', 'runtime-versions.json')
            notice = relative.as_posix() in ('LICENSE', 'THIRD_PARTY_NOTICES.md', 'USERBOT-NOTICES.md')
            if not (package or entry or notice):
                continue
            target = stage/('licenses/'+repo+'/'+relative.as_posix() if notice else relative)
            target = target.resolve()
            if not target.is_relative_to(stage.resolve()) or member.size < 0:
                raise ValueError('Unsafe source archive path.')
            total += member.size
            if total > LIMIT:
                raise ValueError('Unpacked source exceeds size limit.')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.extractfile(member).read())


def install(root):
    marker = root/'.worker-runtime-installed'
    if marker.exists():
        if not (root/'main.py').is_file():
            raise ValueError('Installed Worker entry point is missing; restore its backup.')
        return
    from dotenv import dotenv_values
    config = dotenv_values(root/'config.env')
    if config.get('ZEI_MODE') != 'worker' or not config.get('WORKER_ENROLL_CODE'):
        raise ValueError('Isi config.env Worker dan kode pemasangan dari bot induk terlebih dahulu.')
    directory = Path(config.get('DATA_DIR') or './data')
    if not directory.is_absolute():
        directory = root/directory
    if directory.exists() and any(directory.iterdir()):
        raise ValueError('Data sudah ada. Gunakan migrasi atau pemulihan, bukan pemasangan baru.')
    revision = json.loads(download('https://api.github.com/repos/H3llnn/ZEI-Gate/commits/main', 1024 * 1024))['sha']
    if not isinstance(revision, str) or not SHA.fullmatch(revision):
        raise ValueError('Invalid Gate revision.')
    with tempfile.TemporaryDirectory(dir=root, prefix='.zei-stage-') as folder:
        stage = Path(folder)
        extract(stage, 'ZEI-Gate', revision)
        versions = json.loads((stage/'runtime-versions.json').read_text(encoding='utf-8'))
        if set(versions) != set(PACKAGES)-{'ZEI-Gate'}:
            raise ValueError('Incomplete runtime version manifest.')
        for repo, sha in versions.items():
            extract(stage, repo, sha)
        for name in ('main.py', 'subgate/worker.py', 'zei_forcesubs/child_ui.py',
                     'zei_payment/payment_ui.py', 'zei_userbot/runtime.py'):
            if not (stage/name).is_file():
                raise ValueError('Incomplete runtime sources.')
        for source in stage.rglob('*.py'):
            compile(source.read_bytes(), str(source.relative_to(stage)), 'exec')
        subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', str(stage/'requirements.txt')], check=True)
        for source in stage.rglob('*'):
            if source.is_file():
                target = root/source.relative_to(stage)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
    marker.write_text(json.dumps({'ZEI-Gate': revision, **versions}), encoding='utf-8')
    print('ZEI Worker siap. Menghubungkan ke bot induk…', flush=True)


def main():
    root = Path(__file__).resolve().parent
    os.chdir(root)
    # A fresh Python host needs dotenv before it can read config.env.
    try:
        import dotenv
    except ImportError:
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'python-dotenv==1.2.4'], check=True)
    install(root)
    runpy.run_path(str(root/'main.py'), run_name='__main__')


if __name__ == '__main__':
    main()
