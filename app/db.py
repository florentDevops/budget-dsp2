"""Stockage SQLite minimal (un seul fichier, zéro serveur)."""
import sqlite3
from contextlib import contextmanager

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    uid          TEXT PRIMARY KEY,
    session_id   TEXT,
    bank         TEXT,
    name         TEXT,
    iban         TEXT,
    currency     TEXT,
    valid_until  TEXT,
    last_sync    TEXT
);

CREATE TABLE IF NOT EXISTS transactions (
    id            TEXT PRIMARY KEY,
    account_uid   TEXT NOT NULL,
    date          TEXT NOT NULL,          -- YYYY-MM-DD (date de comptabilisation)
    amount        REAL NOT NULL,          -- négatif = dépense, positif = entrée
    currency      TEXT DEFAULT 'EUR',
    label         TEXT,                   -- libellé brut de la banque
    counterparty  TEXT,
    mcc           TEXT,
    merchant      TEXT,                   -- marchand normalisé (clé de regroupement)
    category      TEXT,
    nature        TEXT,
    class_source  TEXT                    -- user | rule | mcc | llm | default
);
CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_tx_merchant ON transactions(merchant);

-- Classification mémorisée par marchand : corrections utilisateur et cache LLM
CREATE TABLE IF NOT EXISTS merchant_overrides (
    merchant  TEXT PRIMARY KEY,
    category  TEXT NOT NULL,
    nature    TEXT,                       -- NULL = nature par défaut de la catégorie
    source    TEXT NOT NULL               -- user | llm
);
"""


def init_db() -> None:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect() as con:
        con.executescript(SCHEMA)


@contextmanager
def connect():
    con = sqlite3.connect(settings.db_path)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def rows(sql: str, params: tuple = ()) -> list[dict]:
    with connect() as con:
        return [dict(r) for r in con.execute(sql, params).fetchall()]


def upsert_account(acc: dict) -> None:
    with connect() as con:
        con.execute(
            """INSERT INTO accounts (uid, session_id, bank, name, iban, currency, valid_until)
               VALUES (:uid, :session_id, :bank, :name, :iban, :currency, :valid_until)
               ON CONFLICT(uid) DO UPDATE SET session_id=excluded.session_id,
                   valid_until=excluded.valid_until""",
            acc,
        )


def insert_transactions(txs: list[dict]) -> int:
    """Insère sans écraser l'existant (les corrections manuelles sont préservées)."""
    with connect() as con:
        before = con.total_changes
        con.executemany(
            """INSERT OR IGNORE INTO transactions
               (id, account_uid, date, amount, currency, label, counterparty, mcc, merchant)
               VALUES (:id, :account_uid, :date, :amount, :currency, :label,
                       :counterparty, :mcc, :merchant)""",
            txs,
        )
        return con.total_changes - before


def get_overrides() -> dict[str, dict]:
    return {r["merchant"]: r for r in rows("SELECT * FROM merchant_overrides")}


def save_override(merchant: str, category: str, nature: str | None, source: str) -> None:
    with connect() as con:
        con.execute(
            """INSERT INTO merchant_overrides (merchant, category, nature, source)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(merchant) DO UPDATE SET category=excluded.category,
                   nature=excluded.nature, source=excluded.source""",
            (merchant, category, nature, source),
        )


def set_classification(updates: list[tuple]) -> None:
    """updates = [(category, nature, source, tx_id), ...]"""
    with connect() as con:
        con.executemany(
            "UPDATE transactions SET category=?, nature=?, class_source=? WHERE id=?", updates
        )
