"""Cache misses should share one producer instead of stampeding a retailer."""

from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import sleep

from django.core.cache import cache
from django.test import SimpleTestCase

from apps.games.cache import cached


class CacheSingleFlightTests(SimpleTestCase):
    def tearDown(self):
        cache.clear()

    def test_concurrent_identical_misses_run_one_producer(self):
        calls = 0
        calls_lock = Lock()

        def producer():
            nonlocal calls
            with calls_lock:
                calls += 1
            sleep(0.03)
            return {"results": ["one shared response"]}

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _index: cached("single-flight:test", producer), range(8)))

        self.assertEqual(calls, 1)
        self.assertTrue(all(result == results[0] for result in results))

    def test_none_is_cached_as_a_negative_result(self):
        calls = 0

        def producer():
            nonlocal calls
            calls += 1
            return None

        self.assertIsNone(cached("single-flight:none", producer))
        self.assertIsNone(cached("single-flight:none", producer))
        self.assertEqual(calls, 1)
