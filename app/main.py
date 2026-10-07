"""Point d'entrée : uvicorn app.main:app --reload"""
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import classifier, db, demo, insights
from .categories import CATEGORIES
from .config import settings
from .enable_banking import EnableBankingClient, EnableBankingError, normalize_transaction

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("budget")

STATIC = Path(__file__).with_name("static")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Budget DSP2", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")

_pending_auth: dict[str, str] = {}  # state -> nom de la banque (usage mono-utilisateur)


def _client() -> EnableBankingClient:
    if not settings.bank_enabled:
        raise HTTPException(400, "Enable Banking n'est pas configuré : renseigne .env et keys/private.pem.")
    return EnableBankingClient()


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/status")
def status():
    return {
        "bank_enabled": settings.bank_enabled,
        "llm_enabled": settings.llm_enabled,
        "accounts": db.rows(
            "SELECT uid, bank, name, iban, valid_until, last_sync, "
            "session_id IS NOT NULL AS connected FROM accounts"
        ),
        "months": insights.available_months(),
    }


@app.get("/api/categories")
def categories():
    return [{"id": k, **v} for k, v in CATEGORIES.items()]


# --- Connexion bancaire -------------------------------------------------------

@app.get("/api/banks")
def banks(country: str = settings.eb_country):
    try:
        return [{"name": b["name"], "country": b["country"],
                 "max_days": b.get("maximum_consent_validity")} for b in _client().list_banks(country)]
    except EnableBankingError as exc:
        raise HTTPException(502, str(exc))


class ConnectBody(BaseModel):
    bank: str
    country: str = settings.eb_country


@app.post("/api/connect")
def connect(body: ConnectBody):
    state = str(uuid.uuid4())
    try:
        auth = _client().start_auth(body.bank, body.country, state)
    except EnableBankingError as exc:
        raise HTTPException(502, str(exc))
    _pending_auth[state] = body.bank
    return {"url": auth["url"]}


@app.get("/callback")
def callback(code: str | None = None, state: str | None = None, error: str | None = None):
    if error or not code:
        return RedirectResponse(f"/?error={error or 'consentement_refuse'}")
    bank = _pending_auth.pop(state, "Banque") if state else "Banque"
    client = _client()
    try:
        session = client.create_session(code)
    except EnableBankingError as exc:
        log.error(exc)
        return RedirectResponse("/?error=session")

    valid_until = (session.get("access") or {}).get("valid_until")
    for acc in session.get("accounts", []):
        uid = acc["uid"] if isinstance(acc, dict) else acc
        info = acc if isinstance(acc, dict) else {}
        db.upsert_account({
            "uid": uid,
            "session_id": session["session_id"],
            "bank": bank,
            "name": info.get("name") or info.get("product") or "Compte",
            "iban": (info.get("account_id") or {}).get("iban", ""),
            "currency": info.get("currency", "EUR"),
            "valid_until": valid_until,
        })
    sync()
    return RedirectResponse("/?connected=1")


# --- Synchronisation ----------------------------------------------------------

@app.post("/api/sync")
def sync():
    accounts = [a for a in db.rows("SELECT * FROM accounts") if a["session_id"]]
    if not accounts:
        return {"inserted": 0, "classified": classifier.classify_pending(), "errors": []}

    client = _client()
    inserted, errors = 0, []
    for acc in accounts:
        last = db.rows("SELECT MAX(date) AS d FROM transactions WHERE account_uid = ?", (acc["uid"],))[0]["d"]
        # On repart quelques jours en arrière : certaines opérations arrivent en retard
        date_from = ((date.fromisoformat(last) - timedelta(days=7)) if last
                     else date.today() - timedelta(days=settings.history_days)).isoformat()
        try:
            batch = []
            for raw in client.iter_transactions(acc["uid"], date_from):
                tx = normalize_transaction(raw, acc["uid"])
                if tx:
                    batch.append(tx)
            inserted += db.insert_transactions(batch)
            with db.connect() as con:
                con.execute("UPDATE accounts SET last_sync = ? WHERE uid = ?",
                            (datetime.now(timezone.utc).isoformat(timespec="seconds"), acc["uid"]))
        except EnableBankingError as exc:
            log.error(exc)
            errors.append({"account": acc["name"], "error": str(exc)[:300]})

    return {"inserted": inserted, "classified": classifier.classify_pending(), "errors": errors}


@app.post("/api/demo")
def load_demo():
    inserted = demo.load_demo()
    return {"inserted": inserted, "classified": classifier.classify_pending()}


@app.post("/api/reclassify")
def reclassify():
    """À lancer après avoir modifié rules.yaml."""
    classifier.load_rules.cache_clear()
    return {"classified": classifier.classify_pending(force=True)}


# --- Lecture et corrections ---------------------------------------------------

@app.get("/api/summary")
def summary(month: str | None = None):
    months = insights.available_months()
    if not months:
        return {"month": None, "transactions": [], "insights": []}
    return insights.monthly_summary(month or months[0])


class OverrideBody(BaseModel):
    category: str
    nature: str | None = None


@app.put("/api/merchants/{merchant}")
def override(merchant: str, body: OverrideBody):
    if body.category not in CATEGORIES:
        raise HTTPException(400, "Catégorie inconnue")
    return {"updated": classifier.apply_user_override(merchant, body.category, body.nature)}
