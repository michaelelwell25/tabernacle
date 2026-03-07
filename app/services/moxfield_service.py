import re
import urllib.request
import json


def parse_moxfield_id(url):
    """Extract the deck ID from a Moxfield URL."""
    match = re.search(r'moxfield\.com/decks/([A-Za-z0-9_-]+)', url)
    return match.group(1) if match else None


def fetch_moxfield_deck(url):
    """Fetch deck info from Moxfield. Returns (commander_names, deck_name) or (None, None) on failure."""
    deck_id = parse_moxfield_id(url)
    if not deck_id:
        return None, None

    api_url = f'https://api2.moxfield.com/v3/decks/all/{deck_id}'
    req = urllib.request.Request(api_url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json',
        'Origin': 'https://www.moxfield.com',
        'Referer': 'https://www.moxfield.com/',
    })

    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())

        commanders = data.get('boards', {}).get('commanders', {}).get('cards', {})
        commander_names = [v['card']['name'] for v in commanders.values() if 'card' in v]
        deck_name = data.get('name', '')

        commander_str = ' / '.join(commander_names) if commander_names else None
        return commander_str, deck_name
    except Exception:
        return None, None
