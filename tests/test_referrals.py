"""Referral routing, disclosure and README regressions; no external requests."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import catalog
import build_site
import render_readme
import validate
import fetch_bots


class ReferralTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((catalog.ROOT / 'data/bots.json').read_text(encoding='utf-8'))
        self.site = catalog.load_site()
        self.bot = copy.deepcopy(next(b for b in self.data['bots'] if b['id'] != self.site['primaryBotId']))
        self.bot.update(id='ref_demo_bot', username='@ref_demo_bot', url='https://t.me/ref_demo_bot', referralStart='a_test-42', featured=False, category='search', subsection=None)
        self.data['bots'].append(self.bot)
        self.owned = next(b for b in self.data['bots'] if b['id'] == self.site['primaryBotId'])

    def test_referral_works_with_owned_tracking_disabled(self):
        self.site.update(trackingEnabled=False, startCompatibilityConfirmed=False)
        self.assertEqual(catalog.telegram_url(self.bot, self.site, 'search_results'), self.bot['url']+'?start=a_test-42')
        self.assertEqual(catalog.telegram_url(self.owned, self.site, 'search_results'), self.owned['url'])

    def test_owned_nav_0_is_independent_of_third_party_invitation(self):
        self.site.update(trackingEnabled=True, startCompatibilityConfirmed=True)
        self.site['channels'] = dict.fromkeys(self.site['channels'], 'nav_0')
        self.assertEqual(catalog.site_errors(self.site, self.data), [])
        for channel in self.site['channels']:
            self.assertEqual(catalog.telegram_url(self.owned, self.site, channel), self.owned['url']+'?start=nav_0')
            self.assertEqual(catalog.telegram_url(self.bot, self.site, channel), self.bot['url']+'?start=a_test-42')

    def test_empty_or_omitted_referral_keeps_normal_links(self):
        self.bot['referralStart'] = ''
        self.assertEqual(catalog.telegram_url(self.bot), self.bot['url'])
        del self.bot['referralStart']
        self.assertEqual(catalog.telegram_url(self.bot), self.bot['url'])

    def test_invalid_referral_payloads_fail_validation_and_generation(self):
        for value in (None, True, 123, [], {}, 'a'*65, '中文', 'a b', 'a\n', 'a&start=b', 'https://t.me/other', '?start=test', '<script>'):
            with self.subTest(value=value):
                self.bot['referralStart'] = value
                self.assertTrue(catalog.seed_errors(self.data))
                with self.assertRaises(ValueError):
                    catalog.telegram_url(self.bot)
        self.bot['referralStart'] = 'A9_-' * 16
        self.assertEqual(catalog.seed_errors(self.data), [])

    def test_base_url_still_cannot_override_username_or_embed_queries(self):
        for url in ('https://t.me/other_bot', 'https://t.me/ref_demo_bot?start=wrong', 'https://evil.example/ref_demo_bot'):
            self.bot['url'] = url
            self.assertTrue(catalog.seed_errors(self.data))

    def test_primary_cannot_combine_referral_with_source_parameters(self):
        self.owned['referralStart'] = 'a_test'
        self.assertTrue(catalog.site_errors(self.site, self.data))
        with self.assertRaises(ValueError):
            catalog.telegram_url(self.owned, self.site, 'home_featured')

    def test_cards_and_popularity_links_preserve_referrals_and_disclose(self):
        expected = self.bot['url']+'?start=a_test-42'
        for channel in ('home_catalog', 'search_results', 'cat_search'):
            card = BeautifulSoup(build_site.bot_card(self.bot, self.site, channel), 'html.parser')
            link = card.find('a')
            self.assertEqual(link['href'], expected)
            self.assertEqual(link['data-search-url'], expected)
            self.assertIn('sponsored', link['rel'])
            self.assertIn('邀请推广', card.get_text())
            self.assertIn(catalog.REFERRAL_DISCLOSURE, card.get_text())
        self.bot['fetch'].update(status='ok', monthly_users=100, not_bot=False)
        popular = BeautifulSoup(build_site.popular([self.bot], self.site), 'html.parser')
        self.assertEqual(popular.find('a')['href'], expected)
        self.assertIn('sponsored', popular.find('a')['rel'])
        self.assertIn('邀请推广', popular.get_text())
        owned = BeautifulSoup(build_site.bot_card(self.owned, self.site), 'html.parser')
        self.assertNotIn('邀请推广', owned.get_text())
        self.assertNotIn('sponsored', owned.find('a')['rel'])

    def test_readme_paths_use_the_same_link_and_disclosure(self):
        expected = self.bot['url']+'?start=a_test-42'
        for text in (render_readme.render_category_table_row(self.bot, self.site), render_readme.render_list_item(self.bot, self.site), render_readme.render_featured_table([self.bot], self.site), render_readme.render_category('search', [self.bot], self.site)):
            self.assertIn(']('+expected+')', text)
            self.assertIn('邀请推广', text)
            self.assertIn('邀请奖励', text)
        owned = render_readme.render_category_table_row(self.owned, self.site)
        expected_owned = catalog.telegram_url(self.owned, self.site, 'gh_readme')
        self.assertIn(']('+expected_owned+')', owned)

    def generated_readme(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)/'README.md'
            target.write_text((catalog.ROOT/'README.md').read_text(encoding='utf-8'), encoding='utf-8')
            with patch.object(render_readme, 'load_data', return_value=self.data), patch.object(render_readme, 'load_site', return_value=self.site), patch.object(render_readme, 'README_FILE', target), contextlib.redirect_stdout(io.StringIO()):
                render_readme.main()
            return target.read_text(encoding='utf-8')

    def test_readme_validation_detects_lost_or_replaced_start(self):
        text = self.generated_readme()
        expected = self.bot['url']+'?start=a_test-42'
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(validate.check_readme(self.data, text))
            self.assertTrue(validate.check_links(self.data, text, self.site))
            self.assertFalse(validate.check_links(self.data, text.replace(expected, self.bot['url']), self.site))
            self.assertFalse(validate.check_links(self.data, text.replace(expected, self.bot['url']+'?start=wrong'), self.site))

    def test_dead_and_nonbot_badges_survive_invitation_urls(self):
        for state in ('dead', 'notbot'):
            self.bot['fetch'].update(status='dead' if state=='dead' else 'ok', dead_streak=2 if state=='dead' else 0, not_bot=state=='notbot', page_kind='user')
            text = self.generated_readme()
            with patch.object(validate, 'load_site', return_value=self.site), contextlib.redirect_stdout(io.StringIO()):
                self.assertTrue(validate.check_dead(self.data, text))
                self.assertTrue(validate.check_notbot(self.data, text))

    def test_fetch_uses_public_username_without_referral_and_keeps_manual_field(self):
        html = '<div class="tgme_page_title">Demo</div><a class="tgme_action_button_new">Start Bot</a>'
        response = SimpleNamespace(status_code=200, text=html)
        with patch.object(fetch_bots, 'load_data', return_value=copy.deepcopy(self.data)), patch.object(fetch_bots, 'save_data') as save, patch.object(fetch_bots.requests, 'get', return_value=response) as get, patch.object(fetch_bots.time, 'sleep'), patch.object(sys, 'argv', ['fetch_bots.py', '--id', self.bot['id']]), contextlib.redirect_stdout(io.StringIO()):
            fetch_bots.main()
        self.assertEqual(get.call_args.args[0], self.bot['url'])
        saved = next(b for b in save.call_args.args[0]['bots'] if b['id']==self.bot['id'])
        self.assertEqual(saved['referralStart'], 'a_test-42')
        self.assertEqual(saved['url'], self.bot['url'])


if __name__ == '__main__':
    unittest.main()
