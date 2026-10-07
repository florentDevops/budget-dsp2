"""Classification des marchands inconnus par un LLM (Ollama en local, Claude ou Gemini).

Confidentialité : seuls les noms de marchands normalisés sont envoyés,
jamais les montants, dates, IBAN ou soldes.
"""
import json
import logging
import re
import time

import requests

from .categories import CATEGORIES
from .config import settings

log = logging.getLogger(__name__)

_ALLOWED = [c for c in CATEGORIES if c not in ("revenus", "inconnu")]

SYSTEM_PROMPT = f"""Tu classes des marchands issus de relevés bancaires français.
Pour chaque marchand, choisis exactement une catégorie parmi :
{", ".join(_ALLOWED)}.
Si tu ne reconnais vraiment pas le marchand, réponds "inconnu".

Réponds UNIQUEMENT avec un objet JSON dont chaque clé est un nom de marchand
REPRIS EXACTEMENT TEL QUEL depuis la liste fournie (jamais le mot "marchand"
littéralement, même s'il n'y a qu'un seul marchand), et chaque valeur une
catégorie choisie ci-dessus. Pas de texte autour, pas de balises Markdown.

Exemple - entrée : ["CARREFOUR MARKET"]
Exemple - sortie : {{"CARREFOUR MARKET": "courses"}}"""


def _parse_json(text: str) -> dict:
    # Un petit modèle local répète parfois sa réponse (deux objets JSON à la suite) :
    # on ne décode que le premier objet valide et on ignore ce qui suit.
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start = text.find("{")
    if start == -1:
        return {}
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError:
        return {}
    return obj if isinstance(obj, dict) else {}


def _classify_chunk_anthropic(chunk: list[str]) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    msg = client.messages.create(
        model=settings.llm_model,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": json.dumps(chunk, ensure_ascii=False)}],
    )
    text = "".join(b.text for b in msg.content if b.type == "text")
    return _parse_json(text)


def _classify_chunk_ollama(chunk: list[str]) -> dict:
    # API compatible OpenAI exposée par Ollama : https://github.com/ollama/ollama/blob/main/docs/openai.md
    resp = requests.post(
        f"{settings.ollama_base_url}/v1/chat/completions",
        json={
            "model": settings.llm_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(chunk, ensure_ascii=False)},
            ],
            "temperature": 0,
            "stream": False,
        },
        timeout=180,
    )
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"]
    return _parse_json(text)


def _classify_chunk_gemini(chunk: list[str]) -> dict:
    # https://ai.google.dev/api/generate-content
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.llm_model}:generateContent"
    headers = {"x-goog-api-key": settings.gemini_api_key}
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": json.dumps(chunk, ensure_ascii=False)}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }
    resp = requests.post(url, headers=headers, json=body, timeout=60)
    if resp.status_code == 503:
        # Le mode JSON strict est parfois en surcharge côté Google ("high demand") ;
        # on retente sans, en comptant sur _parse_json pour extraire l'objet malgré tout.
        del body["generationConfig"]["responseMimeType"]
        resp = requests.post(url, headers=headers, json=body, timeout=60)
    if resp.status_code == 503:
        # Toujours en surcharge : un bref backoff suffit en général (pic temporaire).
        time.sleep(3)
        resp = requests.post(url, headers=headers, json=body, timeout=60)
    resp.raise_for_status()
    text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    return _parse_json(text)


_CLASSIFY_CHUNK = {
    "anthropic": _classify_chunk_anthropic,
    "ollama": _classify_chunk_ollama,
    "gemini": _classify_chunk_gemini,
}


def classify_merchants(merchants: list[str], batch_size: int = 60) -> dict[str, str]:
    if not settings.llm_enabled or not merchants:
        return {}
    classify_chunk = _CLASSIFY_CHUNK[settings.llm_provider]
    if settings.llm_provider == "ollama":
        # Un petit modèle local génère ~10 tokens/s (un lot de 60 dépasse le timeout HTTP),
        # et oublie parfois une entrée sur de longs lots : 10 par lot reste fiable.
        batch_size = min(batch_size, 10)

    result: dict[str, str] = {}
    for i in range(0, len(merchants), batch_size):
        chunk = merchants[i:i + batch_size]
        try:
            for merchant, cat in classify_chunk(chunk).items():
                if merchant in chunk and cat in CATEGORIES:  # "inconnu" est aussi mis en cache
                    result[merchant] = cat
        except Exception as exc:  # le LLM ne doit jamais bloquer une synchro
            log.warning("Classification LLM (%s) échouée pour un lot : %s", settings.llm_provider, exc)
    return result
