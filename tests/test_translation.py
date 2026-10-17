import unittest

from repo_monitor.translation import AzureTranslator, GoogleCloudTranslator, TranslationService, cache_key


class TranslationTests(unittest.TestCase):
    def test_disabled_is_network_free(self):
        def unexpected(*args):
            raise AssertionError("network must not be called")
        service = TranslationService(AzureTranslator("x", transport=unexpected),
                                     GoogleCloudTranslator("x", transport=unexpected))
        self.assertEqual(service.translate("hello").status, "original")

    def test_fallback_and_cache(self):
        calls = []
        def fail(*args):
            calls.append("azure")
            raise TimeoutError("offline")
        def google(url, headers, payload):
            calls.append("google")
            return {"data": {"translations": [{"translatedText": "こんにちは"}]}}
        service = TranslationService(AzureTranslator("x", transport=fail),
                                     GoogleCloudTranslator("x", transport=google),
                                     admission=lambda provider, count: True, enabled=True)
        first = service.translate("hello")
        second = service.translate("hello")
        self.assertEqual((first.provider, first.translated), ("google", "こんにちは"))
        self.assertEqual(second.status, "cached")
        self.assertEqual(calls, ["azure", "google"])

    def test_no_admission_no_call(self):
        def unexpected(*args):
            raise AssertionError("network must not be called")
        service = TranslationService(AzureTranslator("x", transport=unexpected),
                                     GoogleCloudTranslator("x", transport=unexpected),
                                     admission=lambda provider, count: False, enabled=True)
        self.assertEqual(service.translate("hello").status, "original")

    def test_cache_separates_provider_and_policy(self):
        a = cache_key("hello", "en", "ja", "azure", "standard")
        b = cache_key("hello", "en", "ja", "google", "nmt")
        c = cache_key("hello", "en", "ja", "azure", "standard", "v2")
        self.assertEqual(len({a, b, c}), 3)


if __name__ == "__main__":
    unittest.main()
