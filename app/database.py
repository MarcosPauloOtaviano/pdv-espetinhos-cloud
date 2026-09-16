"""Camada de acesso ao SQLite: conexao, criacao de schema e seed inicial."""
import sqlite3
from contextlib import contextmanager

from app.utils import get_db_path, now_iso, hash_password

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin', 'caixa', 'garcom', 'cozinha')),
    active INTEGER NOT NULL DEFAULT 1,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_secrets (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id INTEGER,
    action TEXT NOT NULL,
    username TEXT,
    details TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category_id INTEGER REFERENCES categories(id),
    price REAL NOT NULL CHECK(price >= 0),
    cost REAL DEFAULT 0,
    track_stock INTEGER NOT NULL DEFAULT 0,
    stock REAL DEFAULT 0,
    low_stock_threshold REAL DEFAULT 5,
    active INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cash_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    opening_amount REAL NOT NULL DEFAULT 0,
    operator_name TEXT,
    open_notes TEXT,
    status TEXT NOT NULL DEFAULT 'aberto' CHECK(status IN ('aberto', 'fechado')),
    counted_amount REAL,
    expected_amount REAL,
    difference REAL,
    close_notes TEXT,
    closed_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cash_movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cash_session_id INTEGER NOT NULL REFERENCES cash_sessions(id),
    type TEXT NOT NULL CHECK(type IN ('sangria', 'reforco')),
    amount REAL NOT NULL CHECK(amount > 0),
    reason TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number INTEGER NOT NULL,
    customer_name TEXT,
    table_ref TEXT,
    status TEXT NOT NULL DEFAULT 'aberto'
        CHECK(status IN ('aberto', 'aguardando_pagamento', 'paga', 'cancelada', 'fiado')),
    discount REAL NOT NULL DEFAULT 0,
    notes TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    cash_session_id INTEGER REFERENCES cash_sessions(id),
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    created_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS command_access_credentials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    command_id INTEGER NOT NULL REFERENCES commands(id),
    nonce TEXT NOT NULL UNIQUE,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    created_by TEXT,
    revoked_at TEXT,
    revoked_by TEXT,
    replaced_by_id INTEGER REFERENCES command_access_credentials(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_command_access_one_active
ON command_access_credentials(command_id)
WHERE active = 1;

CREATE TABLE IF NOT EXISTS command_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    command_id INTEGER NOT NULL REFERENCES commands(id),
    product_id INTEGER REFERENCES products(id),
    product_name TEXT NOT NULL,
    unit_price REAL NOT NULL,
    quantity REAL NOT NULL CHECK(quantity > 0),
    subtotal REAL NOT NULL,
    notes TEXT,
    kitchen_status TEXT NOT NULL DEFAULT 'pendente'
        CHECK(kitchen_status IN ('pendente', 'preparando', 'pronto', 'entregue')),
    created_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    command_id INTEGER NOT NULL REFERENCES commands(id),
    method TEXT NOT NULL CHECK(method IN ('dinheiro', 'pix', 'debito', 'credito')),
    amount REAL NOT NULL CHECK(amount > 0),
    received_amount REAL,
    change_amount REAL,
    pix_confirmed INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT NOT NULL
);
"""

DEFAULT_SETTINGS = {
    "establishment_name": "Espetinho DU'DAIR",
    "pix_key": "",
    "pix_receiver_name": "ESPETINHO DUDAIR",
    "pix_city": "SAO PAULO",
    "pix_description": "Pagamento Espetinho DU'DAIR",
    "theme": "dark",
}

DEFAULT_DEMO_USERS = [
    ("caixa", "caixa123", "caixa"),
    ("garcom", "garcom123", "garcom"),
    ("cozinha", "cozinha123", "cozinha"),
]

DEFAULT_CATEGORIES = ["Espetinhos", "Bebidas", "Marmitas", "Porcoes", "Adicionais"]

DEFAULT_PRODUCTS = [
    ("Espetinho de vaca", "Espetinhos", 8.0, 4.0, 1, 40),
    ("Espetinho de frango", "Espetinhos", 7.0, 3.5, 1, 40),
    ("Espetinho de coracao", "Espetinhos", 7.5, 3.5, 1, 30),
    ("Coca-Cola lata", "Bebidas", 6.0, 3.2, 1, 30),
    ("Guarana lata", "Bebidas", 6.0, 3.2, 1, 30),
    ("Agua", "Bebidas", 3.0, 1.0, 1, 40),
    ("Marmita do dia", "Marmitas", 18.0, 9.0, 1, 15),
    ("Porcao de mandioca", "Porcoes", 15.0, 6.0, 1, 20),
    ("Vinagrete extra", "Adicionais", 2.0, 0.5, 0, 0),
]


def _connect():
    conn = sqlite3.connect(str(get_db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_connection():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Cria as tabelas se nao existirem e popula dados iniciais (idempotente)."""
    with get_connection() as conn:
        conn.executescript(SCHEMA)

        ts = now_iso()

        cur = conn.execute("SELECT COUNT(*) c FROM users")
        if cur.fetchone()["c"] == 0:
            conn.execute(
                "INSERT INTO users (username, password_hash, role, active, must_change_password, created_at, updated_at) "
                "VALUES (?, ?, 'admin', 1, 1, ?, ?)",
                ("admin", hash_password("admin123"), ts, ts),
            )
            for username, password, role in DEFAULT_DEMO_USERS:
                conn.execute(
                    "INSERT INTO users (username, password_hash, role, active, must_change_password, created_at, updated_at) "
                    "VALUES (?, ?, ?, 1, 1, ?, ?)",
                    (username, hash_password(password), role, ts, ts),
                )

        cur = conn.execute("SELECT COUNT(*) c FROM categories")
        if cur.fetchone()["c"] == 0:
            for name in DEFAULT_CATEGORIES:
                conn.execute(
                    "INSERT INTO categories (name, created_at, updated_at) VALUES (?, ?, ?)",
                    (name, ts, ts),
                )

        cur = conn.execute("SELECT COUNT(*) c FROM products")
        if cur.fetchone()["c"] == 0:
            cat_rows = conn.execute("SELECT id, name FROM categories").fetchall()
            cat_map = {row["name"]: row["id"] for row in cat_rows}
            for name, cat_name, price, cost, track_stock, stock in DEFAULT_PRODUCTS:
                conn.execute(
                    "INSERT INTO products (name, category_id, price, cost, track_stock, stock, "
                    "low_stock_threshold, active, notes, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, 5, 1, '', ?, ?)",
                    (name, cat_map.get(cat_name), price, cost, track_stock, stock, ts, ts),
                )

        cur = conn.execute("SELECT COUNT(*) c FROM settings")
        if cur.fetchone()["c"] == 0:
            for key, value in DEFAULT_SETTINGS.items():
                conn.execute(
                    "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                    (key, value, ts),
                )
