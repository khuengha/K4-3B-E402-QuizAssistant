"""Lessonleaf Live Quiz — dependency-free, in-memory classroom server."""
import argparse
import copy
import json
import mimetypes
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent


class APIError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def require(condition, message, status=400):
    if not condition:
        raise APIError(message, status)


def text(value, limit=2000):
    require(isinstance(value, str) and 0 < len(value.strip()) <= limit, 'Nội dung không hợp lệ.')
    return value


class QuizStore:
    def __init__(self, clock=time.time):
        self.rooms = {}
        self.clock = clock
        self.lock = threading.RLock()

    def create(self, data):
        qs = data.get('questions')
        require(isinstance(qs, list) and 1 <= len(qs) <= 100, 'Cần từ 1 đến 100 câu đã duyệt.')
        for q in qs:
            require(isinstance(q, dict) and q.get('status') == 'approved', 'Chỉ sử dụng câu hỏi đã duyệt.')
            text(q.get('q'), 1000)
            require(isinstance(q.get('a'), list) and len(q['a']) == 4, 'Mỗi câu cần 4 phương án.')
            for option in q['a']:
                text(option, 500)
            require(len({a.strip().casefold() for a in q['a']}) == 4, 'Phương án không được trùng nhau.')
            require(type(q.get('correct')) is int and 0 <= q['correct'] < 4, 'Đáp án đúng không hợp lệ.')
            text(q.get('topic'), 100)
            text(q.get('level'), 100)
            text(q.get('explain'), 2000)
            require(type(q.get('page')) is int and q['page'] > 0, 'Thiếu trang nguồn.')
            text(q.get('code'), 100)
        duration = data.get('duration', 30)
        require(type(duration) is int and duration in (15, 20, 30, 45, 60, 90), 'Thời gian không hợp lệ.')
        max_players = data.get('maxPlayers', 30)
        require(type(max_players) is int and 1 <= max_players <= 100,
                'Số người tham gia tối đa phải là số nguyên từ 1 đến 100.')
        # Bound storage; rooms expire after 12 hours without activity.
        for pin in list(self.rooms):
            if self.clock() - self.rooms[pin]['touched'] > 43200:
                del self.rooms[pin]
        require(len(self.rooms) < 200, 'Server đã đủ phòng. Hãy thử lại sau.', 503)
        pin = str(secrets.randbelow(900000) + 100000)
        while pin in self.rooms:
            pin = str(secrets.randbelow(900000) + 100000)
        host = secrets.token_urlsafe(32)
        room = dict(pin=pin, host=host, title=text(data.get('title', 'Live Quiz'), 150),
                    questions=copy.deepcopy(qs), duration=duration, maxPlayers=max_players, players={}, phase='lobby',
                    index=-1, deadline=None, round=1, seq=0, touched=self.clock(), history=[])
        self.rooms[pin] = room
        return dict(pin=pin, token=host, role='host')

    def room(self, pin):
        room = self.rooms.get(pin)
        require(room is not None and self.clock() - room['touched'] <= 43200,
                'Không tìm thấy phòng hoặc phòng đã hết hạn.', 404)
        room['touched'] = self.clock()
        self.tick(room)
        return room

    def tick(self, room):
        if room['phase'] == 'question' and self.clock() >= room['deadline']:
            room['phase'] = 'reveal'
            room['seq'] += 1

    def identity(self, room, token):
        if token and secrets.compare_digest(token, room['host']):
            return 'host', None
        for p in room['players'].values():
            if token and secrets.compare_digest(token, p['token']):
                return 'player', p
        raise APIError('Phiên tham gia không hợp lệ. Vui lòng vào phòng lại.', 401)

    def join(self, room, data):
        require(room['phase'] == 'lobby', 'Phòng đã bắt đầu hoặc đã kết thúc. Hãy chờ lượt chơi mới.', 409)
        capacity = room.get('maxPlayers', 100)
        require(len(room['players']) < capacity,
                f'Phòng đã đủ {capacity}/{capacity} người chơi. Không thể tham gia thêm.', 409)
        name = text(data.get('name'), 30).strip()
        require(not any(p['name'].casefold() == name.casefold() for p in room['players'].values()),
                'Tên này đã được sử dụng trong phòng. Hãy chọn tên khác.', 409)
        pid = secrets.token_hex(6)
        token = secrets.token_urlsafe(32)
        room['players'][pid] = dict(id=pid, token=token, name=name, answers={})
        return dict(pin=room['pin'], token=token, role='player')

    def begin_question(self, room):
        room['phase'] = 'question'
        room['deadline'] = self.clock() + room['duration']
        room['seq'] += 1

    def action(self, room, token, action, data):
        role, _ = self.identity(room, token)
        require(role == 'host', 'Chỉ giảng viên được điều khiển phòng.', 403)
        require(data.get('seq') == room['seq'], 'Phòng đã chuyển bước. Hãy chờ đồng bộ rồi thử lại.', 409)
        require(room['phase'] != 'closed', 'Phòng đã kết thúc.', 409)
        if action == 'start':
            require(room['phase'] == 'lobby' and room['players'], 'Cần ít nhất một người chơi trong phòng chờ.', 409)
            room['index'] = 0
            self.begin_question(room)
        elif action == 'reveal':
            require(room['phase'] == 'question', 'Không có câu hỏi đang chạy.', 409)
            room['phase'] = 'reveal'
            room['seq'] += 1
        elif action == 'next':
            require(room['phase'] == 'reveal', 'Hãy xem đáp án trước khi chuyển câu.', 409)
            if room['index'] + 1 == len(room['questions']):
                room['phase'] = 'finished'
                room['seq'] += 1
            else:
                room['index'] += 1
                self.begin_question(room)
        elif action == 'restart':
            require(room['phase'] != 'lobby', 'Phòng đang chờ bắt đầu.', 409)
            room['history'].append(self.report(room))
            room['history'] = room['history'][-10:]
            for p in room['players'].values():
                p['answers'] = {}
            room.update(phase='lobby', index=-1, deadline=None, round=room['round'] + 1, seq=room['seq'] + 1)
        elif action == 'close':
            room['phase'] = 'closed'
            room['seq'] += 1
        else:
            raise APIError('Thao tác không hợp lệ.', 404)

    def answer(self, room, token, data):
        role, player = self.identity(room, token)
        require(role == 'player', 'Host không gửi đáp án.', 403)
        require(data.get('round') == room['round'] and data.get('index') == room['index'],
                'Câu hỏi đã thay đổi. Hãy chờ đồng bộ.', 409)
        choice = data.get('choice')
        require(type(choice) is int and 0 <= choice < 4, 'Phương án không hợp lệ.')
        # A repeated network request with the same choice is safe; changing it is forbidden.
        previous = player['answers'].get(room['index'])
        if previous is not None:
            require(previous == choice, 'Bạn đã chốt đáp án cho câu này.', 409)
            return
        require(room['phase'] == 'question' and self.clock() < room['deadline'], 'Đã hết thời gian trả lời.', 409)
        player['answers'][room['index']] = choice
        if all(room['index'] in p['answers'] for p in room['players'].values()):
            room['phase'] = 'reveal'
            room['seq'] += 1

    def scored_count(self, room):
        if room['phase'] == 'lobby':
            return 0
        return room['index'] + (room['phase'] != 'question')

    def report(self, room):
        n = self.scored_count(room)
        rows = []
        topics = {}
        breakdown = []
        for i, q in enumerate(room['questions'][:n]):
            counts = [0, 0, 0, 0]
            skipped = 0
            for p in room['players'].values():
                choice = p['answers'].get(i)
                if choice is None:
                    skipped += 1
                else:
                    counts[choice] += 1
            correct = counts[q['correct']]
            total = len(room['players'])
            item = topics.setdefault(q['topic'], dict(topic=q['topic'], wrong=0, skipped=0, total=0))
            item['wrong'] += total - correct - skipped
            item['skipped'] += skipped
            item['total'] += total
            breakdown.append(dict(index=i, question=q['q'], correct=q['correct'], options=q['a'],
                                  topic=q['topic'], difficulty=q['level'], source=dict(slide=q['page'], transcript=q['code']),
                                  explanation=q['explain'], counts=counts, skipped=skipped, total=total))
        for p in room['players'].values():
            correct = wrong = skipped = 0
            weaknesses = {}
            for i, q in enumerate(room['questions'][:n]):
                choice = p['answers'].get(i)
                if choice is None:
                    skipped += 1
                elif choice == q['correct']:
                    correct += 1
                else:
                    wrong += 1
                    weaknesses[q['topic']] = weaknesses.get(q['topic'], 0) + 1
            rows.append(dict(id=p['id'], name=p['name'], score=correct * 1000, correct=correct,
                             wrong=wrong, skipped=skipped, weakTopics=sorted(
                                 [dict(topic=k, wrong=v) for k, v in weaknesses.items()], key=lambda x: -x['wrong'])))
        rows.sort(key=lambda p: (-p['score'], p['name'].casefold()))
        last_score = None
        rank = 0
        for i, row in enumerate(rows):
            if row['score'] != last_score:
                rank = i + 1
            row['rank'] = rank
            last_score = row['score']
        return dict(round=room['round'], scored=n, questionCount=len(room['questions']), players=rows,
                    topics=sorted(topics.values(), key=lambda t: (-t['wrong'], -t['skipped'], t['topic'])),
                    breakdown=breakdown, title=room['title'])

    def state(self, room, token):
        role, player = self.identity(room, token)
        report = self.report(room)
        current = None
        if room['index'] >= 0:
            q = room['questions'][room['index']]
            current = dict(index=room['index'], text=q['q'], options=q['a'], topic=q['topic'], difficulty=q['level'])
            if room['phase'] != 'question':
                current.update(correct=q['correct'], explanation=q['explain'],
                               source=dict(slide=q['page'], transcript=q['code']))
        me = next((p for p in report['players'] if player and p['id'] == player['id']), None)
        return dict(pin=room['pin'], title=room['title'], role=role, phase=room['phase'], seq=room['seq'],
                    round=room['round'], duration=room['duration'], maxPlayers=room.get('maxPlayers', 100), serverTime=self.clock() * 1000,
                    deadline=room['deadline'] * 1000 if room['deadline'] else None,
                    questionCount=len(room['questions']), current=current, players=report['players'], me=me,
                    myAnswer=player['answers'].get(room['index']) if player else None,
                    answerCount=sum(room['index'] in p['answers'] for p in room['players'].values()),
                    report=report if room['phase'] in ('reveal', 'finished', 'closed') else None)


STORE = QuizStore()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Never log authentication headers or participant names.
        pass

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path.startswith('/api/'):
            return self.api('GET', path)
        files = {'/': 'index1.html', '/index1.html': 'index1.html', '/live.html': 'live.html',
                 '/live.js': 'live.js', '/live.css': 'live.css'}
        name = files.get(path)
        if not name:
            return self.send_json(dict(error='Không tìm thấy trang.'), 404)
        body = (ROOT / name).read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', (mimetypes.guess_type(name)[0] or 'text/plain') + '; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self.api('POST', urlsplit(self.path).path)

    def api(self, method, path):
        try:
            data = {}
            if method == 'POST':
                require(self.headers.get_content_type() == 'application/json', 'Yêu cầu JSON.', 415)
                size = int(self.headers.get('Content-Length', 0))
                require(0 < size <= 1000000, 'Yêu cầu quá lớn hoặc rỗng.', 413)
                data = json.loads(self.rfile.read(size))
                require(isinstance(data, dict), 'Dữ liệu không hợp lệ.')
            token = self.headers.get('Authorization', '').removeprefix('Bearer ')
            parts = path.strip('/').split('/')
            with STORE.lock:
                if path == '/api/rooms' and method == 'POST':
                    return self.send_json(STORE.create(data), 201)
                require(len(parts) in (3, 4) and parts[:2] == ['api', 'rooms'], 'Không tìm thấy API.', 404)
                room = STORE.room(parts[2])
                if method == 'GET' and len(parts) == 3:
                    return self.send_json(STORE.state(room, token))
                require(method == 'POST' and len(parts) == 4, 'Thao tác không hợp lệ.', 404)
                action = parts[3]
                if action == 'join':
                    return self.send_json(STORE.join(room, data), 201)
                if action == 'answer':
                    STORE.answer(room, token, data)
                else:
                    STORE.action(room, token, action, data)
                return self.send_json(STORE.state(room, token))
        except APIError as e:
            self.send_json(dict(error=str(e)), e.status)
        except (ValueError, TypeError, UnicodeDecodeError):
            self.send_json(dict(error='Dữ liệu yêu cầu không hợp lệ.'), 400)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f'Lessonleaf: http://localhost:{args.port} — cùng Wi-Fi: dùng IP LAN của máy host.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
