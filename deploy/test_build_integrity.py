"""Temporary filesystem/index checks only; never packages or modifies a real release."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from build_integrity import web_digest, artifact_digest, validate_build, write_receipt
spec=importlib.util.spec_from_file_location('package_release',Path(__file__).with_name('package-release.py'))
package=importlib.util.module_from_spec(spec);spec.loader.exec_module(package)

class BuildIntegrityTests(unittest.TestCase):
    def test_receipt_rejects_missing_stale_or_incomplete_build(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'web').mkdir();(root/'web/page.tsx').write_text('TEST source')
            build=root/'build';build.mkdir()
            with self.assertRaises(RuntimeError):validate_build(root,build)
            receipt=dict(version=2,web_source_sha256=web_digest(root),artifact_sha256='0'*64,build_revision='a'*40)
            (build/'.quorum-build.json').write_text(json.dumps(receipt))
            with self.assertRaises(RuntimeError):validate_build(root,build)
            for name in ('standalone','static'):(build/'.next'/name).mkdir(parents=True)
            (build/'.next/standalone/server.js').write_text('TEST server')
            receipt['artifact_sha256']=artifact_digest(build)
            (build/'.quorum-build.json').write_text(json.dumps(receipt))
            self.assertEqual(validate_build(root,build),receipt)
            (root/'web/page.tsx').write_text('TEST changed source')
            with self.assertRaises(RuntimeError):write_receipt(root,build,receipt['web_source_sha256'])
            with self.assertRaises(RuntimeError):validate_build(root,build)

    def test_export_excludes_untracked_private_artifacts_and_rejects_tracked_ones(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);repo=root/'repo';repo.mkdir();(repo/'backend').mkdir()
            subprocess.run(['git','init','-q',str(repo)],check=True)
            (repo/'backend/manage.py').write_text('# TEST source')
            (repo/'backend/.env.example').write_text('TEST placeholder only')
            subprocess.run(['git','add','backend/manage.py','backend/.env.example'],cwd=repo,check=True)
            (repo/'backend/private.sqlite').write_text('TEST private data')
            (repo/'backend/.env').write_text('TEST private config')
            release=root/'release'
            package.copy_portal_sources(repo,release)
            self.assertEqual(list((release/'backend').iterdir()),[release/'backend/manage.py'])
            subprocess.run(['git','add','backend/private.sqlite'],cwd=repo,check=True)
            with self.assertRaises(RuntimeError):package.copy_portal_sources(repo,root/'blocked')

    def test_web_source_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'web').mkdir();(root/'outside').write_text('TEST private')
            (root/'web/link').symlink_to(root/'outside')
            with self.assertRaises(RuntimeError):web_digest(root)


    def test_output_tampering_and_linked_artifacts_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'web').mkdir();(root/'web/page.tsx').write_text('TEST source')
            build=root/'build';server=build/'.next/standalone/server.js'
            server.parent.mkdir(parents=True);server.write_text('TEST server')
            assets=build/'.next/static';assets.mkdir();(assets/'chunk.js').write_text('TEST chunk')
            receipt=dict(version=2,web_source_sha256=web_digest(root),artifact_sha256=artifact_digest(build),build_revision='a'*40)
            marker=build/'.quorum-build.json';marker.write_text(json.dumps(receipt))
            self.assertEqual(validate_build(root,build),receipt)
            server.write_text('TEST changed server')
            with self.assertRaises(RuntimeError):validate_build(root,build)
            server.write_text('TEST server');(assets/'chunk.js').unlink()
            with self.assertRaises(RuntimeError):validate_build(root,build)
            (assets/'chunk.js').write_text('TEST chunk');(assets/'extra.js').write_text('TEST extra')
            with self.assertRaises(RuntimeError):validate_build(root,build)
            (assets/'extra.js').unlink();server.unlink();(root/'outside.js').write_text('TEST server')
            server.symlink_to(root/'outside.js')
            with self.assertRaises(RuntimeError):validate_build(root,build)

    def test_legacy_coercive_and_unknown_receipts_require_rebuild(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'web').mkdir();build=root/'build';build.mkdir()
            for receipt in (dict(version=True),dict(version=1),dict(version=2,extra='TEST'),[]):
                (build/'.quorum-build.json').write_text(json.dumps(receipt))
                with self.assertRaises(RuntimeError):validate_build(root,build)
