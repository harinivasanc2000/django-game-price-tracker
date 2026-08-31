"""Remote news fields must stay text/data, never executable page links."""

from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from apps.games.clients.news import _steam_news_uncached


class SteamNewsSafetyTests(SimpleTestCase):
    @patch("apps.games.clients.news.requests.get")
    def test_news_rejects_non_http_link_schemes(self, get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "appnews": {
                "newsitems": [
                    {"title": "Unsafe", "url": "javascript:alert(1)"},
                    {
                        "title": "Safe",
                        "url": "https://store.steampowered.com/news/example",
                    },
                ]
            }
        }
        get.return_value = response

        rows = _steam_news_uncached(123, count=2, deals_only=False)

        self.assertEqual(rows[0]["url"], "")
        self.assertEqual(rows[1]["url"], "https://store.steampowered.com/news/example")
