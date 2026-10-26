#!/usr/bin/env python3
"""
validate.py - Self-check script for bots data pipeline.

Per SPEC §4 Task D (M5):
- --check seed   : bots.json schema, required fields, id unique, category valid, featured <=5
- --check readme : markers paired, every non-dead json bot rendered in some marker block,
                   no stray/old bot links left inside marker blocks
- --check links  : every https://t.me/xxx inside marker blocks matches a bot's url in json
- --check dead   : every visible dead bot entry is rendered with "已失效" / ❗ marker;
                   entries dead for HIDE_AFTER consecutive checks must NOT be rendered
- --check notbot : live pages that are not bots (fetch.not_bot) carry a ⚠️ marker;
                   prints a warning listing them so maintainers can review/remove
- (no arg)       : run ALL checks; exit 0 only if every check passes
"""

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit
from catalog import HIDE_AFTER, is_hidden, seed_errors, site_errors, load_site, telegram_url

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "bots.json"
README_FILE = ROOT / "README.md"


def load_bots():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_readme():
    with open(README_FILE, "r", encoding="utf-8") as f:
        return f.read()


def check_seed(data):
    """--check seed"""
    errors = seed_errors(data)
    if errors:
        print('SEED CHECK FAILED:\n  - ' + '\n  - '.join(errors))
        return False
    print(f"SEED CHECK PASSED: {len(data['bots'])} bots")
    return True


def extract_marker_inners(readme: str) -> dict:
    """Return dict of marker_name -> inner text between start/end (markers themselves excluded)."""
    inners = {}
    marker_names = [
        "last-verified",
        "bots-primary",
        "bots-featured",
        "bots-category:search",
        "bots-category:group",
        "bots-category:download",
        "bots-category:ai",
        "bots-category:rss",
        "bots-category:tools",
        "bots-category:translate",
        "bots-category:checkin",
        "bots-category:channel",
        "bots-category:game",
    ]
    for m in marker_names:
        start = f"<!-- AUTO:{m}:start -->"
        end = f"<!-- AUTO:{m}:end -->"
        s = readme.find(start)
        e = readme.find(end, s + 1) if s >= 0 else -1
        if s >= 0 and e > s:
            inner = readme[s + len(start): e]
            inners[m] = inner
    return inners


def find_marker_pairs(readme: str):
    """Return list of (marker, has_pair) and overall ok."""
    errors = []
    marker_names = [
        "last-verified", "bots-primary", "bots-featured",
        "bots-category:search", "bots-category:group", "bots-category:download",
        "bots-category:ai", "bots-category:rss", "bots-category:tools",
        "bots-category:translate", "bots-category:checkin", "bots-category:channel",
        "bots-category:game",
    ]
    for m in marker_names:
        start = f"<!-- AUTO:{m}:start -->"
        end = f"<!-- AUTO:{m}:end -->"
        sc = readme.count(start)
        ec = readme.count(end)
        if sc != 1 or ec != 1:
            errors.append(f"marker {m} not exactly one start+end pair (start={sc}, end={ec})")
        elif readme.find(start) > readme.find(end):
            errors.append(f"marker {m} end appears before start")
    return errors


def collect_rendered_urls(inners: dict) -> set:
    """Retain the entire destination: losing/changing start must fail validation."""
    return {url for inner in inners.values()
            for url in re.findall(r'\]\((https://t\.me/[^\s)]+)\)', inner)}


def check_readme(data, readme):
    """--check readme : pairs + coverage (non-dead must appear) + no residual old links"""
    errors = []

    # pairs
    pair_errs = find_marker_pairs(readme)
    errors.extend(pair_errs)

    inners = extract_marker_inners(readme)
    rendered_urls = {urlsplit(url)._replace(query='', fragment='').geturl()
                     for url in collect_rendered_urls(inners)}

    # visible (non-hidden) bots must be present in rendered; hidden ones must not
    non_dead_urls = set()
    visible_urls = set()
    hidden_urls = set()
    for b in data.get("bots", []):
        u = b.get("url")
        if not u:
            continue
        if is_hidden(b):
            hidden_urls.add(u)
            continue
        visible_urls.add(u)
        if b.get("fetch", {}).get("status") != "dead":
            non_dead_urls.add(u)

    missing = visible_urls - rendered_urls
    if missing:
        errors.append(f"visible bots missing from rendered marker blocks: {sorted(missing)}")

    leaked = hidden_urls & rendered_urls
    if leaked:
        errors.append(f"hidden bots (dead x{HIDE_AFTER}+) still rendered: {sorted(leaked)}")

    # stray / old urls inside markers that are not visible json bots
    stray = rendered_urls - visible_urls - hidden_urls
    if stray:
        errors.append(f"stray/old bot links inside marker blocks not in json: {sorted(stray)}")

    if errors:
        print("README CHECK FAILED:")
        for e in errors:
            print(f"  - {e}")
        return False
    print(f"README CHECK PASSED: {len(non_dead_urls)} non-dead bots covered in markers, no stray links")
    return True


def check_links(data, readme, site=None):
    """--check links : marker-block urls must exactly correspond to json urls (consistency)"""
    errors = []
    inners = extract_marker_inners(readme)
    rendered_urls = collect_rendered_urls(inners)

    if site is None:
        site = load_site()
    expected = {telegram_url(b, site, 'gh_readme')
                for b in data.get('bots', []) if b.get('url') and not is_hidden(b)}

    for u in sorted(rendered_urls):
        if u not in expected:
            errors.append(f"rendered destination differs from configured bot/start: {u}")
    for u in sorted(expected - rendered_urls):
        errors.append(f"configured bot/start destination missing from README: {u}")

    # Also ensure every json url that should render appears (covered by readme check too)
    # But for links we focus on "all rendered == known"
    if errors:
        print("LINKS CHECK FAILED:")
        for e in errors:
            print(f"  - {e}")
        return False
    print(f"LINKS CHECK PASSED: {len(rendered_urls)} destinations match configured bots and start payloads")
    return True


def check_dead(data, readme):
    """--check dead : dead bots must carry failure marker in their rendered line"""
    errors = []
    inners = extract_marker_inners(readme)
    combined = "\n".join(inners.values())

    dead_bots = [b for b in data.get("bots", [])
                 if b.get("fetch", {}).get("status") == "dead" and not is_hidden(b)]

    for b in dead_bots:
        bid = b["id"]
        u = b.get("username", "").lstrip("@")
        url = telegram_url(b, load_site(), 'gh_readme') if b.get('url') else ''
        # Must appear and contain failure indicator near it
        # Look for the url or username + 已失效 / ❗
        if url and url in combined:
            # find surrounding context
            lines = [line for line in combined.splitlines() if f']({url})' in line]
            if not lines or any('已失效' not in line and '❗' not in line for line in lines):
                errors.append(f"dead bot {bid} rendered but missing '已失效' / ❗ marker")
        else:
            # not even the link? still fail (though readme check may catch for non-dead, dead are optional in readme spec but we render them)
            errors.append(f"dead bot {bid} link not found in any marker block (should still be shown with failure note)")

    if errors:
        print("DEAD CHECK FAILED:")
        for e in errors:
            print(f"  - {e}")
        return False
    print(f"DEAD CHECK PASSED: {len(dead_bots)} dead bot(s) correctly marked")
    return True


def check_notbot(data, readme):
    """--check notbot : not_bot entries must carry the ⚠️ marker; list them as a warning"""
    errors = []
    inners = extract_marker_inners(readme)
    combined = "\n".join(inners.values())
    flagged = [b for b in data.get("bots", [])
               if (b.get("fetch") or {}).get("status") == "ok" and (b.get("fetch") or {}).get("not_bot")
               and not is_hidden(b)]
    for b in flagged:
        url = telegram_url(b, load_site(), 'gh_readme') if b.get('url') else ''
        line = next((ln for ln in combined.splitlines() if url and f"({url})" in ln), None)
        if line is None or "⚠️" not in line:
            errors.append(f"not_bot entry {b['id']} rendered without ⚠️ marker")
    if errors:
        print("NOTBOT CHECK FAILED:")
        for e in errors:
            print(f"  - {e}")
        return False
    if flagged:
        kinds = ", ".join(f"{b['id']}({b['fetch'].get('page_kind')})" for b in flagged)
        print(f"WARNING: {len(flagged)} entr(y/ies) no longer look like bots, review/remove: {kinds}")
        if __import__("os").environ.get("GITHUB_ACTIONS"):
            print(f"::warning title=not_bot entries::{kinds}")
    print(f"NOTBOT CHECK PASSED: {len(flagged)} not_bot entr(y/ies) marked")
    return True


def main():
    parser = argparse.ArgumentParser(description="Validate bots data and pipeline state (M4/M5)")
    parser.add_argument("--check", choices=["seed", "readme", "links", "dead", "notbot"], help="Run specific check (default = all)")
    args = parser.parse_args()

    try:
        data = load_bots()
    except Exception as e:
        print(f"Failed to load {DATA_FILE}: {e}")
        sys.exit(2)

    try:
        readme = load_readme()
    except Exception as e:
        print(f"Failed to load {README_FILE}: {e}")
        sys.exit(2)

    ok = True

    preflight = seed_errors(data)
    if preflight:
        print('Invalid catalog:\n  - ' + '\n  - '.join(preflight))
        sys.exit(1)

    checks_to_run = []
    if args.check is None:
        checks_to_run = ["seed", "readme", "links", "dead", "notbot"]
    else:
        checks_to_run = [args.check]

    for chk in checks_to_run:
        if chk == "seed":
            ok = check_seed(data) and ok
        elif chk == "readme":
            ok = check_readme(data, readme) and ok
        elif chk == "links":
            ok = check_links(data, readme) and ok
        elif chk == "dead":
            ok = check_dead(data, readme) and ok
        elif chk == "notbot":
            ok = check_notbot(data, readme) and ok

    config_errors = site_errors(load_site(), data)
    if config_errors:
        print('SITE CONFIG FAILED:\n  - ' + '\n  - '.join(config_errors))
        ok = False

    if args.check is None:
        if ok:
            print("FULL VALIDATION PASSED (all checks).")
        else:
            print("FULL VALIDATION FAILED (see above).")

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
