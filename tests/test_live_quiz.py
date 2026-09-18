import copy
import json
from pathlib import Path
import sys
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


def question(topic='Token', correct=0):
    return dict(q='Token là gì?', a=['Đơn vị văn bản', 'Tốc độ học', 'Bộ dữ liệu', 'Tên mô hình'],
                correct=correct, topic=topic, level='Dễ', page=12, code='T03-045',
                explain='Token là một đơn vị văn bản.', status='approved')


class RoomTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000
        self.store = server.QuizStore(lambda: self.now)
        self.questions = [question(), question('LLM', 1)]
        self.host = self.store.create(dict(questions=self.questions, duration=15, title='Test'))
        self.room = self.store.room(self.host['pin'])
        self.alice = self.store.join(self.room, dict(name='An'))
        self.bob = self.store.join(self.room, dict(name='Bình'))

    def act(self, action):
        self.store.action(self.room, self.host['token'], action, dict(seq=self.room['seq']))

    def answer(self, player, choice):
        self.store.answer(self.room, player['token'], dict(round=self.room['round'], index=self.room['index'], choice=choice))

    def test_approved_only_and_immutable_snapshot(self):
        self.questions[0]['q'] = 'Changed after creation'
        self.assertNotEqual(self.room['questions'][0]['q'], self.questions[0]['q'])
        self.assertEqual(self.room['questions'][0]['code'], 'T03-045')
        q = question(); q['status'] = 'pending'
        with self.assertRaises(server.APIError): self.store.create(dict(questions=[q]))
        q['status'] = 'rejected'
        with self.assertRaises(server.APIError): self.store.create(dict(questions=[q]))

    def test_private_tokens_answers_and_host_permissions(self):
        self.act('start')
        for credential in [self.alice, self.bob, self.host]:
            state = self.store.state(self.room, credential['token'])
            self.assertNotIn('correct', state['current'])
            self.assertNotIn('source', state['current'])
            self.assertIsNone(state['report'])
            self.assertNotIn(self.host['token'], json.dumps(state))
            self.assertNotIn(self.alice['token'], json.dumps(state))
        with self.assertRaises(server.APIError): self.store.state(self.room, 'invalid')
        with self.assertRaises(server.APIError): self.store.action(self.room, self.alice['token'], 'close', dict(seq=self.room['seq']))

    def test_complete_game_scoring_topics_and_ties(self):
        self.act('start')
        self.answer(self.alice, 0); self.answer(self.bob, 2)
        self.assertEqual(self.room['phase'], 'reveal')
        state = self.store.state(self.room, self.alice['token'])
        self.assertEqual(state['current']['correct'], 0)
        self.assertEqual(state['current']['source'], dict(slide=12, transcript='T03-045'))
        self.assertEqual(state['me']['score'], 1000)
        self.act('next')
        self.answer(self.alice, 0); self.answer(self.bob, 1)
        self.act('next')
        report = self.store.state(self.room, self.host['token'])['report']
        self.assertEqual(self.room['phase'], 'finished')
        self.assertEqual([p['score'] for p in report['players']], [1000, 1000])
        self.assertEqual([p['rank'] for p in report['players']], [1, 1])
        self.assertTrue(all(p['correct'] == 1 and p['wrong'] == 1 for p in report['players']))
        self.assertEqual(sum(t['wrong'] for t in report['topics']), 2)

    def test_duplicate_answer_and_expiry(self):
        self.act('start'); self.answer(self.alice, 0); self.answer(self.alice, 0)
        with self.assertRaises(server.APIError): self.answer(self.alice, 1)
        self.now += 16
        self.store.room(self.room['pin'])
        with self.assertRaises(server.APIError): self.answer(self.bob, 0)
        report = self.store.report(self.room)
        bob = next(p for p in report['players'] if p['name'] == 'Bình')
        self.assertEqual((bob['correct'], bob['wrong'], bob['skipped']), (0, 0, 1))
        self.assertEqual(report['topics'][0]['skipped'], 1)
        self.assertEqual(report['topics'][0]['wrong'], 0)

    def test_restart_stale_requests_close(self):
        self.act('start'); self.answer(self.alice, 0); self.act('reveal')
        old = copy.deepcopy(self.room['questions'])
        old_seq = self.room['seq']
        self.act('restart')
        self.assertEqual(self.room['questions'], old)
        self.assertEqual(self.room['round'], 2)
        self.assertEqual(self.room['phase'], 'lobby')
        self.assertTrue(all(p['score'] == 0 for p in self.store.report(self.room)['players']))
        self.act('start')
        with self.assertRaises(server.APIError):
            self.store.answer(self.room, self.alice['token'], dict(round=1, index=0, choice=0))
        with self.assertRaises(server.APIError):
            self.store.action(self.room, self.host['token'], 'reveal', dict(seq=old_seq))
        self.act('close')
        with self.assertRaises(server.APIError): self.answer(self.alice, 0)
        with self.assertRaises(server.APIError): self.act('restart')
        with self.assertRaises(server.APIError): self.store.join(self.room, dict(name='Late'))

    def test_room_capacity_validation_and_restart(self):
        for invalid in [0, -1, 101, 1.5, True, '10', None]:
            with self.assertRaises(server.APIError):
                self.store.create(dict(questions=[question()], maxPlayers=invalid))
        credentials = self.store.create(dict(questions=[question()], maxPlayers=1))
        room = self.store.room(credentials['pin'])
        player = self.store.join(room, dict(name='Only player'))
        with self.assertRaisesRegex(server.APIError, '1/1'):
            self.store.join(room, dict(name='Extra player'))
        self.assertEqual(self.store.state(room, player['token'])['maxPlayers'], 1)
        self.store.action(room, credentials['token'], 'start', dict(seq=room['seq']))
        self.store.action(room, credentials['token'], 'restart', dict(seq=room['seq']))
        self.assertEqual(room['maxPlayers'], 1)
        self.assertEqual(self.store.state(room, player['token'])['me']['name'], 'Only player')
        with self.assertRaises(server.APIError): self.store.join(room, dict(name='Extra player'))

    def test_join_validation_and_late_join(self):
        with self.assertRaises(server.APIError): self.store.join(self.room, dict(name=' AN '))
        with self.assertRaises(server.APIError): self.store.join(self.room, dict(name=' '))
        self.act('start')
        with self.assertRaises(server.APIError): self.store.join(self.room, dict(name='Late'))


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.url = 'http://127.0.0.1:' + str(cls.http.server_address[1])
        cls.worker = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown(); cls.http.server_close(); cls.worker.join()

    def request(self, path, data=None, token=None):
        req = Request(self.url + path, data=json.dumps(data).encode() if data is not None else None,
                      headers={'Content-Type':'application/json', **({'Authorization':'Bearer '+token} if token else {})})
        with urlopen(req, timeout=5) as response:
            return json.load(response)

    def test_concurrent_join_cannot_exceed_capacity(self):
        h = self.request('/api/rooms', dict(questions=[question()], maxPlayers=1))
        base = '/api/rooms/' + h['pin']
        joined, failures = [], []
        def join(name):
            try: joined.append(self.request(base + '/join', dict(name=name)))
            except HTTPError as e: failures.append(e.code)
        workers = [threading.Thread(target=join, args=(name,)) for name in ('First', 'Second')]
        for worker in workers: worker.start()
        for worker in workers: worker.join()
        self.assertEqual(len(joined), 1)
        self.assertEqual(failures, [409])
        state = self.request(base, token=h['token'])
        self.assertEqual((len(state['players']), state['maxPlayers']), (1, 1))

    def test_two_http_players_and_static_boundaries(self):
        h = self.request('/api/rooms', dict(questions=[question()], duration=15))
        base = '/api/rooms/' + h['pin']
        a = self.request(base + '/join', dict(name='HTTP A'))
        b = self.request(base + '/join', dict(name='HTTP B'))
        state = self.request(base, token=h['token'])
        self.request(base+'/start', dict(seq=state['seq']), h['token'])
        errors=[]
        def submit(player):
            try: self.request(base+'/answer', dict(index=0, round=1, choice=0), player['token'])
            except Exception as e: errors.append(e)
        workers=[threading.Thread(target=submit,args=(p,)) for p in (a,b)]
        for worker in workers: worker.start()
        for worker in workers: worker.join()
        self.assertEqual(errors, [])
        state=self.request(base, token=h['token'])
        self.assertEqual(state['phase'], 'reveal')
        self.assertEqual([p['score'] for p in state['players']], [1000,1000])
        for path in ('/.git/config','/server.py','/api/rooms/'+h['pin']):
            with self.assertRaises(HTTPError): self.request(path)
        with urlopen(self.url+'/live.html') as response:
            self.assertIn(b'live.js', response.read())


if __name__ == '__main__':
    unittest.main()
