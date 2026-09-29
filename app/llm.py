"""Classification des marchands inconnus par un LLM (Claude).

Confidentialité : seuls les noms de marchands normalisés sont envoyés,
jamais les montants, dates, IBAN ou soldes.
"""
import json
import logging
import re

from .categories import CATEGORIES
from .config import settings

log = logging.getLogger(__name__)

_ALLOWED = [c for c in CATEGORIES if c not in ("revenus", "inconnu")]

SYSTEM_PROMPT = f"""Tu classes des marchands issus de relevés bancaires français.
Pour chaque marchand, choisis exactement une catégorie parmi :
{", ".join(_ALLOWED)}.
Si tu ne reconnais vraiment pas le marchand, réponds "inconnu".
Réponds UNIQUEMENT avec un objet JSON {{"marchand": "categorie", ...}},
sans texte autour ni balises Markdown."""


def _parse_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return {}
    return json.loads(text[start:end + 1])


def classify_merchants(merchants: list[str], batch_size: int = 60) -> dict[str, str]:
    if not settings.llm_enabled or not merchants:
        return {}
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    result: dict[str, str] = {}
    for i in range(0, len(merchants), batch_size):
        chunk = merchants[i:i + batch_size]
        try:
            msg = client.messages.create(
                model=settings.llm_model,
                max_tokens=2000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": json.dumps(chunk, ensure_ascii=False)}],
            )
            text = "".join(b.text for b in msg.content if b.type == "text")
            for merchant, cat in _parse_json(text).items():
                if merchant in chunk and cat in CATEGORIES:  # "inconnu" est aussi mis en cache
                    result[merchant] = cat
        except Exception as exc:  # le LLM ne doit jamais bloquer une synchro
            log.warning("Classification LLM échouée pour un lot : %s", exc)
    return result
