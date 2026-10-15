import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from corpus_v10 import acquire, attach_editor, audit, normalize_captions, prepare_jobs, write_json
from jev_credentials_v10 import load_jev_env
from oracle_dataset_v10 import build_dataset, load_bundle
from policy_gate_v10 import assess
from research_evidence_v10 import json_hash, verify_artifacts


def fixture(talk="one", group=None):
    return {"talk_id": talk, "context": {}, "transcript": [
        {"start_s": 0, "end_s": 10, "text": f"A causal explanation for {talk}."}],
        "editors": [{"name":"a", "family":"model_a", "version":"v1", "mode":"oracle", "shape":"generic",
                     "events":[{"start_s":0,"end_s":5,"function":"explain","representation":"flow","confidence":.9}]}],
        "metadata":{"split_group":group or talk, "rights_status":"reviewed", "rights_basis":"test fixture",
                    "source_uri":"https://example.test/talk", "context_reviewed":True, "independent_editors":True}}


class CorpusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
    def tearDown(self):
        self.temp.cleanup()
    def bundle(self, talk="one", group=None):
        p = self.root / f"{talk}.json"
        write_json(p, fixture(talk,group))
        return p

    def test_source_group_is_never_split_and_duplicates_rejected(self):
        paths = [self.bundle("a","shared"),self.bundle("b","shared"),self.bundle("c","other")]
        bundles = [load_bundle(p) for p in paths]
        d = build_dataset(bundles)
        split_for = {r['talk_id']:s for s,rows in d['splits'].items() for r in rows}
        self.assertEqual(split_for['a'],split_for['b'])
        self.assertNotEqual(split_for['a'],split_for['c'])
        with self.assertRaises(ValueError):build_dataset([bundles[0],bundles[0]])
        duplicate = fixture("d");duplicate['transcript']=fixture('a')['transcript']
        write_json(self.root/'d.json',duplicate)
        with self.assertRaises(ValueError):build_dataset([bundles[0],load_bundle(self.root/'d.json')])

    def test_independence_and_rights_cannot_be_inferred_from_count(self):
        p=self.bundle();b=json.loads(p.read_text());b['editors'].append({**b['editors'][0],'name':'second'})
        write_json(p,b)
        self.assertEqual(audit([p])['eligible_talks'],0)
        b['editors'][1]['family']='model_b';write_json(p,b)
        self.assertEqual(audit([p])['eligible_talks'],1)
        b['metadata']['rights_status']='pending';write_json(p,b)
        self.assertEqual(audit([p])['eligible_talks'],0)

    def test_job_import_preserves_provenance_and_rejects_stale_context(self):
        p=self.bundle();jobs=self.root/'jobs'
        self.assertEqual(prepare_jobs([p],jobs,['model_a','model_b']),2)
        trace=self.root/'trace.json';write_json(trace,fixture()['editors'][0]['events'])
        job=jobs/'one/model_b/job.json'
        e=attach_editor(p,trace,job,name='b',version='exact-v2')
        self.assertEqual(e['family'],'model_b');self.assertTrue(e['trace_sha256'])
        with self.assertRaises(ValueError):attach_editor(p,trace,job,name='b',version='exact-v2')
        b=json.loads(p.read_text());b['context']={'has_dataset':True};write_json(p,b)
        with self.assertRaises(ValueError):attach_editor(p,trace,job,name='c',version='v3')

    def test_acquisition_normalizes_real_reader_shape_and_preserves_annotations(self):
        url='https://svs.gsfc.nasa.gov/test.en_US.srt'
        source={'id':1,'title':'test','media_groups':[{'media_type':'Captions','url':url}]}
        seed=self.root/'seed.json'
        raw=('1\n00:00:00,000 --> 00:04:00,000\n'+('explanation '*500)+'\n').encode()
        from corpus_v10 import digest
        write_json(seed,{'records':[{'page_id':1,'caption_url':url,'caption_sha256':digest(raw)}]})
        def fake_fetch(link):return json.dumps(source).encode() if '/api/' in link else raw
        with patch('corpus_v10.fetch',side_effect=fake_fetch):
            result=acquire(self.root/'out',limit=1,seed_path=seed)
            self.assertEqual(result['acquired'],1)
            bundle=self.root/'out'/result['records'][0]['talk_id']/'bundle.json'
            b=json.loads(bundle.read_text());self.assertEqual(b['transcript'][0]['end_s'],240)
            b['editors']=[{'name':'preserved'}];write_json(bundle,b)
            acquire(self.root/'out',limit=1,seed_path=seed)
            self.assertEqual(json.loads(bundle.read_text())['editors'][0]['name'],'preserved')

    def test_zero_cues_logged_overlaps_rejected(self):
        clean,rejected=normalize_captions([{'start':0,'end':0,'text':'bad'},{'start':1,'end':2,'text':'ok'}])
        self.assertEqual(len(clean),1);self.assertEqual(len(rejected),1)
        with self.assertRaises(ValueError):normalize_captions([{'start':0,'end':2,'text':'a'},{'start':1,'end':3,'text':'b'}])

    def test_promotion_rejects_unreviewed_or_pipeline_only_corpus(self):
        stats={'talk_count':100,'example_count':600,'empirical_eligible_talks':0,'split_group_count':2,'min_consensus_votes':2}
        evaluation={'examples':200,'coverage':1,'selective_accuracy':1}
        self.assertFalse(assess(stats,evaluation,non_fixture_talks=100,browser_rehearsal_ok=True).eligible)
        stats.update(empirical_eligible_talks=100,pipeline_only=True)
        self.assertFalse(assess(stats,evaluation,non_fixture_talks=100,browser_rehearsal_ok=True).eligible)
        stats['pipeline_only']=False
        self.assertTrue(assess(stats,evaluation,non_fixture_talks=100,browser_rehearsal_ok=True).eligible)
        evaluation['coverage']=float('nan')
        self.assertFalse(assess(stats,evaluation,non_fixture_talks=100,browser_rehearsal_ok=True).eligible)

    def test_artifacts_reproduce_and_reject_changed_sources_or_metrics(self):
        from hashlib import sha256
        from representation_policy_v10 import OracleRepresentationPolicy, evaluate_policy
        paths=[self.bundle('a'),self.bundle('b')]
        d=build_dataset([load_bundle(p) for p in paths])
        quality=audit(paths)
        d['stats'].update(empirical_eligible_talks=quality['eligible_talks'],pipeline_only=True,
                          non_fixture_talks=quality['non_fixture_talks'])
        d['source_bundles']=[{'path':str(p),'sha256':sha256(p.read_bytes()).hexdigest()} for p in paths]
        d['dataset_sha256']=json_hash(d)
        policy=OracleRepresentationPolicy.fit(d['splits']['train'])
        e={**evaluate_policy(policy,d['splits']['eval']), 'dataset_sha256':d['dataset_sha256'],
           'policy_sha256':json_hash(policy.artifact)}
        self.assertEqual(verify_artifacts(d,e,base_dir=self.root),[])
        e['coverage']=.12345
        self.assertTrue(any('rows/metrics' in x for x in verify_artifacts(d,e,base_dir=self.root)))
        paths[0].write_text('{}')
        self.assertTrue(any('source bundle' in x for x in verify_artifacts(d,e,base_dir=self.root)))

    def test_nasa_group_cannot_disagree_with_source_page(self):
        p=self.bundle();b=json.loads(p.read_text())
        b['metadata']['source_uri']='https://svs.gsfc.nasa.gov/31168/'
        b['metadata']['split_group']='different_group';write_json(p,b)
        with self.assertRaises(ValueError):load_bundle(p)


class CredentialTests(unittest.TestCase):
    def test_env_file_is_data_and_environment_wins(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{},clear=True):
            p=Path(directory)/'keys.env'
            p.write_text('export TYPESAFE_API_KEY="test-value" # comment\nUNRELATED_SECRET=ignored\n')
            self.assertTrue(load_jev_env(p));self.assertEqual(os.environ['TYPESAFE_API_KEY'],'test-value')
            self.assertNotIn('UNRELATED_SECRET',os.environ)
            os.environ['TYPESAFE_API_KEY']='existing'
            load_jev_env(p);self.assertEqual(os.environ['TYPESAFE_API_KEY'],'existing')


if __name__=='__main__':unittest.main()
