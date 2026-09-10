from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from autospine_workbench.automation.asset_library import AssetLibrary
from autospine_workbench.automation.asset_source import upload_sources
from autospine_workbench.automation.storage_io import publish_document


class AssetSourceTests(unittest.TestCase):
    def journal(self, root, job, digest='a'*64, name='Original.psd', **changes):
        folder=root/'jobs/psd-import-v1'/job; folder.mkdir(parents=True)
        request=dict(job_id=job, source_sha256=digest, name=name)
        result=dict(job_id=job, status='succeeded', step='complete', authority='none', project_id='imported-'+digest)
        result.update(changes)
        for filename,doc in [('request.json',request),('result.json',result)]:
            publish_document(folder/filename,doc,staging=folder/'.staging')

    def test_rename_preserves_manifest_filename_and_duplicate_names_are_explicit(self):
        with TemporaryDirectory() as directory:
            root=Path(directory); project='imported-'+'a'*64
            self.journal(root,'import-'+'1'*32)
            self.journal(root,'import-'+'2'*32,name='另一文件名.psd')
            store=SimpleNamespace(state_root=root,list_projects=lambda:[dict(id=project,name='Display',revision=0)],get_project=lambda _: {})
            library=AssetLibrary(store); library.change(project,dict(action='rename',expected_revision=0,name='新显示名'))
            row=library.list()[0]
            self.assertEqual(row['name'],'新显示名')
            self.assertEqual(row['source']['file_names'],['Original.psd','另一文件名.psd'])
            self.assertEqual(row['source']['source_sha256'],'a'*64)
            self.assertNotIn(str(root),str(row['source']))

    def test_bad_failed_and_cross_source_records_do_not_establish_filename(self):
        with TemporaryDirectory() as directory:
            root=Path(directory); project='imported-'+'a'*64
            self.journal(root,'import-'+'1'*32,status='failed')
            self.journal(root,'import-'+'2'*32,project_id='imported-'+'b'*64)
            self.journal(root,'import-'+'3'*32,name='C:\\private\\source.psd')
            rows=upload_sources(root,[project,'legacy'])
            self.assertEqual(rows[project],dict(kind='unavailable',file_names=[]))
            self.assertEqual(rows['legacy'],dict(kind='audit',file_names=[]))

    def test_missing_journal_keeps_legacy_catalog_available(self):
        with TemporaryDirectory() as directory:
            self.assertEqual(upload_sources(Path(directory),['legacy'])['legacy']['kind'],'audit')
