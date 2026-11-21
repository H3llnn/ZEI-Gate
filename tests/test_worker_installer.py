import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import install_worker as installer


def archive(files):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w:gz') as tar:
        for name, text in files.items():
            data = text.encode()
            info = tarfile.TarInfo('source/'+name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return output.getvalue()


class WorkerInstallerTests(unittest.TestCase):
    def test_new_server_uses_one_gate_revision_and_pinned_runtimes(self):
        gate = 'a'*40
        versions = {repo: str(i)*40 for i, repo in enumerate(list(installer.PACKAGES)[1:], 1)}
        sources = {
            'ZEI-Gate': {'subgate/worker.py': 'pass', 'main.py': 'pass',
                         'requirements.txt': '', 'runtime-versions.json': json.dumps(versions),
                         'config.env': 'DO_NOT_INSTALL=1', 'LICENSE': 'license'},
            'ZEI-ForceSubs': {'zei_forcesubs/child_ui.py': 'pass'},
            'ZEI-Payment': {'zei_payment/payment_ui.py': 'pass'},
            'ZEI-Userbot': {'zei_userbot/runtime.py': 'pass'},
        }
        urls = []
        def download(url, limit):
            urls.append(url)
            if 'commits/main' in url:
                return json.dumps({'sha': gate}).encode()
            repo = url.split('/')[4]
            self.assertTrue(url.endswith(gate if repo=='ZEI-Gate' else versions[repo]))
            return archive(sources[repo])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = 'ZEI_MODE=worker\nWORKER_ENROLL_CODE=test\n'
            (root/'config.env').write_text(config)
            with patch.object(installer, 'download', side_effect=download), patch.object(installer.subprocess, 'run') as pip:
                installer.install(root)
                self.assertEqual((root/'config.env').read_text(), config)
                self.assertEqual(json.loads((root/'.worker-runtime-installed').read_text()), {'ZEI-Gate':gate, **versions})
                self.assertTrue((root/'licenses/ZEI-Gate/LICENSE').exists())
                installer.install(root)
                self.assertEqual(len(urls), 5)
                pip.assert_called_once()

    def test_existing_data_is_not_reinstalled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'config.env').write_text('ZEI_MODE=worker\nWORKER_ENROLL_CODE=test\n')
            (root/'data').mkdir()
            (root/'data/subgate.sqlite').write_bytes(b'private')
            with patch.object(installer, 'download') as network:
                with self.assertRaisesRegex(ValueError, 'Data sudah ada'):
                    installer.install(root)
                network.assert_not_called()
            self.assertEqual((root/'data/subgate.sqlite').read_bytes(), b'private')

    def test_archive_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(installer, 'download', return_value=archive({'subgate/../../escape.py':'pass'})):
                with self.assertRaisesRegex(ValueError, 'Unsafe'):
                    installer.extract(Path(directory), 'ZEI-Gate', 'a'*40)

    def test_incomplete_install_does_not_create_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'.worker-runtime-installed').write_text('installed')
            with self.assertRaisesRegex(ValueError, 'entry point'):
                installer.install(root)
