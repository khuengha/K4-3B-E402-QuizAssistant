"""Merged FE/BE contract checks; fake LLM, isolated storage, no API charges."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from codebase.app import server as api
import pipeline


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.patches = []
        for module, name, value in [
            (api, 'REGISTRY', root / 'registry.json'),
            (api, 'CACHE', root / 'cache'), (api, 'UPLOADS', root / 'uploads'),
            (api, 'TRACE', root / 'trace.log'),
            (pipeline, 'CACHE', root / 'cache'), (pipeline, 'UPLOADS', root / 'uploads'),
            (pipeline, 'TRACE', root / 'trace.log'),
            (api, 'JOBS', {}), (api, 'STORE', api._live.QuizStore()),
        ]:
            p = patch.object(module, name, value); p.start(); self.patches.append(p)
        api.CACHE.mkdir(); api.UPLOADS.mkdir()
        self.client = TestClient(api.APP)

    def tearDown(self):
        self.client.close()
        for p in reversed(self.patches): p.stop()
        self.tmp.cleanup()

    def seed(self, did, name, turn=False):
        source = {'file': name, **({'turn': 'T01-001'} if turn else {'page': 2})}
        node = {'id': 'c1', 'name': 'AI', 'type': 'concept', 'definition': 'Nội dung AI',
                'quotes': ['Nội dung AI'], 'sources': [source], 'evidence': [{'quote': 'Nội dung AI', 'source': source}],
                'confidence': .9, 'aliases': []}
        other = {**copy.deepcopy(node), 'id': 'c2', 'name': 'Token'}
        graph = {'nodes': [node, other], 'edges': [{'source': 'c1', 'target': 'c2', 'type': 'related'}], 'stats': {}}
        (api.CACHE / (did + '.json')).write_text(json.dumps(graph))
        reg = api._load_registry()
        reg['docs'][did] = {'doc_id': did, 'name': name, 'sha': did, 'built_at': 'today', 'n_nodes': 2}
        api._save_registry(reg)
        path = api.UPLOADS / did; path.mkdir()
        (path / 'chunks.json').write_text(json.dumps([{**source, 'text': 'Nội dung AI đầy đủ'}]))
        return graph

    @staticmethod
    def fake_llm(system, user):
        payload = json.loads(user)
        concepts = {n['concept_id']: n for n in payload['concepts']}
        previous = {q['q'] for q in payload.get('existing_questions', [])}
        questions = []
        for slot in payload['requests']:
            n = concepts[slot['concept_id']]
            i = 1
            while f"{n['concept']} nội dung {i}?" in previous:
                i += 1
            text = f"{n['concept']} nội dung {i}?"
            previous.add(text)
            questions.append({**slot, 'q': text, 'evidence_id': n['evidence'][(i-1) % len(n['evidence'])]['evidence_id'],
                'a': ['Một', 'Hai', 'Ba', 'Bốn'], 'correct': 0, 'explain': 'Nội dung AI'})
        return json.dumps({'questions': questions})

    def test_public_assets_and_private_paths(self):
        for path in ['/', '/live.js', '/live.css', '/live.html', '/static/live.js']:
            self.assertEqual(self.client.get(path).status_code, 200, path)
        for path in ['/.env', '/server.py', '/appdata/registry.json']:
            self.assertEqual(self.client.get(path).status_code, 404, path)
        self.assertIn('graph-select', self.client.get('/').text)

    def test_quiz_to_live_transcript_and_refill(self):
        self.seed('doc1', 'lesson.md', turn=True)
        with patch.object(api, 'call_llm', side_effect=self.fake_llm):
            response = self.client.post('/api/quiz', json={'graph_id': 'doc1', 'count': 1, 'topics': ['AI']})
            self.assertEqual(response.status_code, 200, response.text)
            q = response.json()['questions'][0]
            self.assertIsNone(q['page']); self.assertEqual(q['code'], 'T01-001')
            self.assertEqual(q['text'], 'Nội dung AI đầy đủ')
            refill = self.client.post('/api/quiz', json={'graph_id': 'doc1', 'count': 1, 'exclude_concept_ids': [q['concept_id']]})
            self.assertNotEqual(refill.json()['questions'][0]['concept_id'], q['concept_id'])
        q['status'] = 'approved'
        host = self.client.post('/api/rooms', json={'questions': [q], 'maxPlayers': 1}).json()
        pin = host['pin']; headers = {'Authorization': 'Bearer ' + host['token']}
        player = self.client.post(f'/api/rooms/{pin}/join', json={'name': 'An'}).json()
        self.assertEqual(self.client.post(f'/api/rooms/{pin}/join', json={'name': 'Bình'}).status_code, 409)
        start = self.client.post(f'/api/rooms/{pin}/start', json={'seq': 0}, headers=headers)
        self.assertNotIn('correct', start.json()['current'])
        result = self.client.post(f'/api/rooms/{pin}/answer', json={'round': 1, 'index': 0, 'choice': 0},
                                  headers={'Authorization': 'Bearer ' + player['token']})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['phase'], 'reveal')
        self.assertEqual(result.json()['current']['source']['transcript'], 'T01-001')

    def test_merge_edges_sources_and_deleted_document(self):
        self.seed('doc1', 'first.pdf'); self.seed('doc2', 'second.md', turn=True)
        with patch.object(api, 'call_llm', side_effect=self.fake_llm):
            response = self.client.post('/api/merge', json={'doc_ids': ['doc1', 'doc2']})
            self.assertEqual(response.status_code, 200, response.text)
            mid = response.json()['merge_id']
            graph = self.client.get('/api/graph/' + mid).json()
            ids = {n['id'] for n in graph['nodes']}
            self.assertTrue(graph['edges'])
            self.assertTrue(all(e['source'] in ids and e['target'] in ids for e in graph['edges']))
            self.assertEqual({e['source']['doc_id'] for e in graph['nodes'][0]['evidence']}, {'doc1', 'doc2'})
            q = self.client.post('/api/quiz', json={'graph_id': mid, 'count': 1}).json()['questions'][0]
            self.assertEqual(q['source_doc_id'], 'doc1')
            self.assertEqual(q['text'], 'Nội dung AI đầy đủ')
        self.assertEqual(self.client.delete('/api/doc/doc1').status_code, 200)
        self.assertEqual(self.client.get('/api/graph/' + mid).status_code, 409)
        self.assertTrue(self.client.get('/api/merges').json()[0]['stale'])

    def test_semantic_merge_keeps_edges_of_renamed_nodes(self):
        self.seed('doc1', 'first.pdf'); self.seed('doc2', 'second.pdf')
        for did, name in [('doc1', 'Embedding'), ('doc2', 'Embeddings')]:
            path = api.CACHE / (did + '.json')
            graph = json.loads(path.read_text()); graph['nodes'][0]['name'] = name
            path.write_text(json.dumps(graph))
        with patch.object(api, 'call_llm', return_value='{"same": true, "reason": "same concept"}'):
            response = self.client.post('/api/merge', json={'doc_ids': ['doc1', 'doc2']})
        self.assertEqual(response.status_code, 200, response.text)
        graph = self.client.get('/api/graph/' + response.json()['merge_id']).json()
        self.assertEqual(len(graph['nodes']), 2)
        self.assertEqual(len(graph['edges']), 1)
        merged = next(n for n in graph['nodes'] if n['name'] == 'Embedding')
        self.assertIn('Embeddings', merged['aliases'])
        self.assertEqual({e['source']['doc_id'] for e in merged['evidence']}, {'doc1', 'doc2'})

    def test_plain_text_and_multiline_transcript_ingestion(self):
        from ingest import ingest_file
        path = Path(self.tmp.name) / 'notes.md'
        path.write_text('## Lesson\n**[T01-001]** First line\nSecond line preserved\n**[T01-002]** Next turn')
        chunks = ingest_file(path)
        self.assertEqual([c['turn'] for c in chunks], ['T01-001', 'T01-002'])
        self.assertIn('Second line preserved', chunks[0]['text'])
        path.write_text('## Lesson\nOrdinary markdown without transcript markers.')
        self.assertIn('Ordinary markdown', ingest_file(path)[0]['text'])

    def test_invalid_requests_and_llm_output(self):
        self.seed('doc1', 'first.pdf')
        for payload in [{}, {'graph_id': 'doc1', 'count': -1}, {'graph_id': 'doc1', 'topics': 'AI'}]:
            self.assertEqual(self.client.post('/api/quiz', json=payload).status_code, 400)
        self.assertEqual(self.client.post('/api/merge', json={'doc_ids': ['doc1', 'doc1']}).status_code, 400)
        with patch.object(api, 'call_llm', return_value='{"questions":[{"concept":"AI","q":"bad","a":["same","same"],"correct":null}]}'):
            result = self.client.post('/api/quiz', json={'graph_id': 'doc1'})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()['status'], 'insufficient_evidence')
        api.JOBS['doc1'] = {'status': 'processing'}
        self.assertEqual(self.client.delete('/api/doc/doc1').status_code, 409)

    def quiz_fixture(self):
        graph = self.seed('doc1', 'first.pdf')
        third = copy.deepcopy(graph['nodes'][1]); third.update(id='c3', name='Signature')
        graph['nodes'].append(third)
        ev = {'quote': 'Bằng chứng thứ hai khác biệt', 'source': {'file': 'first.pdf', 'page': 3}}
        graph['nodes'][0]['evidence'].extend([ev, copy.deepcopy(ev)])
        (api.CACHE / 'doc1.json').write_text(json.dumps(graph))
        return {'graph_id': 'doc1', 'count': 4, 'topics': ['AI', 'Token', 'Signature']}

    def test_four_questions_three_concepts_and_paired_evidence(self):
        payload = self.quiz_fixture()
        with patch.object(api, 'call_llm', side_effect=self.fake_llm) as llm:
            result = self.client.post('/api/quiz', json=payload).json()
        self.assertEqual(result['status'], 'complete')
        self.assertEqual((result['requested_count'], result['generated_count']), (4, 4))
        self.assertEqual([sum(q['concept_id'] == cid for q in result['questions']) for cid in ['c1','c2','c3']], [2,1,1])
        self.assertEqual(llm.call_count, 1)
        prompt = json.loads(llm.call_args.args[1])
        self.assertEqual(len(next(n for n in prompt['concepts'] if n['concept_id'] == 'c1')['evidence']), 2)
        second = next(q for q in result['questions'] if q['page'] == 3)
        self.assertEqual(second['quote'], 'Bằng chứng thứ hai khác biệt')
        self.assertEqual(second['source_file'], 'first.pdf')
        self.assertEqual({q['level'] for q in result['questions']}, {'Dễ', 'Trung bình', 'Khó'})

    def test_refill_reuses_rejected_concept_and_balances_retained(self):
        payload = self.quiz_fixture()
        with patch.object(api, 'call_llm', side_effect=self.fake_llm):
            existing = self.client.post('/api/quiz', json=payload).json()['questions']
            for q in existing:
                q['status'] = 'rejected' if q['concept_id'] == 'c3' else 'approved'
            before = copy.deepcopy(existing)
            result = self.client.post('/api/quiz', json={**payload, 'count': 1, 'existing_questions': existing}).json()
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['questions'][0]['concept_id'], 'c3')
        self.assertNotIn(result['questions'][0]['q'], {q['q'] for q in existing})
        self.assertEqual(existing, before)

    def test_one_topup_only_for_missing_slots(self):
        payload = self.quiz_fixture()
        def incomplete(system, user):
            result = json.loads(self.fake_llm(system, user))
            if len(json.loads(user)['requests']) == 4:
                result['questions'] = result['questions'][:2]
            return json.dumps(result)
        with patch.object(api, 'call_llm', side_effect=incomplete) as llm:
            result = self.client.post('/api/quiz', json=payload).json()
        self.assertEqual(result['generated_count'], 4)
        self.assertEqual([len(json.loads(call.args[1])['requests']) for call in llm.call_args_list], [4,2])
        self.assertEqual(len(json.loads(llm.call_args_list[1].args[1])['existing_questions']), 2)

    def test_partial_invalid_sources_duplicates_and_out_of_scope(self):
        payload = self.quiz_fixture()
        def invalid(system, user):
            result = json.loads(self.fake_llm(system, user))
            if len(json.loads(user)['requests']) == 4:
                qs = result['questions']
                qs[1]['q'] = qs[0]['q'].upper().replace('?', ' !!!')
                qs[2]['evidence_id'] = 'unknown'
                qs[3]['concept_id'] = 'outside'
            else:
                result = {'questions': []}
            return json.dumps(result)
        with patch.object(api, 'call_llm', side_effect=invalid) as llm:
            result = self.client.post('/api/quiz', json=payload).json()
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['generated_count'], 1)
        self.assertEqual(llm.call_count, 2)

    def test_same_concept_multiple_questions_and_normalized_existing_duplicates(self):
        payload = self.quiz_fixture()
        payload.update(topics=['Token'], count=2, level='Khó')
        with patch.object(api, 'call_llm', side_effect=self.fake_llm):
            result = self.client.post('/api/quiz', json=payload).json()
        self.assertEqual(result['status'], 'complete')
        self.assertEqual([q['concept_id'] for q in result['questions']], ['c2', 'c2'])
        self.assertTrue(all(q['level'] == 'Khó' for q in result['questions']))
        existing = result['questions'][0]
        existing.update(status='rejected', original_q='Câu nguyên bản trước chỉnh sửa?')
        def repeat(system, user):
            result = json.loads(self.fake_llm(system, user))
            result['questions'][0]['q'] = '  CÂU NGUYÊN BẢN TRƯỚC CHỈNH SỬA !!! '
            return json.dumps(result)
        with patch.object(api, 'call_llm', side_effect=repeat) as llm:
            result = self.client.post('/api/quiz', json={**payload, 'count': 1, 'existing_questions': [existing]}).json()
        self.assertEqual(result['generated_count'], 0)
        self.assertEqual(llm.call_count, 2)

    def test_empty_pool_empty_ai_and_service_errors(self):
        payload = self.quiz_fixture()
        with patch.object(api, 'call_llm') as llm:
            result = self.client.post('/api/quiz', json={**payload, 'topics': ['Unrelated']}).json()
            self.assertEqual(result['status'], 'insufficient_evidence')
            llm.assert_not_called()
        with patch.object(api, 'call_llm', return_value='{"questions": []}') as llm:
            result = self.client.post('/api/quiz', json=payload).json()
            self.assertEqual(result['status'], 'insufficient_evidence')
            self.assertEqual(llm.call_count, 2)
        with patch.object(api, 'call_llm', side_effect=TimeoutError):
            self.assertEqual(self.client.post('/api/quiz', json=payload).status_code, 502)
        with patch.object(api, 'call_llm') as llm:
            self.assertEqual(self.client.post('/api/quiz', json={**payload, 'existing_questions': [{}]}).status_code, 400)
            llm.assert_not_called()

    def test_upload_pipeline_cache_and_source(self):
        content = ('AI là một công cụ xử lý thông tin. ' * 5).encode()
        sha = hashlib.sha256(content).hexdigest()
        (api.CACHE / (sha + '.json')).write_text(json.dumps({'nodes': [], 'edges': [], 'stats': {}}))
        with patch.object(pipeline, 'call_llm', side_effect=AssertionError('Cache must not call AI')):
            response = self.client.post('/api/upload', files={'file': ('notes.txt', content, 'text/plain')})
            self.assertEqual(response.status_code, 200)
            did = response.json()['doc_id']
            for _ in range(100):
                docs = self.client.get('/api/docs').json()
                if docs[0]['status'] != 'processing': break
                time.sleep(.01)
            self.assertEqual(docs[0]['status'], 'ready', docs)
            chunks = json.loads((api.UPLOADS / did / 'chunks.json').read_text())
            self.assertTrue(chunks)
            source = self.client.get('/api/source', params={'gid': did, 'turn': chunks[0]['turn']})
            self.assertEqual(source.status_code, 200)
        self.assertEqual(self.client.post('/api/upload', files={'file': ('empty.txt', b'')}).status_code, 400)


if __name__ == '__main__': unittest.main()
