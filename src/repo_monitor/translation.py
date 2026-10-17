"""Optional, fail-open translation core. No network call unless explicitly configured.

Presentation only: never feed translated content into devflow authority or automation.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Callable
from urllib import request, parse, error


@dataclass(frozen=True)
class Translation:
    original: str
    translated: str | None
    status: str
    provider: str | None = None


class ProviderError(Exception):
    pass


def cache_key(text: str, source: str, target: str, provider: str, model: str, policy: str = "v1") -> str:
    payload = json.dumps([text, source, target, provider, model, policy], ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _post_json(url: str, headers: dict[str, str], payload: object, timeout: float = 5.0) -> object:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(url, data=data, headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return json.load(response)
    except (error.HTTPError, error.URLError, TimeoutError, ValueError) as exc:
        raise ProviderError(type(exc).__name__) from exc


class AzureTranslator:
    name = "azure"
    model = "standard"

    def __init__(self, key: str, region: str = "", transport: Callable = _post_json):
        self.key, self.region, self.transport = key, region, transport

    def translate(self, text: str, source: str, target: str) -> str:
        if not self.key:
            raise ProviderError("not_configured")
        params = {"api-version": "3.0", "to": target}
        if source != "auto":
            params["from"] = source
        headers = {"Ocp-Apim-Subscription-Key": self.key}
        if self.region:
            headers["Ocp-Apim-Subscription-Region"] = self.region
        result = self.transport("https://api.cognitive.microsofttranslator.com/translate?" + parse.urlencode(params), headers, [{"Text": text}])
        try:
            return result[0]["translations"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("invalid_response") from exc


class GoogleCloudTranslator:
    name = "google"
    model = "nmt"

    def __init__(self, key: str, transport: Callable = _post_json):
        self.key, self.transport = key, transport

    def translate(self, text: str, source: str, target: str) -> str:
        if not self.key:
            raise ProviderError("not_configured")
        payload = {"q": text, "target": target, "format": "text", "model": "nmt"}
        if source != "auto":
            payload["source"] = source
        result = self.transport("https://translation.googleapis.com/language/translate/v2?key=" + parse.quote(self.key, safe=""), {}, payload)
        try:
            return result["data"]["translations"][0]["translatedText"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("invalid_response") from exc


class TranslationService:
    """In-memory cache and Azure-first fallback; caller owns quota/admission.

    No API call occurs unless enabled=True AND provider admission explicitly passes.
    """

    def __init__(self, azure: AzureTranslator, google: GoogleCloudTranslator,
                 admission: Callable[[str, int], bool] | None = None, enabled: bool = False):
        self.providers = (azure, google)
        self.admission = admission
        self.enabled = enabled
        self.cache: dict[str, str] = {}

    def translate(self, text: str, source: str = "auto", target: str = "ja") -> Translation:
        if not text or not self.enabled or self.admission is None:
            return Translation(text, None, "original")
        for provider in self.providers:
            key = cache_key(text, source, target, provider.name, provider.model)
            if key in self.cache:
                return Translation(text, self.cache[key], "cached", provider.name)
            # Fail closed on unproven quota: never call a provider without admission.
            if not self.admission(provider.name, len(text)):
                continue
            try:
                translated = provider.translate(text, source, target)
                if not isinstance(translated, str) or not translated.strip():
                    raise ProviderError("empty_response")
                self.cache[key] = translated
                return Translation(text, translated, "translated", provider.name)
            except (ProviderError, TimeoutError, OSError, ValueError):
                continue
        return Translation(text, None, "original")
