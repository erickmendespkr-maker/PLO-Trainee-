"""Synthetic-only tests for a portable offline multi-batch ZIP."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

import offline_session_portable_bundle as portable
import test_offline_session_batch_timeline as fixture_module


class PortableTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        fixture = fixture_module.TimelineTests('test_two_batches_four_tables_and_verify')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.session = fixture.root
        self.fixture = fixture
        fixture.run_timeline()
        self.zip = self.root/'session.zip'

    def export(self):
        return portable.export(self.session, self.zip)

    def rewrite(self, changes, target=None):
        target = target or self.root/'changed.zip'
        with zipfile.ZipFile(self.zip) as source, zipfile.ZipFile(target, 'w') as out:
            for item in source.infolist():
                raw = source.read(item.filename)
                out.writestr(item, changes.get(item.filename, raw))
        return target

    def test_export_verify_open_four_tables_two_batches(self):
        mf = self.export()
        self.assertEqual((mf['hands'], mf['completed_batches'], mf['total_batches']), (102,2,2))
        self.assertFalse(mf['ocr_verified'])
        self.assertTrue(portable.verify(self.zip)['complete'])
        dest = self.root/'opened'
        portable.open_bundle(self.zip, dest)
        self.assertIn('H0101', (dest/'workspace/batch_timeline.html').read_text())
        self.assertTrue(portable.timeline.process(dest/'plan.json', dest/'annotations.json',
                           dest/'batches', dest/'workspace', verify=True)['verified'])
        self.assertFalse((dest/'original_video.mp4').exists())

    def test_export_with_verified_ffmpeg_clip(self):
        self.fixture.add_clip()
        (self.session/'workspace/batch_timeline.html').unlink()
        self.fixture.run_timeline()
        self.export()
        portable.verify(self.zip)
        self.assertIn('workspace/clips/batch-0001/H0000.mp4',
                      portable.verify(self.zip)['files'])

    def test_refuse_overwrite(self):
        self.export()
        with self.assertRaisesRegex(ValueError, 'new ZIP'):
            self.export()
        dest = self.root/'opened'
        portable.open_bundle(self.zip, dest)
        with self.assertRaisesRegex(ValueError, 'new directory'):
            portable.open_bundle(self.zip, dest)

    def test_reject_modified_mp4_even_if_inventory_hash_updated(self):
        self.fixture.add_clip()
        (self.session/'workspace/batch_timeline.html').unlink()
        self.fixture.run_timeline()
        self.export()
        with zipfile.ZipFile(self.zip) as z:
            mf = json.loads(z.read(portable.MANIFEST))
        name = 'workspace/clips/batch-0001/H0000.mp4'
        with zipfile.ZipFile(self.zip) as z:
            bad = z.read(name)+b'forged'
        mf['files'][name] = {'size_bytes':len(bad), 'sha256':portable.digest(bad)}
        changed = self.rewrite({name:bad, portable.MANIFEST:portable.canonical(mf)})
        with self.assertRaises(ValueError):
            portable.verify(changed)

    def test_reject_modified_history_even_if_hash_updated(self):
        self.export()
        name = 'workspace/results/session_history.json'
        with zipfile.ZipFile(self.zip) as z:
            mf = json.loads(z.read(portable.MANIFEST))
            data = json.loads(z.read(name))
        data['hands'][0]['table_id'] = 'FAKE'
        bad = portable.canonical(data)
        mf['files'][name] = {'size_bytes':len(bad), 'sha256':portable.digest(bad)}
        changed = self.rewrite({name:bad, portable.MANIFEST:portable.canonical(mf)})
        with self.assertRaises(ValueError):
            portable.verify(changed)

    def test_reject_modified_math_without_updated_hash(self):
        self.export()
        changed = self.rewrite({'workspace/results/batch-0001/hands/H0000.json':b'{}'})
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            portable.verify(changed)

    def test_reject_path_traversal(self):
        self.export()
        with zipfile.ZipFile(self.zip, 'a') as z:
            z.writestr('../escape.txt', 'bad')
        with self.assertRaisesRegex(ValueError, 'unsafe archive'):
            portable.verify(self.zip)
        self.assertFalse((self.root/'escape.txt').exists())

    def test_reject_duplicate_member(self):
        self.export()
        with zipfile.ZipFile(self.zip, 'a') as z:
            z.writestr('plan.json', '{}')
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            portable.verify(self.zip)

    def test_reject_unexpected_source_file(self):
        (self.session/'workspace/rogue.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'unexpected or missing'):
            self.export()
        self.assertFalse(self.zip.exists())

    def test_reject_source_symlink(self):
        target = self.root/'target.txt'
        target.write_text('outside')
        try:
            (self.session/'workspace/linked.txt').symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest('symlinks unavailable')
        with self.assertRaisesRegex(ValueError, 'linked'):
            self.export()

    def test_reject_tampered_timeline_with_updated_inventory(self):
        self.export()
        name = 'workspace/batch_timeline.html'
        with zipfile.ZipFile(self.zip) as z:
            mf = json.loads(z.read(portable.MANIFEST))
            html = z.read(name)
        bad = html+b'<!-- injected -->'
        mf['files'][name] = {'size_bytes':len(bad), 'sha256':portable.digest(bad)}
        changed = self.rewrite({name:bad, portable.MANIFEST:portable.canonical(mf)})
        with self.assertRaisesRegex(ValueError, 'timeline differs'):
            portable.verify(changed)

    def test_partial_history_export_and_open(self):
        partial = self.root/'partial_session'
        shutil.copytree(self.session, partial)
        # Drop last result batch, regenerate current prefix and timeline.
        shutil.rmtree(partial/'workspace/results/batch-0002')
        (partial/'workspace/results/session_history.json').unlink()
        (partial/'workspace/batch_timeline.html').unlink()
        from offline_session_batch_history import process as hist
        hist(partial/'plan.json', partial/'annotations.json', partial/'batches',
             partial/'workspace/results', max_new=0)
        portable.timeline.process(partial/'plan.json', partial/'annotations.json',
                                  partial/'batches', partial/'workspace')
        mf = portable.export(partial, self.zip)
        self.assertEqual((mf['hands'], mf['completed_batches'], mf['total_batches']), (100,1,2))
        self.assertFalse(portable.verify(self.zip)['complete'])

    def test_305_hands_four_tables_four_batches(self):
        import offline_session_batch_planner as planner
        import offline_session_batch_history as history
        plan = json.loads((self.session/'plan.json').read_text())
        ann = json.loads((self.session/'annotations.json').read_text())
        for n in range(102, 305):
            plan['clips'].append({'hand_id': f'H{n:04d}',
                'table_id': f'T{n%4+1}', 'start_seconds': (n//4)*5,
                'end_seconds': (n//4)*5+4,
                'review_basis': 'human_declared_boundaries_not_automatic_detection'})
        (self.session/'plan.json').write_bytes(planner.encode(plan))
        ann['source_plan_sha256'] = planner.q.digest(self.session/'plan.json')
        (self.session/'annotations.json').write_bytes(planner.encode(ann))
        shutil.rmtree(self.session/'batches')
        shutil.rmtree(self.session/'workspace/results')
        (self.session/'workspace/batch_timeline.html').unlink()
        planner.process(self.session/'plan.json', self.session/'annotations.json',
                        self.session/'batches')
        history.process(self.session/'plan.json', self.session/'annotations.json',
                        self.session/'batches', self.session/'workspace/results', max_new=10)
        portable.timeline.process(self.session/'plan.json', self.session/'annotations.json',
                                  self.session/'batches', self.session/'workspace')
        manifest = self.export()
        self.assertEqual((manifest['hands'], manifest['total_batches']), (305,4))
        self.assertTrue(portable.verify(self.zip)['complete'])

    def test_failed_open_does_not_publish_destination(self):
        self.export()
        name = 'workspace/batch_timeline.html'
        corrupted = self.rewrite({name: b'bad'})
        dest = self.root/'unopened'
        with self.assertRaises(ValueError):
            portable.open_bundle(corrupted, dest)
        self.assertFalse(dest.exists())

    def test_reject_wrong_provenance_claim_even_if_manifest_rewritten(self):
        self.export()
        with zipfile.ZipFile(self.zip) as z:
            mf = json.loads(z.read(portable.MANIFEST))
        mf['ocr_verified'] = True
        changed = self.rewrite({portable.MANIFEST:portable.canonical(mf)})
        with self.assertRaisesRegex(ValueError, 'provenance'):
            portable.verify(changed)

    def test_reject_symlink_in_archive(self):
        self.export()
        with zipfile.ZipFile(self.zip) as z:
            mf = json.loads(z.read(portable.MANIFEST))
            info = z.getinfo('plan.json')
            data = z.read('plan.json')
        target = self.root/'symlink.zip'
        with zipfile.ZipFile(self.zip) as src, zipfile.ZipFile(target, 'w') as out:
            for item in src.infolist():
                if item.filename == 'plan.json':
                    item = copy.copy(item)
                    item.create_system = 3
                    item.external_attr = (0o120777 << 16)
                out.writestr(item, src.read(item.filename))
        with self.assertRaisesRegex(ValueError, 'unsafe archive entry'):
            portable.verify(target)


if __name__ == '__main__':
    unittest.main()
