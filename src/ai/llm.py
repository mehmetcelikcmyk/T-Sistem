"""T-Sistem · TEK LLM istemcisi — Metin + Vision (Multimodal) Destekli.

ONCEKI DURUM
------------
* `evaluator.py` gecersiz bir model kimligi kullaniyordu (`claude-sonnet-4-6`),
  bu yuzden Anthropic katmani her anahtarda 404 aliyor ve `except: pass` ile
  sessizce atlaniyordu.
* `groq` paketi requirements.txt'te yoktu -> 2. katman tamamen oluydu.
* OpenAI icin yalnizca tekil `OPENAI_API_KEY` okunuyordu; `.env`'deki
  `OPENAI_API_KEYS` (3 anahtar) hicbir yerde kullanilmiyordu.
* `key_manager` 429 ile 401/404/JSON-parse hatasini ayirt etmiyordu; model
  yaniti bozuk diye UC anahtar birden tuketiliyordu.
* Hepsi basarisiz olunca `_generate_smart_heuristic_evaluation` devreye girip
  rapor icerigine BAKMADAN %82-92 arasi puan uretiyor, ustune sabit
  `confidence: 0.92` yaziyordu. Hakem bunun sahte oldugunu anlayamiyordu.

YENI DURUM
----------
* Saglayici sirasi ve model kimlikleri .env'den okunur.
* Her saglayicinin kendi anahtar havuzu vardir (virgulle ayrilmis).
* Hata siniflandirmasi:
    - RATE_LIMIT (429) / SERVER (5xx)  -> ayni saglayicida sonraki anahtar + backoff
    - AUTH (401/403)                   -> anahtari devre disi birak, sonrakine gec
    - MODEL (404/400 model)            -> modeli devre disi birak, sonraki modele gec
    - BAD_JSON                         -> ayni anahtarla onarim denemesi (anahtar yakilmaz)
* Tum saglayicilar basarisizsa `LLMUnavailable` FIRLATILIR. Sahte puan YOK.

MULTIMODAL (VISION)
-------------------
* `complete_multimodal_json()` metodu metin promptuna ek olarak gorsel listesi alir.
* Gorseller base64 kodlu olarak Anthropic vision API'sine gomulur (Claude Sonnet destekler).
* Groq / OpenAI vision desteklemiyorsa otomatik olarak gorsel OLMADAN metin moduna duser;
  gorseller prompt metnine etiket olarak eklenir ("Sayfa 3 — Sekil 1: [gorsel]").
* MAX_VISION_IMAGES: tek API cagrisinda gonderilebilecek maksimum gorsel (token/maliyet dengesi).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

log = logging.getLogger("tsistem.llm")

_DEFAULT_ORDER = ("anthropic", "groq", "openai")
_MAX_ATTEMPTS_PER_KEY = 2
_BACKOFF_BASE = 1.2

# Tek API cagrisinda gonderilebilecek maksimum gorsel sayisi
# (Anthropic: ~1600 token/gorsel, 12 gorsel ~19K token ek)
MAX_VISION_IMAGES = 12


class LLMError(RuntimeError):
    """LLM katmani hatalarinin tabani."""


class LLMUnavailable(LLMError):
    """Hicbir saglayici yanit veremedi. Cagiran taraf SAHTE VERI URETMEZ,
    kullaniciya acik uyari gosterir."""


class LLMBadJSON(LLMError):
    pass


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    attempts: int = 1
    elapsed_ms: float = 0.0
    vision_used: bool = False   # gorsel analizi yapildiysa True

    def json(self) -> Any:
        return _extract_json(self.text)


@dataclass
class _KeyState:
    value: str
    disabled: bool = False
    cooldown_until: float = 0.0
    failures: int = 0

    @property
    def usable(self) -> bool:
        return not self.disabled and time.time() >= self.cooldown_until


@dataclass
class _Provider:
    name: str
    models: list[str]
    keys: list[_KeyState] = field(default_factory=list)
    dead_models: set[str] = field(default_factory=set)

    @property
    def available(self) -> bool:
        return any(k.usable for k in self.keys) and any(
            m for m in self.models if m not in self.dead_models
        )


def _split_keys(*env_names: str) -> list[str]:
    seen: list[str] = []
    for name in env_names:
        raw = os.getenv(name, "")
        for part in raw.split(","):
            key = part.strip()
            if key and key not in seen:
                seen.append(key)
    return seen


# Vision destekleyen Anthropic model prefixleri
_ANTHROPIC_VISION_MODELS = (
    "claude-3",
    "claude-sonnet",
    "claude-opus",
    "claude-haiku",
)


def _model_supports_vision(provider: str, model: str) -> bool:
    """Bu model/saglayici kombinasyonu gorsel alabilir mi?"""
    if provider == "anthropic":
        return any(model.startswith(p) for p in _ANTHROPIC_VISION_MODELS)
    if provider == "openai":
        # gpt-4o ve gpt-4-vision gorsel destekler
        return "4o" in model or "vision" in model
    return False  # Groq metin modelleri gorsel desteklemez


class LLMClient:
    """Cok saglayicili, cok anahtarli, JSON + Vision odakli LLM istemcisi."""

    _lock = threading.Lock()

    def __init__(self) -> None:
        order = [
            p.strip().lower()
            for p in os.getenv("TSISTEM_LLM_ORDER", ",".join(_DEFAULT_ORDER)).split(",")
            if p.strip()
        ] or list(_DEFAULT_ORDER)

        catalog: dict[str, _Provider] = {
            "anthropic": _Provider(
                name="anthropic",
                models=_models_from_env(
                    "TSISTEM_ANTHROPIC_MODEL",
                    ["claude-sonnet-4-5-20250929", "claude-3-5-sonnet-20241022"],
                ),
                keys=[_KeyState(k) for k in _split_keys("ANTHROPIC_API_KEYS", "ANTHROPIC_API_KEY")],
            ),
            "groq": _Provider(
                name="groq",
                models=_models_from_env(
                    "TSISTEM_GROQ_MODEL",
                    ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
                ),
                keys=[_KeyState(k) for k in _split_keys("GROQ_API_KEYS", "GROQ_API_KEY")],
            ),
            "openai": _Provider(
                name="openai",
                models=_models_from_env("TSISTEM_OPENAI_MODEL", ["gpt-4o-mini", "gpt-4o"]),
                keys=[_KeyState(k) for k in _split_keys("OPENAI_API_KEYS", "OPENAI_API_KEY")],
            ),
        }
        self.providers = [catalog[name] for name in order if name in catalog]
        self._rr: dict[str, int] = {p.name: 0 for p in self.providers}

    # ── durum ─────────────────────────────────────────────────────────────
    @property
    def available(self) -> bool:
        return any(p.available for p in self.providers)

    def status(self) -> list[dict[str, Any]]:
        return [
            {
                "provider": p.name,
                "keys_total": len(p.keys),
                "keys_usable": sum(1 for k in p.keys if k.usable),
                "models": [m for m in p.models if m not in p.dead_models],
                "available": p.available,
            }
            for p in self.providers
        ]

    # ── genel API ─────────────────────────────────────────────────────────
    def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.2,
        json_mode: bool = False,
        images: list[dict[str, Any]] | None = None,
    ) -> LLMResult:
        """Tek turlu tamamlama. `images` verilirse gorsel destekleyen saglayicida
        vision API kullanilir; desteklemiyorsa gorsel etiketleri metne eklenir."""
        if not self.available:
            raise LLMUnavailable(
                "Hicbir LLM saglayicisi yapilandirilmamis. .env icinde "
                "ANTHROPIC_API_KEYS / GROQ_API_KEYS / OPENAI_API_KEYS tanimlayiniz."
            )

        errors: list[str] = []
        started = time.time()
        attempts = 0
        vision_used = False

        for provider in self.providers:
            if not provider.available:
                errors.append(f"{provider.name}: kullanilabilir anahtar/model yok")
                continue
            for model in [m for m in provider.models if m not in provider.dead_models]:
                for _ in range(len(provider.keys)):
                    key = self._next_key(provider)
                    if key is None:
                        break
                    attempts += 1

                    # Vision destegi varsa gorsel gonder, yoksa metin fallback
                    use_vision = bool(images) and _model_supports_vision(provider.name, model)
                    effective_images = images[:MAX_VISION_IMAGES] if use_vision else None
                    effective_prompt = prompt
                    if images and not use_vision:
                        # Gorsel desteklemeyen modelde gorsel etiketlerini metne ekle
                        labels = "\n".join(
                            f"  [{img.get('label', f'Gorsel {i+1}')}]"
                            for i, img in enumerate(images[:MAX_VISION_IMAGES])
                        )
                        effective_prompt = (
                            f"{prompt}\n\n"
                            f"NOT: Bu raporda {len(images)} gorsel/sekil bulunmaktadir "
                            f"(mevcut model gorsel analizi desteklememektedir):\n{labels}"
                        )

                    try:
                        text = self._call(
                            provider.name, model, key.value, effective_prompt,
                            system=system, max_tokens=max_tokens,
                            temperature=temperature, json_mode=json_mode,
                            images=effective_images,
                        )
                        key.failures = 0
                        vision_used = use_vision
                        return LLMResult(
                            text=text, provider=provider.name, model=model,
                            attempts=attempts,
                            elapsed_ms=(time.time() - started) * 1000,
                            vision_used=vision_used,
                        )
                    except _Retryable as exc:
                        key.failures += 1
                        key.cooldown_until = time.time() + _BACKOFF_BASE * (2 ** min(key.failures, 4))
                        errors.append(f"{provider.name}/{model}: {exc}")
                        log.warning("[llm] gecici hata %s/%s: %s", provider.name, model, exc)
                    except _AuthError as exc:
                        key.disabled = True
                        errors.append(f"{provider.name}: anahtar reddedildi ({exc})")
                        log.error("[llm] anahtar devre disi %s: %s", provider.name, exc)
                    except _ModelError as exc:
                        provider.dead_models.add(model)
                        errors.append(f"{provider.name}/{model}: model gecersiz ({exc})")
                        log.error("[llm] model devre disi %s/%s: %s", provider.name, model, exc)
                        break
                    except _Fatal as exc:
                        errors.append(f"{provider.name}/{model}: {exc}")
                        break

        raise LLMUnavailable(
            "Tum LLM saglayicilari basarisiz oldu:\n  - " + "\n  - ".join(errors[-8:])
        )

    def complete_json(
        self,
        prompt: str,
        *,
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.1,
        validator: Callable[[Any], Any] | None = None,
        repair_attempts: int = 2,
    ) -> tuple[Any, LLMResult]:
        """JSON dondurur. Bozuk JSON gelirse ONARIM ister (anahtar yakilmaz)."""
        return self._complete_json_internal(
            prompt, system=system, max_tokens=max_tokens,
            temperature=temperature, validator=validator,
            repair_attempts=repair_attempts, images=None,
        )

    def complete_multimodal_json(
        self,
        prompt: str,
        images: list[dict[str, Any]],
        *,
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.1,
        validator: Callable[[Any], Any] | None = None,
        repair_attempts: int = 2,
    ) -> tuple[Any, LLMResult]:
        """Metin + gorsel iceren JSON tamamlama.

        `images`: images_to_base64() ciktisi —
            [{"mime_type": "image/png", "data": "<base64>", "label": "...", ...}]

        Vision destekleyen ilk saglayicida gorsel analizi yapilir.
        Hicbiri desteklemiyorsa gorsel etiketleri prompt metnine eklenir
        ve standart metin modu kullanilir — islem HIC durmaz.
        """
        return self._complete_json_internal(
            prompt, system=system, max_tokens=max_tokens,
            temperature=temperature, validator=validator,
            repair_attempts=repair_attempts, images=images,
        )

    def _complete_json_internal(
        self,
        prompt: str,
        *,
        system: str,
        max_tokens: int,
        temperature: float,
        validator: Callable[[Any], Any] | None,
        repair_attempts: int,
        images: list[dict[str, Any]] | None,
    ) -> tuple[Any, LLMResult]:
        current_prompt = prompt
        last_error = ""
        for attempt in range(repair_attempts + 1):
            result = self.complete(
                current_prompt, system=system, max_tokens=max_tokens,
                temperature=temperature, json_mode=True,
                images=images if attempt == 0 else None,  # onarim denemesinde gorsel yok
            )
            try:
                payload = _extract_json(result.text)
            except LLMBadJSON as exc:
                last_error = str(exc)
                current_prompt = (
                    f"{prompt}\n\n"
                    f"ONCEKI YANIT GECERLI JSON DEGILDI ({last_error}). "
                    f"YALNIZCA gecerli JSON dondur, aciklama ve kod bloğu ekleme."
                )
                continue

            if validator is not None:
                try:
                    return validator(payload), result
                except Exception as exc:  # noqa: BLE001
                    last_error = str(exc)
                    current_prompt = (
                        f"{prompt}\n\n"
                        f"ONCEKI YANIT SEMAYA UYMADI: {last_error}\n"
                        f"Semaya birebir uyan gecerli JSON dondur."
                    )
                    continue
            return payload, result

        raise LLMBadJSON(f"JSON {repair_attempts + 1} denemede uretilemedi. Son hata: {last_error}")

    # ── ic calisma ────────────────────────────────────────────────────────
    def _next_key(self, provider: _Provider) -> _KeyState | None:
        with self._lock:
            usable = [k for k in provider.keys if k.usable]
            if not usable:
                return None
            idx = self._rr[provider.name] % len(usable)
            self._rr[provider.name] = idx + 1
            return usable[idx]

    def _call(
        self, provider: str, model: str, api_key: str, prompt: str, *,
        system: str, max_tokens: int, temperature: float, json_mode: bool,
        images: list[dict[str, Any]] | None = None,
    ) -> str:
        if provider == "anthropic":
            return _call_anthropic(
                model, api_key, prompt, system, max_tokens, temperature,
                images=images,
            )
        if provider == "groq":
            return _call_openai_compatible(
                "https://api.groq.com/openai/v1/chat/completions",
                model, api_key, prompt, system, max_tokens, temperature, json_mode,
            )
        if provider == "openai":
            return _call_openai_compatible(
                "https://api.openai.com/v1/chat/completions",
                model, api_key, prompt, system, max_tokens, temperature, json_mode,
                images=images if _model_supports_vision("openai", model) else None,
            )
        raise _Fatal(f"Bilinmeyen saglayici: {provider}")


# ── hata siniflari (ic kullanim) ───────────────────────────────────────────
class _Retryable(Exception):
    pass


class _AuthError(Exception):
    pass


class _ModelError(Exception):
    pass


class _Fatal(Exception):
    pass


def _models_from_env(env_name: str, defaults: list[str]) -> list[str]:
    raw = os.getenv(env_name, "")
    models = [m.strip() for m in raw.split(",") if m.strip()]
    for d in defaults:
        if d not in models:
            models.append(d)
    return models


def _classify(status: int, body: str) -> Exception:
    lowered = body.lower()
    if status in (401, 403):
        return _AuthError(f"HTTP {status}")
    if status == 404 or ("model" in lowered and ("not found" in lowered or "does not exist" in lowered)):
        return _ModelError(f"HTTP {status}: {body[:160]}")
    if status == 429 or "rate limit" in lowered or "overloaded" in lowered:
        return _Retryable(f"HTTP {status} (hiz siniri)")
    if status >= 500:
        return _Retryable(f"HTTP {status} (sunucu)")
    if status == 400 and "model" in lowered:
        return _ModelError(f"HTTP 400: {body[:160]}")
    return _Fatal(f"HTTP {status}: {body[:200]}")


def _post(url: str, headers: dict[str, str], body: dict[str, Any], timeout: int = 120) -> dict[str, Any]:
    payload = json.dumps(body).encode("utf-8")
    try:
        import requests  # type: ignore

        resp = requests.post(url, data=payload, headers=headers, timeout=timeout)
        if resp.status_code >= 400:
            raise _classify(resp.status_code, resp.text)
        return resp.json()
    except ImportError:
        import urllib.error
        import urllib.request

        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise _classify(exc.code, exc.read().decode("utf-8", errors="replace")) from exc
        except urllib.error.URLError as exc:
            raise _Retryable(f"ag hatasi: {exc}") from exc


def _call_anthropic(
    model: str, api_key: str, prompt: str, system: str,
    max_tokens: int, temperature: float,
    images: list[dict[str, Any]] | None = None,
) -> str:
    """Anthropic Messages API — metin veya metin+gorsel."""
    # Icerik blogu olustur
    if images:
        content: list[dict[str, Any]] = []
        # Once gorselleri ekle (Anthropic: gorsel once, metin sonra okunur daha iyi)
        for img in images[:MAX_VISION_IMAGES]:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": img.get("mime_type", "image/png"),
                    "data": img["data"],
                },
            })
        # Gorsel etiketlerini prompt'un basina ekle
        label_lines = "\n".join(
            f"  [{img.get('label', f'Gorsel {i+1}')}]"
            for i, img in enumerate(images[:MAX_VISION_IMAGES])
        )
        full_prompt = (
            f"Asagidaki {len(images[:MAX_VISION_IMAGES])} gorsel/sekil raporda yer almaktadir "
            f"ve degerlendirmende dikkate alinmalidir:\n{label_lines}\n\n{prompt}"
        )
        content.append({"type": "text", "text": full_prompt})
    else:
        content = prompt  # type: ignore[assignment]

    body: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": content}],
    }
    if system:
        body["system"] = system

    data = _post(
        "https://api.anthropic.com/v1/messages",
        {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        body,
        timeout=180,  # gorsel analizi daha uzun surebilir
    )
    blocks = data.get("content") or []
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    if not text.strip():
        raise _Retryable("bos yanit")
    return text


def _call_openai_compatible(
    url: str, model: str, api_key: str, prompt: str, system: str,
    max_tokens: int, temperature: float, json_mode: bool,
    images: list[dict[str, Any]] | None = None,
) -> str:
    messages: list[dict[str, Any]] = []
    if system:
        messages.append({"role": "system", "content": system})

    if images and _model_supports_vision("openai", model):
        # OpenAI vision format
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for img in images[:MAX_VISION_IMAGES]:
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{img.get('mime_type', 'image/png')};base64,{img['data']}",
                    "detail": "high",
                },
            })
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": prompt})

    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if json_mode and not images:
        body["response_format"] = {"type": "json_object"}
    data = _post(url, {"Authorization": f"Bearer {api_key}",
                       "Content-Type": "application/json"}, body)
    choices = data.get("choices") or []
    if not choices:
        raise _Retryable("bos yanit")
    text = (choices[0].get("message") or {}).get("content") or ""
    if not text.strip():
        raise _Retryable("bos icerik")
    return text


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _extract_json(text: str) -> Any:
    """Model yanitindan JSON cikarir (kod blogu, on/arka metin toleransli)."""
    candidate = text.strip()
    fence = _FENCE.search(candidate)
    if fence:
        candidate = fence.group(1).strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        log.debug("[llm] duz JSON cozulemedi, kirpma denenecek: %s", exc)
    for opener, closer in (("{", "}"), ("[", "]")):
        start = candidate.find(opener)
        end = candidate.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(candidate[start:end + 1])
            except json.JSONDecodeError:
                continue
    raise LLMBadJSON("Yanit icinde gecerli JSON bulunamadi.")


_client: LLMClient | None = None


def get_llm() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client


def reset_llm() -> None:
    global _client
    _client = None


__all__ = [
    "LLMClient", "LLMResult", "get_llm", "reset_llm",
    "LLMError", "LLMUnavailable", "LLMBadJSON",
    "MAX_VISION_IMAGES",
]
