"""Security and publication regressions. Offline; never contacts Telegram."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit, unquote
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import catalog
import build_site


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((catalog.ROOT / 'data/bots.json').read_text(encoding='utf-8'))
        self.site = catalog.load_site()

    def test_existing_short_usernames_are_valid(self):
        self.assertEqual(catalog.seed_errors(self.data), [])
        self.assertTrue(catalog.USERNAME.fullmatch('@jiso'))

    def test_bad_data_is_rejected_without_crashing(self):
        cases = [('username', 'not a username'), ('url', 'javascript:alert(1)'), ('notes', []), ('id', 'UPPER'), ('category', []), ('tags', ['valid', {}]), ('fetch', {'status':'ok','monthly_users':True})]
        for field, value in cases:
            with self.subTest(field=field):
                data = copy.deepcopy(self.data)
                data['bots'][0][field] = value
                self.assertTrue(catalog.seed_errors(data))

    def test_duplicate_usernames_ignore_case(self):
        data = copy.deepcopy(self.data)
        duplicate = copy.deepcopy(data['bots'][0])
        duplicate.update(id='another_id', username=duplicate['username'].upper())
        duplicate['url'] = 'https://t.me/' + duplicate['username'][1:]
        data['bots'].append(duplicate)
        self.assertTrue(any('duplicate username' in e for e in catalog.seed_errors(data)))

    def test_fetched_text_and_json_cannot_inject_markup(self):
        bot = copy.deepcopy(self.data['bots'][0])
        bot['name'] = '</script><img src=x onerror=alert(1)>'
        bot['notes'] = '<script>alert(1)</script>'
        markup = BeautifulSoup(build_site.bot_card(bot, self.site), 'html.parser')
        self.assertFalse(markup.find('img'))
        self.assertFalse(markup.find('script'))
        self.assertIn('<script>alert(1)</script>', markup.get_text())
        serialized = build_site.json_script({'name': bot['name']})
        self.assertNotIn('</script>', serialized)
        self.assertEqual(json.loads(serialized)['name'], bot['name'])

    def test_tracking_requires_explicit_compatibility(self):
        self.site['trackingEnabled'] = False
        self.site['startCompatibilityConfirmed'] = False
        bot = next(b for b in self.data['bots'] if b['id']==self.site['primaryBotId'])
        self.assertNotIn('start=', catalog.telegram_url(bot, self.site, 'home_featured'))
        self.site['trackingEnabled'] = True
        with self.assertRaises(ValueError):
            catalog.telegram_url(bot, self.site, 'home_featured')
        self.site['startCompatibilityConfirmed'] = True
        self.assertTrue(catalog.telegram_url(bot, self.site, 'home_featured').endswith('?start=nav_v1_home_featured'))

    def test_production_needs_real_origin(self):
        self.site['publicUrl'] = ''
        self.assertTrue(catalog.site_errors(self.site, self.data, production=True))

    def test_catalog_and_search_results_use_separate_owned_channels(self):
        self.site.update(trackingEnabled=True, startCompatibilityConfirmed=True)
        bot = next(b for b in self.data['bots'] if b['id']==self.site['primaryBotId'])
        card = BeautifulSoup(build_site.bot_card(bot, self.site), 'html.parser')
        link = card.find('a')
        self.assertTrue(link['href'].endswith('start=nav_v1_home_catalog'))
        self.assertTrue(link['data-search-url'].endswith('start=nav_v1_search_results'))

    def test_preview_and_subpath_production_have_correct_links_and_seo(self):
        for public in ('', 'https://example.org/navigation/'):
            with self.subTest(public=public), tempfile.TemporaryDirectory() as tmp:
                self.site['publicUrl'] = public
                output = Path(tmp)
                with patch.object(build_site, 'OUT', output), patch.object(build_site, 'load_site', return_value=self.site):
                    build_site.build(production=bool(public))
                for file in output.rglob('*.html'):
                    doc = BeautifulSoup(file.read_text(encoding='utf-8'), 'html.parser')
                    self.assertEqual(len(doc.find_all('h1')), 1)
                    self.assertTrue(doc.find('meta', attrs={'name':'description'})['content'])
                    canonical = doc.find('link', rel='canonical')
                    if public and file.name != '404.html':
                        self.assertTrue(canonical['href'].startswith(public))
                        self.assertIsNone(doc.find('meta', attrs={'name':'robots'}))
                        self.assertIsInstance(json.loads(doc.find('script', type='application/ld+json').string), dict)
                    else:
                        self.assertIsNone(canonical)
                        self.assertIn('noindex', doc.find('meta', attrs={'name':'robots'})['content'])
                    for tag in doc.select('[href],script[src]'):
                        value = tag.get('href', tag.get('src', ''))
                        parts = urlsplit(value)
                        if parts.scheme or parts.netloc: continue
                        if parts.path.startswith('/'):
                            base = urlsplit(public).path if public else '/'
                            self.assertTrue(parts.path.startswith(base))
                            target = output / parts.path[len(base):]
                        else:
                            target = file.parent / unquote(parts.path)
                        if not parts.path: target = file
                        if target.is_dir(): target = target / 'index.html'
                        self.assertTrue(target.exists(), f'{file}: broken link {value}')
                        if parts.fragment and target.suffix == '.html':
                            target_doc = BeautifulSoup(target.read_text(encoding='utf-8'), 'html.parser')
                            self.assertIsNotNone(target_doc.find(id=parts.fragment), f'missing #{parts.fragment}')
                home = BeautifulSoup((output/'index.html').read_text(encoding='utf-8'), 'html.parser')
                ids = [card['data-bot-id'] for card in home.select('[data-bot-id]')]
                visible = [b for b in self.data['bots'] if not catalog.is_hidden(b) and b.get('url')]
                self.assertEqual(len(ids), len(visible))
                self.assertEqual(len(ids), len(set(ids)))
                for b in visible:
                    if b.get('featured'): self.assertIn(b['id'], ids)
                urls = ET.parse(output/'sitemap.xml').findall('.//{*}loc')
                self.assertEqual(len(urls), 4 if public else 0)
                self.assertEqual((output/'LICENSE.txt').read_bytes(), (catalog.ROOT/'LICENSE').read_bytes())


if __name__ == '__main__':
    unittest.main()
