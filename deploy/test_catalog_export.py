"""Public source-registry metadata only; no corpus, providers or external Git required."""
import csv
import io
import json
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch


class CatalogExportTests(unittest.TestCase):
    def test_registry_identity_zero_null_labels_and_dates_survive_export(self):
        fields = ['id','name','domain','kind','flank','tier','independence_group',
                  'allsides','mbfc','adfontes','audience','allsides_label',
                  'allsides_source_url','mbfc_source_url','adfontes_source_url',
                  'audience_source_url','ratings_checked_at','audience_as_of']
        row = dict.fromkeys(fields, '')
        row.update(id='TEST-registry',name='TEST source',domain='example.org',
                   kind='outlet',flank='center',tier='minor',independence_group='TEST-group',
                   allsides='0',allsides_label='Center',
                   allsides_source_url='https://example.org/rating',
                   audience='10',audience_source_url='https://example.org/audience',
                   ratings_checked_at='2026-10-24',audience_as_of='2026-09-01')
        data=io.StringIO();writer=csv.DictWriter(data,fields);writer.writeheader();writer.writerow(row)
        def git(args, **kwargs):
            if args[1] == 'rev-parse': return 'a'*40+'\n'
            return "TOPICS = {'TEST': {'name':'TEST topic'}}" if args[-1].endswith('run.py') else data.getvalue()
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'catalog.json'
            with patch('sys.argv',['export-catalog.py','TEST-ref',str(target)]),patch('subprocess.check_output',side_effect=git):
                runpy.run_path(str(Path(__file__).with_name('export-catalog.py')),run_name='__main__')
            out=json.loads(target.read_text())['sources'][0]
            self.assertEqual(out['id'],row['id']);self.assertEqual(out['allsides'],0)
            self.assertIsNone(out['mbfc']);self.assertIsNone(out['rating_labels']['mbfc'])
            self.assertEqual(out['rating_labels']['allsides'],'Center')
            self.assertEqual(out['rating_provenance']['allsides'],row['allsides_source_url'])
            self.assertEqual(out['audience_source_url'],row['audience_source_url'])
            self.assertEqual(out['audience_as_of'],'2026-09-01')
            self.assertEqual(out['ratings_checked_at'],'2026-10-24')
