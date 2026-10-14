"""Stockage SQLite minimal (un seul fichier, zéro serveur)."""
import sqlite3
from contextlib import contextmanager

from .config import settings
from .normalize import is_cheque, merchant_key

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
    merchant      TEXT,                   -- marchand normalisé (nom affiché)
    merchant_key  TEXT,                   -- clé technique A-Z0-9 (regroupement, URL)
    category      TEXT,
    nature        TEXT,
    class_source  TEXT,                   -- user | rule | mcc | llm | default
    user_category TEXT,                   -- correction manuelle : source de vérité, jamais écrasée
    user_nature   TEXT                    --   par un reclassement (NULL = nature par défaut)
);
CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(date);

-- Classification mémorisée par marchand : cache LLM, et règles utilisateur déduites des
-- transactions corrigées (reconstruites au démarrage, voir _sync_merchant_keys)
CREATE TABLE IF NOT EXISTS merchant_overrides (
    merchant_key  TEXT PRIMARY KEY,
    category      TEXT NOT NULL,
    nature        TEXT,                   -- NULL = nature par défaut de la catégorie
    source        TEXT NOT NULL           -- user | llm
);
"""

_OVERRIDES_TABLE = SCHEMA[SCHEMA.index("CREATE TABLE IF NOT EXISTS merchant_overrides"):]


def init_db() -> None:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect() as con:
        _migrate(con)
        con.executescript(SCHEMA)
        con.execute("CREATE INDEX IF NOT EXISTS idx_tx_merchant_key ON transactions(merchant_key)")
        _sync_merchant_keys(con)
        _reset_auto_classified_cheques(con)


def _reset_auto_classified_cheques(con: sqlite3.Connection) -> None:
    """Chèques émis classés automatiquement (le LLM en mettait en frais bancaires) : remis
    « à classer », et leur cache LLM supprimé. Les corrections manuelles sont intactes."""
    bad = [(i, k) for i, k, label in con.execute(
        """SELECT id, merchant_key, label FROM transactions
           WHERE amount < 0 AND class_source IN ('rule', 'mcc', 'llm')""") if is_cheque(label or "")]
    con.executemany(
        "UPDATE transactions SET category='inconnu', nature='inconnu', class_source='default' WHERE id=?",
        [(i,) for i, _ in bad])
    con.executemany("DELETE FROM merchant_overrides WHERE merchant_key=? AND source='llm'",
                    [(k,) for _, k in bad])


def _sync_merchant_keys(con: sqlite3.Connection) -> None:
    """Si merchant_key() a évolué, recalcule les clés stockées puis reconstruit les règles
    utilisateur depuis les transactions corrigées : aucune correction manuelle n'est perdue."""
    stale = [(merchant_key(m or ""), i)
             for i, m, k in con.execute("SELECT id, merchant, merchant_key FROM transactions")
             if k != merchant_key(m or "")]
    con.executemany("UPDATE transactions SET merchant_key=? WHERE id=?", stale)
    # Par marchand, la correction la plus récente (par date d'opération) fait la règle
    latest = con.execute(
        """SELECT merchant_key, user_category, user_nature FROM transactions
           WHERE user_category IS NOT NULL ORDER BY date, id""").fetchall()
    for key, category, nature in {r[0]: r for r in latest}.values():
        save_override(key, category, nature, "user", con)


def _migrate(con: sqlite3.Connection) -> None:
    """Bases anciennes : avant merchant_key (le nom affiché servait de clé), et avant
    user_category (les corrections manuelles ne vivaient que dans merchant_overrides)."""
    tx_cols = {r[1] for r in con.execute("PRAGMA table_info(transactions)")}
    if tx_cols and "merchant_key" not in tx_cols:
        con.execute("ALTER TABLE transactions ADD COLUMN merchant_key TEXT")
        # Au passage, retire du nom affiché les tokens de pure ponctuation ("CARDIF / /")
        updates = []
        for i, m in con.execute("SELECT id, merchant FROM transactions").fetchall():
            name = " ".join(t for t in (m or "").split() if any(c.isalnum() for c in t)) or m
            updates.append((name, merchant_key(name or ""), i))
        con.executemany("UPDATE transactions SET merchant=?, merchant_key=? WHERE id=?", updates)
    if tx_cols and "user_category" not in tx_cols:
        con.execute("ALTER TABLE transactions ADD COLUMN user_category TEXT")
        con.execute("ALTER TABLE transactions ADD COLUMN user_nature TEXT")
        con.execute("""UPDATE transactions SET user_category=category, user_nature=nature
                       WHERE class_source='user'""")
    ov_cols = {r[1] for r in con.execute("PRAGMA table_info(merchant_overrides)")}
    if ov_cols and "merchant_key" not in ov_cols:
        old = con.execute("SELECT merchant, category, nature, source FROM merchant_overrides").fetchall()
        con.execute("DROP TABLE merchant_overrides")
        con.executescript(_OVERRIDES_TABLE)
        # Deux anciens noms peuvent partager une clé : une correction manuelle prime sur le LLM
        for m, category, nature, source in sorted(old, key=lambda r: r[3] == "user"):
            save_override(merchant_key(m or ""), category, nature, source, con)


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
               (id, account_uid, date, amount, currency, label, counterparty, mcc, merchant, merchant_key)
               VALUES (:id, :account_uid, :date, :amount, :currency, :label,
                       :counterparty, :mcc, :merchant, :merchant_key)""",
            [{**t, "merchant_key": merchant_key(t["merchant"])} for t in txs],
        )
        return con.total_changes - before


def get_overrides() -> dict[str, dict]:
    return {r["merchant_key"]: r for r in rows("SELECT * FROM merchant_overrides")}


def save_override(key: str, category: str, nature: str | None, source: str,
                  con: sqlite3.Connection | None = None) -> None:
    sql = """INSERT INTO merchant_overrides (merchant_key, category, nature, source)
             VALUES (?, ?, ?, ?)
             ON CONFLICT(merchant_key) DO UPDATE SET category=excluded.category,
                 nature=excluded.nature, source=excluded.source"""
    if con is not None:
        con.execute(sql, (key, category, nature, source))
        return
    with connect() as c:
        c.execute(sql, (key, category, nature, source))


def set_classification(updates: list[tuple]) -> None:
    """updates = [(category, nature, source, tx_id), ...]"""
    with connect() as con:
        con.executemany(
            "UPDATE transactions SET category=?, nature=?, class_source=? WHERE id=?", updates
        )
