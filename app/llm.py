"""Classification des marchands inconnus et conseils budgétaires par un LLM (Ollama en local, Claude ou Gemini).

Confidentialité : pour la classification, seuls les noms de marchands normalisés sont
envoyés, jamais les montants, dates, IBAN ou soldes. Pour les conseils (sur demande
uniquement), seuls des totaux agrégés par mois et par catégorie, sans aucun marchand.
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


def _chat_anthropic(system: str, user: str, max_tokens: int = 2000, temperature: float = 0,
                    timeout: float = 600) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=timeout)
    msg = client.messages.create(
        model=settings.llm_model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in msg.content if b.type == "text")


def _chat_ollama(system: str, user: str, max_tokens: int = 2000, temperature: float = 0,
                 timeout: float = 180) -> str:
    # API compatible OpenAI exposée par Ollama : https://github.com/ollama/ollama/blob/main/docs/openai.md
    resp = requests.post(
        f"{settings.ollama_base_url}/v1/chat/completions",
        json={
            "model": settings.llm_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _chat_gemini(system: str, user: str, max_tokens: int = 2000, temperature: float = 0,
                 timeout: float = 60) -> str:
    # https://ai.google.dev/api/generate-content
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.llm_model}:generateContent"
    headers = {"x-goog-api-key": settings.gemini_api_key}
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"parts": [{"text": user}]}],
        # Pas de maxOutputTokens : sur les modèles « thinking », le raisonnement y est décompté
        # et tronquerait la réponse ; max_tokens n'est donc pas transmis à Gemini.
        "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
    }
    resp = requests.post(url, headers=headers, json=body, timeout=timeout)
    if resp.status_code == 503:
        # Le mode JSON strict est parfois en surcharge côté Google ("high demand") ;
        # on retente sans, en comptant sur _parse_json pour extraire l'objet malgré tout.
        del body["generationConfig"]["responseMimeType"]
        resp = requests.post(url, headers=headers, json=body, timeout=timeout)
    if resp.status_code == 503:
        # Toujours en surcharge : un bref backoff suffit en général (pic temporaire).
        time.sleep(3)
        resp = requests.post(url, headers=headers, json=body, timeout=timeout)
    resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


_CHAT = {
    "anthropic": _chat_anthropic,
    "ollama": _chat_ollama,
    "gemini": _chat_gemini,
}


def classify_merchants(merchants: list[str], batch_size: int = 60) -> dict[str, str]:
    if not settings.llm_enabled or not merchants:
        return {}
    chat = _CHAT[settings.llm_provider]
    if settings.llm_provider == "ollama":
        # Un petit modèle local génère ~10 tokens/s (un lot de 60 dépasse le timeout HTTP),
        # et oublie parfois une entrée sur de longs lots : 10 par lot reste fiable.
        batch_size = min(batch_size, 10)

    result: dict[str, str] = {}
    for i in range(0, len(merchants), batch_size):
        chunk = merchants[i:i + batch_size]
        try:
            answer = _parse_json(chat(SYSTEM_PROMPT, json.dumps(chunk, ensure_ascii=False)))
            for merchant, cat in answer.items():
                if merchant in chunk and cat in CATEGORIES:  # "inconnu" est aussi mis en cache
                    result[merchant] = cat
        except Exception as exc:  # le LLM ne doit jamais bloquer une synchro
            log.warning("Classification LLM (%s) échouée pour un lot : %s", settings.llm_provider, exc)
    return result


ADVICE_PROMPT = """Tu es un conseiller budgétaire bienveillant et concret pour un particulier en France.
Tu reçois en JSON des totaux mensuels agrégés de son compte courant (en euros) :
entrées (salaires, remboursements), sorties (consommation, hors épargne et virements
internes), solde = entrées - sorties, épargne versée, et les dépenses moyennes par
catégorie avec leur nature (essentiel / optimisable) et leur évolution en % entre la
première et la seconde moitié de la période.

Fais une synthèse de 2 à 4 phrases : dépense-t-il plus qu'il ne gagne, quels mois ou
quelles catégories expliquent l'écart. Puis donne 3 à 5 conseils actionnables et chiffrés,
en priorité sur les dépenses optimisables. Tutoie, reste factuel, n'invente aucun chiffre
absent des données.

Réponds UNIQUEMENT avec un objet JSON, sans texte autour ni balises Markdown :
{"synthese": "...", "conseils": ["...", "..."]}"""


# Rédiger une synthèse prend bien plus longtemps que classer des noms (modèles « thinking »
# hébergés : > 60 s observé avec Gemini ; petit modèle local à ~10 tokens/s).
ADVICE_TIMEOUT = 300


def advise(context: dict) -> dict | None:
    """Synthèse et conseils sur des agrégats (jamais de marchands ni de libellés)."""
    if not settings.llm_enabled:
        return None
    try:
        text = _CHAT[settings.llm_provider](
            ADVICE_PROMPT, json.dumps(context, ensure_ascii=False), max_tokens=1200, temperature=0.3,
            timeout=ADVICE_TIMEOUT)
    except Exception as exc:
        log.warning("Conseils LLM (%s) échoués : %s", settings.llm_provider, exc)
        return None
    answer = _parse_json(text)
    if isinstance(answer.get("synthese"), str):
        tips = answer.get("conseils")
        return {"synthese": answer["synthese"].strip(),
                "conseils": [str(t).strip() for t in tips if str(t).strip()] if isinstance(tips, list) else []}
    text = text.strip()
    return {"synthese": text, "conseils": []} if text else None
