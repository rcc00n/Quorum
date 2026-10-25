"""Catalog metadata and unchanged fictional-contract mapping; zero provider calls."""
import copy,json,tempfile,os
from pathlib import Path
from unittest.mock import patch
from django.test import SimpleTestCase
from .catalog_sources import bind_sources,validate_sources
from .integration import CatalogAdapter
from .reasoning_preview import SAMPLE,present_reasoning,load_preview

def source(id='ap',domain='apnews.com'):
    return dict(id=id,name='TEST registry',domain=domain,allsides=0,mbfc=None,adfontes=None,audience=None,rating_provenance=dict(allsides='https://www.allsides.com/news-source/associated-press-media-bias',mbfc=None,adfontes=None),rating_labels=dict(allsides='TEST label',mbfc=None,adfontes=None),ratings_checked_at='2026-10-24',audience_source_url=None,audience_as_of=None)
class CatalogPreviewTests(SimpleTestCase):
    def test_exact_identity_no_name_guess_and_unmatched_explicit_no_domain_fallback(self):
        p={'stories':[{'claims':[{'evidence':[{'url':'https://other.example/article','source_id':'ap'}]}]}]}
        resolve=bind_sources(p,[source()]);self.assertEqual(resolve({'url':'https://other.example/article'})['id'],'ap')
        self.assertIsNone(resolve({'url':'https://unknown.example/article','title':'TEST registry'}))
        p['stories'][0]['claims'][0]['evidence'][0].update(url='https://apnews.com/article',source_id='unknown')
        self.assertIsNone(bind_sources(p,[source()])({'url':'https://apnews.com/article'}))
    def test_ambiguous_id_and_domain_fail(self):
        with self.assertRaises(ValueError):validate_sources([source(),source()])
        p={'stories':[{'claims':[{'evidence':[{'url':'https://example.org/a','source_id':'ap'},{'url':'https://example.org/a','source_id':'other'}]}]}]}
        with self.assertRaises(ValueError):bind_sources(p,[source()])({'url':'https://example.org/a'})
        with self.assertRaises(ValueError):bind_sources({'stories':[]},[source(),source('other')])({'url':'https://apnews.com/a'})
    def test_exact_hostname_only(self):
        resolve=bind_sources({'stories':[]},[source()])
        self.assertEqual(resolve({'url':'https://www.apnews.com/a'})['id'],'ap')
        self.assertIsNone(resolve({'url':'https://apnews.com.evil.example/a'}))
    def test_unsafe_provenance_and_bad_dates_fail(self):
        for bad in ['http://127.0.0.1/private','javascript:alert(1)']:
            x=source();x['rating_provenance']['allsides']=bad
            with self.assertRaises(ValueError):validate_sources([x])
        x=source();x['ratings_checked_at']='yesterday'
        with self.assertRaises(ValueError):validate_sources([x])
    def test_original_reasoning_is_unchanged_and_real_zero_not_missing(self):
        raw=SAMPLE.read_bytes();p=json.loads(raw);url=p['stories'][0]['sources'][0]['url'];x=source(domain=__import__('urllib.parse',fromlist=['urlsplit']).urlsplit(url).hostname)
        # Explicit existing fixture source refs bind this URL; use its declared id when supplied.
        ids={e.get('source_id') for s in p['stories'] for c in s['claims'] for e in c['evidence'] if e['url']==url and e.get('source_id')}
        if len(ids)==1:x['id']=next(iter(ids))
        catalog={'sources':[x],'catalog_revision':'TEST-registry'}
        result=present_reasoning(raw,catalog=catalog)
        self.assertEqual(result['reasoning'],p);self.assertEqual(result['catalog_revision'],'TEST-registry');self.assertEqual(result['events'][0]['sources'][0]['allsides'],0);self.assertIsNone(result['sources'][0]['mbfc'])
    def test_catalog_fields_preserved_but_private_fields_stripped(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'catalog.json';x=source();x['private']='NEVER_EXPORT';f.write_text(json.dumps({'revision':'TEST','topics':[],'sources':[x]}))
            with patch.dict(os.environ,QUORUM_CATALOG_PATH=str(f)):
                result=CatalogAdapter().snapshot();s=result['sources'][0]
                self.assertEqual(s['rating_labels'],x['rating_labels']);self.assertEqual(s['ratings_checked_at'],'2026-10-24');self.assertIsNone(s['audience_as_of']);self.assertNotIn('private',s)
                f.write_text('{}')
                with self.assertRaises(ValueError):load_preview()
