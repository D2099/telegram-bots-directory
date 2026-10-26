"""Shared, dependency-free catalog rules. Never trust fetched text as HTML."""
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
HIDE_AFTER = 3
CATEGORIES = json.loads((ROOT / 'data/categories.json').read_text(encoding='utf-8'))
CATEGORY_MAP = {c['id']: c for c in CATEGORIES}
VALID_CATEGORIES = set(CATEGORY_MAP)
USERNAME = re.compile(r'@[A-Za-z][A-Za-z0-9_]{3,31}\Z')
ID = re.compile(r'[a-z0-9_]{1,64}\Z')
START_PAYLOAD = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')
REFERRAL_DISCLOSURE = '通过此入口使用，站长可能获得邀请奖励。'


def load_site():
    return json.loads((ROOT / 'data/site.json').read_text(encoding='utf-8'))


def is_hidden(bot):
    fetch = bot.get('fetch') or {}
    return fetch.get('status') == 'dead' and (fetch.get('dead_streak') or 0) >= HIDE_AFTER


def display_name(bot):
    return bot.get('name') or (bot.get('fetch') or {}).get('title') or bot['username'].lstrip('@')


def referral_start(bot):
    """An optional, explicit Telegram payload, never a URL or query string."""
    payload = bot.get('referralStart', '')
    if not isinstance(payload, str) or (payload and not START_PAYLOAD.fullmatch(payload)):
        raise ValueError('referralStart must be empty or 1-64 characters: A-Z, a-z, 0-9, _ and -')
    return payload


def telegram_url(bot, site=None, channel=None):
    """Build the destination from a validated username, never an arbitrary href."""
    username = bot.get('username', '')
    if not isinstance(username, str) or not USERNAME.fullmatch(username):
        raise ValueError('Invalid Telegram username')
    url = 'https://t.me/' + username[1:]
    payload = referral_start(bot)
    owned = site and bot['id'] == site.get('primaryBotId')
    if owned and payload:
        raise ValueError('The primary bot must use site.channels, not referralStart')
    if owned and channel and site.get('trackingEnabled'):
        if not site.get('startCompatibilityConfirmed'):
            raise ValueError('Confirm start compatibility before enabling tracking')
        payload = site.get('channels', {}).get(channel)
        if not isinstance(payload, str) or not START_PAYLOAD.fullmatch(payload):
            raise ValueError('Invalid channel payload')
    if payload:
        url += '?start=' + payload
    return url


def safe_https(value):
    if not isinstance(value, str) or any(c.isspace() or c in '<>"\\' for c in value):
        return False
    try:
        parts = urlsplit(value)
        return parts.scheme == 'https' and bool(parts.hostname) and not parts.username and not parts.password
    except ValueError:
        return False


def valid_time(value):
    try:
        return isinstance(value, str) and datetime.fromisoformat(value.replace('Z', '+00:00')).tzinfo is not None
    except ValueError:
        return False


def seed_errors(data):
    errors = []
    if not isinstance(data, dict) or data.get('schema_version') != 1 or not isinstance(data.get('bots'), list):
        return ['Expected schema_version=1 and a bots array']
    ids, usernames = set(), set()
    featured = 0
    for index, bot in enumerate(data['bots']):
        label = f'bot[{index}]'
        if not isinstance(bot, dict):
            errors.append(f'{label} must be an object')
            continue
        bid, username = bot.get('id'), bot.get('username')
        if not isinstance(bid, str) or not ID.fullmatch(bid):
            errors.append(f'{label} invalid lowercase id')
        elif bid in ids:
            errors.append(f'{label} duplicate id {bid}')
        else:
            ids.add(bid)
        placeholder = bot.get('category') == 'ai' and bot.get('url') is None and not username
        if not placeholder:
            if not isinstance(username, str) or not USERNAME.fullmatch(username):
                errors.append(f'{label} invalid username')
            else:
                key = username.lower()
                if key in usernames:
                    errors.append(f'{label} duplicate username {username}')
                usernames.add(key)
                if bot.get('url') != 'https://t.me/' + username[1:]:
                    errors.append(f'{label} url must match username and use https://t.me/; put the invitation payload in referralStart, not url')
        try:
            payload = referral_start(bot)
            if placeholder and payload:
                errors.append(f'{label} referralStart requires a Telegram username and url')
        except ValueError as exc:
            errors.append(f'{label} {exc}')
        if not isinstance(bot.get('category'), str) or bot['category'] not in VALID_CATEGORIES:
            errors.append(f'{label} invalid category')
        sub = bot.get('subsection')
        if sub is not None and not isinstance(sub, str):
            errors.append(f'{label} invalid subsection')
        elif bot.get('category') == 'group' and sub not in (None, 'verify', 'ads', 'stats', 'misc'):
            errors.append(f'{label} invalid group subsection')
        for field in ('featured', 'official'):
            if not isinstance(bot.get(field), bool):
                errors.append(f'{label} {field} must be boolean')
        featured += bot.get('featured') is True
        if not isinstance(bot.get('notes'), str) or not bot['notes'].strip() or len(bot['notes']) > 1000:
            errors.append(f'{label} notes must be nonempty text, at most 1000 characters')
        if 'name' in bot and (not isinstance(bot['name'], str) or not bot['name'].strip() or len(bot['name']) > 160):
            errors.append(f'{label} invalid name')
        tags = bot.get('tags', [])
        if not isinstance(tags, list) or len(tags) > 20 or any(not isinstance(t, str) or not t.strip() or len(t) > 40 for t in tags):
            errors.append(f'{label} invalid tags')
        if bot.get('officialUrl') and not safe_https(bot['officialUrl']):
            errors.append(f'{label} invalid officialUrl')
        fetch = bot.get('fetch')
        if not isinstance(fetch, dict):
            errors.append(f'{label} fetch must be object')
            continue
        if fetch.get('status') not in ('pending', 'ok', 'dead', 'error'):
            errors.append(f'{label} invalid fetch.status')
        for field in ('monthly_users', 'dead_streak'):
            value = fetch.get(field)
            if value is not None and (type(value) is not int or value < 0):
                errors.append(f'{label} invalid fetch.{field}')
        for field in ('title', 'description', 'error_msg'):
            if fetch.get(field) is not None and not isinstance(fetch[field], str):
                errors.append(f'{label} invalid fetch.{field}')
        for field in ('is_verified', 'not_bot'):
            if fetch.get(field) is not None and not isinstance(fetch[field], bool):
                errors.append(f'{label} invalid fetch.{field}')
        for field in ('fetched_at', 'checked_at', 'last_ok_at'):
            if fetch.get(field) is not None and not valid_time(fetch[field]):
                errors.append(f'{label} invalid fetch.{field}')
    if featured > 5:
        errors.append('At most five editorial featured bots')
    return errors


def site_errors(site, data, production=False):
    if not isinstance(site, dict):
        return ['Site config must be an object']
    errors = []
    for field in ('name', 'brand', 'description'):
        if not isinstance(site.get(field), str) or not site[field].strip():
            errors.append(f'Site {field} is required')
    public = site.get('publicUrl')
    if not isinstance(public, str):
        errors.append('publicUrl must be a string')
    elif public:
        try:
            parts = urlsplit(public)
        except ValueError:
            parts = None
        if not safe_https(public) or parts is None or parts.query or parts.fragment or not public.endswith('/'):
            errors.append('publicUrl must be an HTTPS URL ending in /, without query or fragment')
    elif production:
        errors.append('Set the real publicUrl before a production build')
    repo = site.get('repositoryUrl')
    if not isinstance(repo, str) or (repo and (not safe_https(repo) or not re.fullmatch(r'https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo))):
        errors.append('repositoryUrl must be empty or your GitHub repository URL')
    primary = next((b for b in data.get('bots', []) if b.get('id') == site.get('primaryBotId')), None)
    if not primary or is_hidden(primary) or not primary.get('url'):
        errors.append('primaryBotId must reference a visible bot')
    elif primary.get('referralStart'):
        errors.append('The primary bot must use site.channels, not referralStart')
    for field in ('trackingEnabled', 'startCompatibilityConfirmed'):
        if not isinstance(site.get(field), bool):
            errors.append(f'{field} must be boolean')
    if site.get('trackingEnabled') and not site.get('startCompatibilityConfirmed'):
        errors.append('start compatibility must be confirmed before tracking is enabled')
    channels = site.get('channels')
    required = {'home_featured', 'home_catalog', 'search_results', 'cat_search', 'guide_search', 'gh_readme'}
    if not isinstance(channels, dict) or not required.issubset(channels):
        errors.append('Missing channel mappings')
    else:
        values = list(channels.values())
        if any(not isinstance(v, str) or not START_PAYLOAD.fullmatch(v) for v in values):
            errors.append('Invalid start channel payload')
        # Several placements may intentionally share one backend source code.
    return errors
