"""Discord integration: slash command handling and pairing announcements.

Env vars: DISCORD_APP_ID, DISCORD_PUBLIC_KEY, DISCORD_BOT_TOKEN.
"""
import os
import requests
from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError

from app import db
from app.models.league import League
from app.models.league_player import LeaguePlayer
from app.models.league_player_link import LeaguePlayerLink
from app.models.player import Player
from app.models.tournament import Tournament
from app.services.league_service import get_or_create_league_player, add_player_to_week, \
    calculate_league_standings

API_BASE = 'https://discord.com/api/v10'
MANAGE_GUILD = 0x20
EPHEMERAL = 64

# Interaction types
PING = 1
APPLICATION_COMMAND = 2

SLASH_COMMANDS = [
    {
        'name': 'signup',
        'description': 'Join the league roster for this channel',
        'options': [{
            'type': 3, 'name': 'name', 'required': False,
            'description': 'Name to play under (defaults to your Discord name)',
        }],
    },
    {'name': 'checkin', 'description': "Check in for this week's tournament"},
    {'name': 'checkout', 'description': "Withdraw from this week's tournament"},
    {'name': 'whosplaying', 'description': 'See who is checked in this week'},
    {'name': 'points', 'description': 'Check your league points and rank'},
    {'name': 'standings', 'description': 'Show the league standings'},
    {
        'name': 'link',
        'description': 'Link this channel to a league (requires Manage Server)',
        'default_member_permissions': str(MANAGE_GUILD),
        'options': [{
            'type': 4, 'name': 'league_id', 'required': True,
            'description': 'League ID (the number in the league URL)',
        }],
    },
]


def verify_signature(public_key_hex, signature, timestamp, body):
    try:
        VerifyKey(bytes.fromhex(public_key_hex)).verify(
            timestamp.encode() + body, bytes.fromhex(signature))
        return True
    except (BadSignatureError, ValueError):
        return False


INVITE_PERMISSIONS = 2048 | 16384  # Send Messages + Embed Links


def bot_invite_url():
    app_id = os.environ.get('DISCORD_APP_ID')
    if not app_id:
        return None
    return ('https://discord.com/oauth2/authorize'
            f'?client_id={app_id}&scope=bot+applications.commands'
            f'&permissions={INVITE_PERMISSIONS}')


def send_test_message(league):
    """Returns (ok, detail)."""
    if not league.discord_channel_id:
        return False, 'No Discord channel is linked to this league'
    return post_channel_message(league.discord_channel_id, {
        'content': f'👋 **{league.name}** is connected to Tabernacle! '
                   'Players can `/signup` and `/checkin` here, and pairings will be posted in this channel.'})


def _bot_headers():
    return {'Authorization': f"Bot {os.environ.get('DISCORD_BOT_TOKEN', '')}"}


def post_channel_message(channel_id, payload):
    """Returns (ok, detail); detail describes the failure and is logged."""
    if not os.environ.get('DISCORD_BOT_TOKEN'):
        return False, 'DISCORD_BOT_TOKEN is not set on the server'
    try:
        r = requests.post(f'{API_BASE}/channels/{channel_id}/messages',
                          json=payload, headers=_bot_headers(), timeout=5)
        if r.ok:
            return True, ''
        detail = f'Discord API {r.status_code}: {r.text[:200]}'
        print(f'[discord] post to channel {channel_id} failed — {detail}')
        return False, detail
    except requests.RequestException as e:
        print(f'[discord] post to channel {channel_id} error — {e}')
        return False, f'Request failed: {e}'


def register_commands():
    app_id = os.environ['DISCORD_APP_ID']
    r = requests.put(f'{API_BASE}/applications/{app_id}/commands',
                     json=SLASH_COMMANDS, headers=_bot_headers(), timeout=10)
    r.raise_for_status()
    return [c['name'] for c in r.json()]


# ---------- Pairing announcements ----------

def build_pairings_payload(tournament, round_obj):
    links = LeaguePlayerLink.query.filter_by(tournament_id=tournament.id).all()
    lp_by_player = {}
    if links:
        lps = LeaguePlayer.query.filter(
            LeaguePlayer.id.in_([l.league_player_id for l in links])).all()
        lp_map = {lp.id: lp for lp in lps}
        lp_by_player = {l.player_id: lp_map.get(l.league_player_id) for l in links}

    def display(player):
        lp = lp_by_player.get(player.id)
        if lp and lp.discord_user_id:
            return f'<@{lp.discord_user_id}>'
        return player.name

    fields = []
    for pod in round_obj.pods.order_by('pod_number').all():
        assignments = pod.assignments.order_by('seat_position').all()
        names = '\n'.join(f'{i}. {display(a.player)}' for i, a in enumerate(assignments, 1))
        if pod.is_bye:
            fields.append({'name': 'Bye', 'value': names or '—', 'inline': True})
        else:
            title = f'Table {pod.table_number}' if pod.table_number else f'Pod {pod.pod_number}'
            fields.append({'name': title, 'value': names or '—', 'inline': True})

    embeds = [{'title': f'Round {round_obj.round_number} Pairings',
               'color': 0x5865F2, 'fields': fields[i:i + 25]}
              for i in range(0, len(fields), 25)]
    return {'content': f'**{tournament.name}** — Round {round_obj.round_number} pairings are up!',
            'embeds': embeds[:10]}


def post_round_pairings(tournament, round_obj):
    """Post pairings to the league's linked channel. Never raises."""
    try:
        league = tournament.league
        if not league or not league.discord_channel_id:
            return False
        if not os.environ.get('DISCORD_BOT_TOKEN'):
            return False
        payload = build_pairings_payload(tournament, round_obj)
        ok, _ = post_channel_message(league.discord_channel_id, payload)
        return ok
    except Exception:
        return False


# ---------- Interaction handling ----------

def _reply(content, ephemeral=False):
    data = {'content': content}
    if ephemeral:
        data['flags'] = EPHEMERAL
    return {'type': 4, 'data': data}


def _interaction_user(interaction):
    member = interaction.get('member') or {}
    user = member.get('user') or interaction.get('user') or {}
    name = member.get('nick') or user.get('global_name') or user.get('username') or 'Unknown'
    return str(user.get('id', '')), name


def _option(interaction, name):
    for opt in interaction.get('data', {}).get('options', []) or []:
        if opt.get('name') == name:
            return opt.get('value')
    return None


def _league_for_channel(channel_id):
    return League.query.filter_by(discord_channel_id=str(channel_id)).first()


def _open_week(league):
    return Tournament.query.filter_by(league_id=league.id, status='registration') \
        .order_by(Tournament.week_number.desc()).first()


def handle_interaction(interaction):
    if interaction.get('type') == PING:
        return {'type': 1}
    if interaction.get('type') != APPLICATION_COMMAND:
        return _reply('Unsupported interaction.', ephemeral=True)

    command = interaction.get('data', {}).get('name')
    if command == 'link':
        return _cmd_link(interaction)

    league = _league_for_channel(interaction.get('channel_id'))
    if not league:
        return _reply('This channel is not linked to a league. '
                      'An admin can run `/link league_id` first.', ephemeral=True)

    handlers = {'signup': _cmd_signup, 'checkin': _cmd_checkin,
                'checkout': _cmd_checkout, 'whosplaying': _cmd_whosplaying,
                'points': _cmd_points, 'standings': _cmd_standings}
    handler = handlers.get(command)
    if not handler:
        return _reply(f'Unknown command: {command}', ephemeral=True)
    return handler(league, interaction)


def _cmd_link(interaction):
    member = interaction.get('member') or {}
    try:
        perms = int(member.get('permissions', '0'))
    except ValueError:
        perms = 0
    if not perms & MANAGE_GUILD:
        return _reply('You need the Manage Server permission to link a league.', ephemeral=True)

    league = League.query.get(_option(interaction, 'league_id') or 0)
    if not league:
        return _reply('League not found. Check the ID on the league dashboard URL.', ephemeral=True)

    league.discord_channel_id = str(interaction.get('channel_id'))
    db.session.commit()
    return _reply(f'This channel is now linked to **{league.name}**. '
                  'Players can `/signup` and `/checkin` here, and pairings will be posted automatically.')


def _get_or_claim_league_player(league, uid, name):
    """Find roster entry by Discord ID, claim an unclaimed same-name entry, or create one."""
    lp = LeaguePlayer.query.filter_by(league_id=league.id, discord_user_id=uid).first()
    if lp:
        return lp, False
    lp = LeaguePlayer.query.filter_by(league_id=league.id, name=name).first()
    if lp:
        if lp.discord_user_id and lp.discord_user_id != uid:
            return None, False  # name taken by another Discord user
        lp.discord_user_id = uid
        db.session.commit()
        return lp, False
    current_week = max(league.get_current_week(), 1)
    lp = get_or_create_league_player(league.id, name, current_week)
    lp.discord_user_id = uid
    db.session.commit()
    return lp, True


def _cmd_signup(league, interaction):
    uid, display_name = _interaction_user(interaction)
    name = (_option(interaction, 'name') or display_name).strip()[:100]

    existing = LeaguePlayer.query.filter_by(league_id=league.id, discord_user_id=uid).first()
    if existing:
        return _reply(f'You are already on the roster as **{existing.name}**.', ephemeral=True)

    lp, created = _get_or_claim_league_player(league, uid, name)
    if lp is None:
        return _reply(f'The name **{name}** is already claimed by someone else. '
                      'Try `/signup name:YourName` with a different name.', ephemeral=True)
    verb = 'joined' if created else 'is now linked to'
    return _reply(f'🎉 **{lp.name}** {verb} **{league.name}**!')


def _cmd_checkin(league, interaction):
    tournament = _open_week(league)
    if not tournament:
        return _reply('No week is open for check-in right now.', ephemeral=True)

    uid, display_name = _interaction_user(interaction)
    lp, _ = _get_or_claim_league_player(league, uid, display_name)
    if lp is None:
        return _reply(f'The name **{display_name}** is already claimed by someone else. '
                      'Run `/signup name:YourName` first.', ephemeral=True)

    already = LeaguePlayerLink.query.filter_by(
        league_player_id=lp.id, tournament_id=tournament.id).first()
    if already:
        return _reply(f'You are already checked in for Week {tournament.week_number}.', ephemeral=True)

    add_player_to_week(lp, tournament)
    count = Player.query.filter_by(tournament_id=tournament.id, dropped=False).count()
    return _reply(f'✅ **{lp.name}** is checked in for Week {tournament.week_number} '
                  f'({count} player{"s" if count != 1 else ""} so far).')


def _cmd_checkout(league, interaction):
    tournament = _open_week(league)
    if not tournament:
        return _reply('No week is open right now.', ephemeral=True)

    uid, _ = _interaction_user(interaction)
    lp = LeaguePlayer.query.filter_by(league_id=league.id, discord_user_id=uid).first()
    link = lp and LeaguePlayerLink.query.filter_by(
        league_player_id=lp.id, tournament_id=tournament.id).first()
    if not link:
        return _reply(f'You are not checked in for Week {tournament.week_number}.', ephemeral=True)

    player = Player.query.get(link.player_id)
    db.session.delete(link)
    if player:
        db.session.delete(player)
    db.session.commit()
    return _reply(f'👋 **{lp.name}** is out for Week {tournament.week_number}.')


def _cmd_points(league, interaction):
    uid, _ = _interaction_user(interaction)
    lp = LeaguePlayer.query.filter_by(league_id=league.id, discord_user_id=uid).first()
    if not lp:
        return _reply('You are not on the roster yet — run `/signup` first.', ephemeral=True)

    standings = calculate_league_standings(league)
    s = next((x for x in standings if x['league_player'].id == lp.id), None)
    if not s:
        return _reply('No stats for you yet — check in and play a week first.', ephemeral=True)

    parts = [f"{s['wins']} pod win{'s' if s['wins'] != 1 else ''} ({s['wins'] * 5} pts)",
             f"{s['checkins']} check-in{'s' if s['checkins'] != 1 else ''} ({s['checkins']} pt{'s' if s['checkins'] != 1 else ''})"]
    if s['late_join_pts']:
        parts.append(f"late-join bonus ({s['late_join_pts']} pts)")
    return _reply(f"🏆 **{lp.name}** — **{s['league_points']} league points**, "
                  f"rank {s['rank']} of {len(standings)}\n" + ' · '.join(parts),
                  ephemeral=True)


def _cmd_standings(league, interaction):
    standings = calculate_league_standings(league)
    if not standings:
        return _reply('No standings yet — nobody is on the roster.', ephemeral=True)

    medals = {1: '🥇', 2: '🥈', 3: '🥉'}
    lines = []
    for s in standings[:10]:
        rank = medals.get(s['rank'], f"{s['rank']}.")
        lines.append(f"{rank} **{s['league_player'].name}** — {s['league_points']} pts "
                     f"({s['wins']}W, {s['checkins']} week{'s' if s['checkins'] != 1 else ''})")
    title = f'**{league.name} Standings**'
    if len(standings) > 10:
        title += f' (top 10 of {len(standings)})'
    return _reply(title + '\n' + '\n'.join(lines))


def _cmd_whosplaying(league, interaction):
    tournament = _open_week(league)
    if not tournament:
        return _reply('No week is open right now.', ephemeral=True)

    players = Player.query.filter_by(tournament_id=tournament.id, dropped=False) \
        .order_by(Player.name).all()
    if not players:
        return _reply(f'Nobody has checked in for Week {tournament.week_number} yet. '
                      'Be the first with `/checkin`!')
    roster = '\n'.join(f'{i}. {p.name}' for i, p in enumerate(players, 1))
    return _reply(f'**Week {tournament.week_number} — {len(players)} checked in:**\n{roster}')
