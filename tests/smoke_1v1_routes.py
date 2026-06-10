"""Manual smoke test: constructed flow through the real routes. Run directly."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import Tournament, Player
from app.models.user import User
from app.services.pairing_service import generate_swiss_pairings
from app.services.playoff_service import start_playoffs

app = create_app('testing')
app.config['SQLALCHEMY_ECHO'] = False
with app.app_context():
    db.create_all()
    u = User(email='to@test.com', name='TO', role='admin')
    u.set_password('secret123')
    db.session.add(u)
    db.session.commit()

    client = app.test_client()
    r = client.post('/login', data={'email': 'to@test.com', 'password': 'secret123'})
    assert r.status_code == 302 and 'login' not in (r.headers.get('Location') or ''), \
        (r.status_code, r.headers.get('Location'))
    print('login OK')

    r = client.post('/tournaments/create', data={
        'name': 'FNM Modern', 'date': '2026-06-12', 'format': 'constructed',
        'round_timer_minutes': '50'}, follow_redirects=True)
    assert r.status_code == 200
    t = Tournament.query.filter_by(name='FNM Modern').first()
    if t is None:
        import re
        flashes = re.findall(rb'class="flash[^"]*"[^>]*>([^<]+)', r.data)
        print('DEBUG status:', r.status_code, 'flashes:', flashes)
        print(r.data[:2000].decode(errors='replace'))
        raise SystemExit(1)
    assert t.format == 'constructed' and t.scoring_system == '3-1-0' and t.bye_points == 3
    print('create route OK:', t.format, t.scoring_system, 'bye =', t.bye_points)

    for i in range(7):
        db.session.add(Player(tournament_id=t.id, name=f'P{i+1}'))
    t.status = 'active'
    db.session.commit()

    rd = generate_swiss_pairings(t.id, 1)
    t.current_round = 1
    db.session.commit()

    for url in [f'/tournaments/{t.id}', f'/rounds/{rd.id}', f'/results/{rd.id}/submit', '/tournaments/create']:
        r = client.get(url)
        assert r.status_code == 200, (url, r.status_code)
        print('render OK:', url)

    pods = [p for p in rd.pods.order_by('pod_number') if not p.is_bye]
    form = {}
    a0 = pods[0].assignments.order_by('seat_position').all()
    form[f'result_{pods[0].id}'] = f'{a0[0].player_id}:2-1'
    form[f'result_{pods[1].id}'] = 'draw:1-1'
    a2 = pods[2].assignments.order_by('seat_position').all()
    form[f'result_{pods[2].id}'] = f'{a2[1].player_id}:2-0'
    r = client.post(f'/results/{rd.id}/submit', data=form, follow_redirects=True)
    assert r.status_code == 200 and rd.is_complete()
    print('results route OK, round complete')

    r = client.get(f'/rounds/{rd.id}')
    assert r.status_code == 200 and b'WINNER 2-1' in r.data
    print('round view shows scores OK')

    r = client.get(f'/standings/tournament/{t.id}')
    assert r.status_code == 200, r.status_code
    print('standings render OK')

    start_playoffs(t.id, 4)
    db.session.commit()
    r = client.get(f'/playoffs/tournament/{t.id}')
    assert r.status_code == 200 and b'Semifinals' in r.data
    print('playoff view OK (semifinals shown)')

    print('ALL SMOKE CHECKS PASSED')
