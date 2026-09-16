"""
Camada de servicos / regras de negocio do PDV DU'DAIR.
Toda a UI (desktop ou servidor HTTP) fala com o banco atraves destas
funcoes - nunca SQL direto nas telas.
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from app.database import get_connection
from app.utils import now_iso, today_str, hash_password, verify_password

SESSION_TTL_HOURS = 12
ROLES = ("admin", "caixa", "garcom", "cozinha")
KITCHEN_STATUS_LABELS = {
    "pendente": "Pendente",
    "preparando": "Preparando",
    "pronto": "Pronto",
    "entregue": "Entregue",
}

PAYMENT_METHOD_LABELS = {
    "dinheiro": "Dinheiro",
    "pix": "Pix",
    "debito": "Cartao de Debito",
    "credito": "Cartao de Credito",
}

STATUS_LABELS = {
    "aberto": "Em aberto",
    "aguardando_pagamento": "Aguardando pagamento",
    "paga": "Paga",
    "cancelada": "Cancelada",
    "fiado": "Fiado / Pendente",
}


class ServiceError(Exception):
    """Erro de regra de negocio, deve ser mostrado ao usuario numa messagebox."""


def _audit(conn, entity_type: str, entity_id, action: str, actor: str = "", details: str = ""):
    """Registra uma linha de auditoria na MESMA transacao da mutacao (nunca falha o caso principal)."""
    conn.execute(
        "INSERT INTO audit_log (entity_type, entity_id, action, username, details, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (entity_type, entity_id, action, actor or "", details or "", now_iso()),
    )


def _bump_command_version(conn, command_id: int):
    conn.execute("UPDATE commands SET version = version + 1 WHERE id = ?", (command_id,))


def list_audit_log(limit: int = 200, entity_type: str = None, entity_id: int = None):
    sql = "SELECT * FROM audit_log WHERE 1=1"
    params = []
    if entity_type:
        sql += " AND entity_type = ?"
        params.append(entity_type)
    if entity_id is not None:
        sql += " AND entity_id = ?"
        params.append(entity_id)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


# ----------------------------------------------------------------------
# Usuarios / autenticacao / sessoes
# ----------------------------------------------------------------------

def authenticate(username: str, password: str):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? AND active = 1", (username,)
        ).fetchone()
        if row and verify_password(password, row["password_hash"]):
            return dict(row)
        return None


def create_session(user_id: int, ttl_hours: int = SESSION_TTL_HOURS) -> str:
    token = secrets.token_urlsafe(32)
    ts = now_iso()
    expires = (datetime.now() + timedelta(hours=ttl_hours)).strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, user_id, ts, expires),
        )
    return token


def get_user_by_token(token: str):
    if not token:
        return None
    with get_connection() as conn:
        row = conn.execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.token = ? AND s.expires_at > ? AND u.active = 1",
            (token, now_iso()),
        ).fetchone()
        return dict(row) if row else None


def revoke_session(token: str):
    with get_connection() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def cleanup_expired_sessions():
    with get_connection() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now_iso(),))


def list_users():
    with get_connection() as conn:
        rows = conn.execute("SELECT id, username, role, active, must_change_password FROM users ORDER BY username").fetchall()
        return [dict(r) for r in rows]


def create_user(username: str, password: str, role: str):
    username = (username or "").strip()
    if not username:
        raise ServiceError("Informe um nome de usuario.")
    if role not in ROLES:
        raise ServiceError("Perfil invalido.")
    if not password or len(password) < 4:
        raise ServiceError("A senha deve ter ao menos 4 caracteres.")
    ts = now_iso()
    with get_connection() as conn:
        exists = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if exists:
            raise ServiceError("Ja existe um usuario com esse nome.")
        conn.execute(
            "INSERT INTO users (username, password_hash, role, active, must_change_password, created_at, updated_at) "
            "VALUES (?, ?, ?, 1, 0, ?, ?)",
            (username, hash_password(password), role, ts, ts),
        )


def change_password(user_id: int, new_password: str):
    if not new_password or len(new_password) < 4:
        raise ServiceError("A senha deve ter ao menos 4 caracteres.")
    ts = now_iso()
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ?, must_change_password = 0, updated_at = ? WHERE id = ?",
            (hash_password(new_password), ts, user_id),
        )


def set_user_active(user_id: int, active: bool):
    with get_connection() as conn:
        conn.execute("UPDATE users SET active = ?, updated_at = ? WHERE id = ?", (1 if active else 0, now_iso(), user_id))


# ----------------------------------------------------------------------
# Configuracoes
# ----------------------------------------------------------------------

def get_all_settings() -> dict:
    with get_connection() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}


def get_setting(key: str, default=None):
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str):
    ts = now_iso()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (key, value, ts),
        )


def set_settings_bulk(values: dict):
    for key, value in values.items():
        set_setting(key, value)


# ----------------------------------------------------------------------
# Categorias
# ----------------------------------------------------------------------

def list_categories():
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
        return [dict(r) for r in rows]


def create_category(name: str):
    name = (name or "").strip()
    if not name:
        raise ServiceError("Informe o nome da categoria.")
    ts = now_iso()
    with get_connection() as conn:
        if conn.execute("SELECT id FROM categories WHERE name = ?", (name,)).fetchone():
            raise ServiceError("Categoria ja existe.")
        conn.execute("INSERT INTO categories (name, created_at, updated_at) VALUES (?, ?, ?)", (name, ts, ts))


def delete_category(category_id: int):
    with get_connection() as conn:
        in_use = conn.execute("SELECT COUNT(*) c FROM products WHERE category_id = ?", (category_id,)).fetchone()["c"]
        if in_use:
            raise ServiceError("Nao e possivel excluir: existem produtos nesta categoria.")
        conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))


# ----------------------------------------------------------------------
# Produtos
# ----------------------------------------------------------------------

def list_products(search: str = None, category_id: int = None, only_active: bool = True):
    query = (
        "SELECT p.*, c.name as category_name FROM products p "
        "LEFT JOIN categories c ON c.id = p.category_id WHERE 1=1"
    )
    params = []
    if only_active:
        query += " AND p.active = 1"
    if category_id:
        query += " AND p.category_id = ?"
        params.append(category_id)
    if search:
        query += " AND p.name LIKE ?"
        params.append(f"%{search}%")
    query += " ORDER BY c.name, p.name"
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def get_product(product_id: int):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        return dict(row) if row else None


def create_product(name, category_id, price, cost=0, track_stock=False, stock=0,
                    low_stock_threshold=5, notes="", active=True, actor: str = ""):
    name = (name or "").strip()
    if not name:
        raise ServiceError("Informe o nome do produto.")
    if price is None or float(price) < 0:
        raise ServiceError("O preco nao pode ser negativo.")
    ts = now_iso()
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO products (name, category_id, price, cost, track_stock, stock, "
            "low_stock_threshold, active, notes, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (name, category_id, float(price), float(cost or 0), 1 if track_stock else 0,
             float(stock or 0), float(low_stock_threshold or 5), 1 if active else 0, notes or "", ts, ts),
        )
        product_id = cur.lastrowid
        _audit(conn, "product", product_id, "created", actor, name)
        return product_id


def update_product(product_id, name, category_id, price, cost=0, track_stock=False,
                    stock=0, low_stock_threshold=5, notes="", active=True):
    name = (name or "").strip()
    if not name:
        raise ServiceError("Informe o nome do produto.")
    if price is None or float(price) < 0:
        raise ServiceError("O preco nao pode ser negativo.")
    ts = now_iso()
    with get_connection() as conn:
        conn.execute(
            "UPDATE products SET name=?, category_id=?, price=?, cost=?, track_stock=?, stock=?, "
            "low_stock_threshold=?, notes=?, active=?, updated_at=? WHERE id=?",
            (name, category_id, float(price), float(cost or 0), 1 if track_stock else 0,
             float(stock or 0), float(low_stock_threshold or 5), notes or "", 1 if active else 0, ts, product_id),
        )


def set_product_active(product_id: int, active: bool):
    with get_connection() as conn:
        conn.execute("UPDATE products SET active = ?, updated_at = ? WHERE id = ?", (1 if active else 0, now_iso(), product_id))


def delete_product(product_id: int):
    with get_connection() as conn:
        used = conn.execute("SELECT COUNT(*) c FROM command_items WHERE product_id = ?", (product_id,)).fetchone()["c"]
        if used:
            # Produto ja foi vendido alguma vez: preserva historico, apenas desativa.
            conn.execute("UPDATE products SET active = 0, updated_at = ? WHERE id = ?", (now_iso(), product_id))
        else:
            conn.execute("DELETE FROM products WHERE id = ?", (product_id,))


def low_stock_products():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM products WHERE active = 1 AND track_stock = 1 AND stock <= low_stock_threshold ORDER BY stock ASC"
        ).fetchall()
        return [dict(r) for r in rows]


def adjust_stock(product_id: int, delta: float):
    with get_connection() as conn:
        conn.execute(
            "UPDATE products SET stock = stock + ?, updated_at = ? WHERE id = ? AND track_stock = 1",
            (delta, now_iso(), product_id),
        )


# ----------------------------------------------------------------------
# Comandas
# ----------------------------------------------------------------------

def _next_command_number(conn) -> int:
    today = today_str()
    row = conn.execute(
        "SELECT COUNT(*) c FROM commands WHERE substr(opened_at, 1, 10) = ?", (today,)
    ).fetchone()
    return row["c"] + 1


def create_command(customer_name: str = "", table_ref: str = "", created_by: str = ""):
    ts = now_iso()
    with get_connection() as conn:
        number = _next_command_number(conn)
        cur = conn.execute(
            "INSERT INTO commands (number, customer_name, table_ref, status, discount, notes, "
            "opened_at, created_by, created_at, updated_at) "
            "VALUES (?, ?, ?, 'aberto', 0, '', ?, ?, ?, ?)",
            (number, (customer_name or "").strip(), (table_ref or "").strip(), ts, created_by, ts, ts),
        )
        command_id = cur.lastrowid
        _audit(conn, "command", command_id, "created", created_by, f"comanda #{number}")
        return command_id


def _totals_from_items(items):
    return sum(i["subtotal"] for i in items)


def get_command(command_id: int):
    with get_connection() as conn:
        cmd = conn.execute("SELECT * FROM commands WHERE id = ?", (command_id,)).fetchone()
        if not cmd:
            return None
        cmd = dict(cmd)
        items = conn.execute(
            "SELECT * FROM command_items WHERE command_id = ? ORDER BY id", (command_id,)
        ).fetchall()
        cmd["items"] = [dict(i) for i in items]
        subtotal = _totals_from_items(cmd["items"])
        cmd["subtotal"] = subtotal
        cmd["total"] = max(subtotal - (cmd["discount"] or 0), 0)
        payments = conn.execute(
            "SELECT * FROM payments WHERE command_id = ? ORDER BY id", (command_id,)
        ).fetchall()
        cmd["payments"] = [dict(p) for p in payments]
        return cmd


def _get_access_signing_secret(conn, create: bool = False):
    row = conn.execute("SELECT value FROM app_secrets WHERE key = 'command_access_signing_key'").fetchone()
    if row:
        return row["value"]
    if not create:
        return None
    value = secrets.token_urlsafe(48)
    ts = now_iso()
    conn.execute(
        "INSERT INTO app_secrets (key, value, created_at, updated_at) VALUES (?, ?, ?, ?)",
        ("command_access_signing_key", value, ts, ts),
    )
    return value


def _build_command_access_token(command_id: int, nonce: str, signing_secret: str) -> str:
    payload = f"{int(command_id)}.{nonce}"
    signature = hmac.new(signing_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def _parse_command_access_token(conn, token: str):
    try:
        command_text, nonce, supplied_signature = (token or "").split(".", 2)
        command_id = int(command_text)
    except (TypeError, ValueError):
        return None
    signing_secret = _get_access_signing_secret(conn, create=False)
    if not signing_secret:
        return None
    expected = _build_command_access_token(command_id, nonce, signing_secret).rsplit(".", 1)[1]
    if not hmac.compare_digest(supplied_signature, expected):
        return None
    return command_id, nonce


def get_command_access(command_id: int):
    with get_connection() as conn:
        command = conn.execute("SELECT id, status FROM commands WHERE id = ?", (command_id,)).fetchone()
        if not command:
            raise ServiceError("Comanda nao encontrada.")
        row = conn.execute(
            "SELECT * FROM command_access_credentials WHERE command_id = ? ORDER BY id DESC LIMIT 1",
            (command_id,),
        ).fetchone()
        if not row:
            return {
                "status": "sem_acesso",
                "token": None,
                "created_at": None,
                "last_regenerated_at": None,
                "revoked_at": None,
            }
        count_row = conn.execute(
            "SELECT COUNT(*) AS total, MIN(created_at) AS first_created_at "
            "FROM command_access_credentials WHERE command_id = ?",
            (command_id,),
        ).fetchone()
        status = "ativo" if row["active"] else "revogado"
        token = None
        if row["active"]:
            signing_secret = _get_access_signing_secret(conn, create=False)
            token = _build_command_access_token(command_id, row["nonce"], signing_secret)
        return {
            "status": status,
            "token": token,
            "created_at": count_row["first_created_at"],
            "last_regenerated_at": row["created_at"] if count_row["total"] > 1 else None,
            "revoked_at": row["revoked_at"],
        }


def generate_command_access(command_id: int, actor: str = ""):
    with get_connection() as conn:
        command = conn.execute("SELECT * FROM commands WHERE id = ?", (command_id,)).fetchone()
        if not command:
            raise ServiceError("Comanda nao encontrada.")
        if command["status"] not in ("aberto", "aguardando_pagamento", "fiado"):
            raise ServiceError("O acesso digital so pode ser gerenciado em comandas abertas ou pendentes.")

        ts = now_iso()
        previous = conn.execute(
            "SELECT id FROM command_access_credentials WHERE command_id = ? AND active = 1",
            (command_id,),
        ).fetchone()
        if previous:
            conn.execute(
                "UPDATE command_access_credentials SET active = 0, revoked_at = ?, revoked_by = ? WHERE id = ?",
                (ts, actor or "", previous["id"]),
            )

        nonce = secrets.token_urlsafe(24)
        cur = conn.execute(
            "INSERT INTO command_access_credentials (command_id, nonce, active, created_at, created_by) "
            "VALUES (?, ?, 1, ?, ?)",
            (command_id, nonce, ts, actor or ""),
        )
        if previous:
            conn.execute(
                "UPDATE command_access_credentials SET replaced_by_id = ? WHERE id = ?",
                (cur.lastrowid, previous["id"]),
            )
        _get_access_signing_secret(conn, create=True)
        action = "access_regenerated" if previous else "access_created"
        _audit(conn, "command", command_id, action, actor, f"comanda #{command['number']}")
    return get_command_access(command_id)


def _revoke_active_command_access(conn, command_id: int, actor: str, ts: str) -> bool:
    active = conn.execute(
        "SELECT id FROM command_access_credentials WHERE command_id = ? AND active = 1",
        (command_id,),
    ).fetchone()
    if not active:
        return False
    conn.execute(
        "UPDATE command_access_credentials SET active = 0, revoked_at = ?, revoked_by = ? WHERE id = ?",
        (ts, actor or "", active["id"]),
    )
    return True


def revoke_command_access(command_id: int, actor: str = ""):
    with get_connection() as conn:
        command = conn.execute("SELECT * FROM commands WHERE id = ?", (command_id,)).fetchone()
        if not command:
            raise ServiceError("Comanda nao encontrada.")
        active = conn.execute(
            "SELECT id FROM command_access_credentials WHERE command_id = ? AND active = 1",
            (command_id,),
        ).fetchone()
        if not active:
            latest = conn.execute(
                "SELECT id FROM command_access_credentials WHERE command_id = ? ORDER BY id DESC LIMIT 1",
                (command_id,),
            ).fetchone()
            if not latest:
                raise ServiceError("Esta comanda ainda nao possui acesso digital.")
            return get_command_access(command_id)
        ts = now_iso()
        _revoke_active_command_access(conn, command_id, actor, ts)
        _audit(conn, "command", command_id, "access_revoked", actor, f"comanda #{command['number']}")
    return get_command_access(command_id)


def get_command_by_access_token(token: str):
    with get_connection() as conn:
        parsed = _parse_command_access_token(conn, token)
        if not parsed:
            return None
        command_id, nonce = parsed
        credential = conn.execute(
            "SELECT id FROM command_access_credentials "
            "WHERE command_id = ? AND nonce = ? AND active = 1",
            (command_id, nonce),
        ).fetchone()
        if not credential:
            return None
        status_row = conn.execute("SELECT status FROM commands WHERE id = ?", (command_id,)).fetchone()
        if not status_row or status_row["status"] not in ("aberto", "aguardando_pagamento", "fiado"):
            return None

    command = get_command(command_id)
    if not command:
        return None
    public_fields = (
        "id", "number", "customer_name", "table_ref", "status", "discount", "opened_at", "updated_at",
        "items", "subtotal", "total",
    )
    result = {key: command[key] for key in public_fields}
    public_item_fields = ("product_name", "unit_price", "quantity", "subtotal", "notes", "kitchen_status")
    result["items"] = [
        {key: item[key] for key in public_item_fields}
        for item in command["items"]
    ]
    result["establishment_name"] = get_setting("establishment_name", "Espetinho DU'DAIR")
    return result


def list_open_commands():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM commands WHERE status IN ('aberto', 'aguardando_pagamento') ORDER BY opened_at"
        ).fetchall()
        result = []
        for r in rows:
            cmd = dict(r)
            items = conn.execute(
                "SELECT * FROM command_items WHERE command_id = ?", (cmd["id"],)
            ).fetchall()
            subtotal = sum(i["subtotal"] for i in items)
            cmd["item_count"] = len(items)
            cmd["subtotal"] = subtotal
            cmd["total"] = max(subtotal - (cmd["discount"] or 0), 0)
            result.append(cmd)
        return result


def list_pending_commands():
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM commands WHERE status = 'fiado' ORDER BY opened_at").fetchall()
        result = []
        for r in rows:
            cmd = dict(r)
            items = conn.execute("SELECT * FROM command_items WHERE command_id = ?", (cmd["id"],)).fetchall()
            subtotal = sum(i["subtotal"] for i in items)
            cmd["total"] = max(subtotal - (cmd["discount"] or 0), 0)
            result.append(cmd)
        return result


def search_commands(query: str = "", status: str = None, date_from: str = None, date_to: str = None):
    sql = "SELECT * FROM commands WHERE 1=1"
    params = []
    if query:
        sql += " AND (CAST(number AS TEXT) LIKE ? OR customer_name LIKE ? OR table_ref LIKE ?)"
        like = f"%{query}%"
        params += [like, like, like]
    if status:
        sql += " AND status = ?"
        params.append(status)
    if date_from:
        sql += " AND substr(opened_at, 1, 10) >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND substr(opened_at, 1, 10) <= ?"
        params.append(date_to)
    sql += " ORDER BY opened_at DESC LIMIT 300"
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
        result = []
        for r in rows:
            cmd = dict(r)
            items = conn.execute("SELECT * FROM command_items WHERE command_id = ?", (cmd["id"],)).fetchall()
            subtotal = sum(i["subtotal"] for i in items)
            cmd["total"] = max(subtotal - (cmd["discount"] or 0), 0)
            result.append(cmd)
        return result


def _ensure_editable(cmd):
    if cmd["status"] not in ("aberto", "aguardando_pagamento"):
        raise ServiceError(f"Comanda #{cmd['number']} nao pode ser editada (status: {STATUS_LABELS.get(cmd['status'], cmd['status'])}).")


def add_item(command_id: int, product_id: int, quantity: float = 1, notes: str = "", actor: str = ""):
    if quantity is None or float(quantity) <= 0:
        raise ServiceError("A quantidade deve ser maior que zero.")
    with get_connection() as conn:
        cmd = conn.execute("SELECT * FROM commands WHERE id = ?", (command_id,)).fetchone()
        if not cmd:
            raise ServiceError("Comanda nao encontrada.")
        _ensure_editable(cmd)
        product = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        if not product or not product["active"]:
            raise ServiceError("Produto invalido ou inativo.")
        quantity = float(quantity)
        subtotal = round(product["price"] * quantity, 2)
        ts = now_iso()

        # Item novo se tiver observacao propria (nao agrupa com itens ja existentes do mesmo produto).
        existing = None
        if not notes:
            existing = conn.execute(
                "SELECT * FROM command_items WHERE command_id = ? AND product_id = ? AND (notes IS NULL OR notes = '')",
                (command_id, product_id),
            ).fetchone()
        if existing:
            new_qty = existing["quantity"] + quantity
            new_subtotal = round(existing["unit_price"] * new_qty, 2)
            conn.execute(
                "UPDATE command_items SET quantity = ?, subtotal = ?, updated_at = ? WHERE id = ?",
                (new_qty, new_subtotal, ts, existing["id"]),
            )
            item_id = existing["id"]
        else:
            cur = conn.execute(
                "INSERT INTO command_items (command_id, product_id, product_name, unit_price, quantity, "
                "subtotal, notes, kitchen_status, created_by, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'pendente', ?, ?, ?)",
                (command_id, product_id, product["name"], product["price"], quantity, subtotal,
                 notes or "", actor, ts, ts),
            )
            item_id = cur.lastrowid
        conn.execute("UPDATE commands SET updated_at = ? WHERE id = ?", (ts, command_id))
        _bump_command_version(conn, command_id)
        _audit(conn, "command_item", item_id, "added", actor, f"{product['name']} x{quantity:g} (comanda #{cmd['number']})")


def update_item_quantity(item_id: int, quantity: float, actor: str = ""):
    if quantity is None or float(quantity) <= 0:
        raise ServiceError("A quantidade deve ser maior que zero.")
    with get_connection() as conn:
        item = conn.execute("SELECT * FROM command_items WHERE id = ?", (item_id,)).fetchone()
        if not item:
            raise ServiceError("Item nao encontrado.")
        cmd = conn.execute("SELECT * FROM commands WHERE id = ?", (item["command_id"],)).fetchone()
        _ensure_editable(cmd)
        quantity = float(quantity)
        new_subtotal = round(item["unit_price"] * quantity, 2)
        ts = now_iso()
        conn.execute(
            "UPDATE command_items SET quantity = ?, subtotal = ?, updated_at = ? WHERE id = ?",
            (quantity, new_subtotal, ts, item_id),
        )
        conn.execute("UPDATE commands SET updated_at = ? WHERE id = ?", (ts, cmd["id"]))
        _bump_command_version(conn, cmd["id"])
        _audit(conn, "command_item", item_id, "quantity_changed", actor,
               f"{item['product_name']} -> {quantity:g} (comanda #{cmd['number']})")


def remove_item(item_id: int, actor: str = ""):
    with get_connection() as conn:
        item = conn.execute("SELECT * FROM command_items WHERE id = ?", (item_id,)).fetchone()
        if not item:
            raise ServiceError("Item nao encontrado.")
        cmd = conn.execute("SELECT * FROM commands WHERE id = ?", (item["command_id"],)).fetchone()
        _ensure_editable(cmd)
        conn.execute("DELETE FROM command_items WHERE id = ?", (item_id,))
        conn.execute("UPDATE commands SET updated_at = ? WHERE id = ?", (now_iso(), cmd["id"]))
        _bump_command_version(conn, cmd["id"])
        _audit(conn, "command_item", item_id, "removed", actor,
               f"{item['product_name']} (comanda #{cmd['number']})")


def set_item_notes(item_id: int, notes: str, actor: str = ""):
    with get_connection() as conn:
        item = conn.execute("SELECT * FROM command_items WHERE id = ?", (item_id,)).fetchone()
        if not item:
            raise ServiceError("Item nao encontrado.")
        cmd = conn.execute("SELECT * FROM commands WHERE id = ?", (item["command_id"],)).fetchone()
        _ensure_editable(cmd)
        conn.execute(
            "UPDATE command_items SET notes = ?, updated_at = ? WHERE id = ?", (notes or "", now_iso(), item_id)
        )
        _bump_command_version(conn, cmd["id"])
        _audit(conn, "command_item", item_id, "notes_changed", actor, notes or "")


def set_item_kitchen_status(item_id: int, status: str, actor: str = ""):
    if status not in KITCHEN_STATUS_LABELS:
        raise ServiceError("Status de cozinha invalido.")
    with get_connection() as conn:
        item = conn.execute("SELECT * FROM command_items WHERE id = ?", (item_id,)).fetchone()
        if not item:
            raise ServiceError("Item nao encontrado.")
        conn.execute(
            "UPDATE command_items SET kitchen_status = ?, updated_at = ? WHERE id = ?",
            (status, now_iso(), item_id),
        )
        _bump_command_version(conn, item["command_id"])
        _audit(conn, "command_item", item_id, "kitchen_status_changed", actor, status)


def list_kitchen_queue():
    """Itens pendentes/preparando/prontos de comandas ainda abertas, para a tela da cozinha."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT ci.*, c.number as command_number, c.table_ref, c.customer_name FROM command_items ci "
            "JOIN commands c ON c.id = ci.command_id "
            "WHERE ci.kitchen_status != 'entregue' AND c.status IN ('aberto', 'aguardando_pagamento', 'fiado') "
            "ORDER BY ci.created_at"
        ).fetchall()
        return [dict(r) for r in rows]


def set_discount(command_id: int, discount: float, actor: str = ""):
    if discount is None or float(discount) < 0:
        raise ServiceError("O desconto nao pode ser negativo.")
    with get_connection() as conn:
        cmd = conn.execute("SELECT * FROM commands WHERE id = ?", (command_id,)).fetchone()
        _ensure_editable(cmd)
        conn.execute("UPDATE commands SET discount = ?, updated_at = ? WHERE id = ?", (float(discount), now_iso(), command_id))
        _bump_command_version(conn, command_id)
        _audit(conn, "command", command_id, "discount_changed", actor, f"R$ {float(discount):.2f}")


def set_notes(command_id: int, notes: str, actor: str = ""):
    with get_connection() as conn:
        conn.execute("UPDATE commands SET notes = ?, updated_at = ? WHERE id = ?", (notes or "", now_iso(), command_id))
        _bump_command_version(conn, command_id)
        _audit(conn, "command", command_id, "notes_changed", actor, notes or "")


def set_customer_info(command_id: int, customer_name: str, table_ref: str, actor: str = ""):
    with get_connection() as conn:
        cmd = conn.execute("SELECT * FROM commands WHERE id = ?", (command_id,)).fetchone()
        _ensure_editable(cmd)
        conn.execute(
            "UPDATE commands SET customer_name = ?, table_ref = ?, updated_at = ? WHERE id = ?",
            ((customer_name or "").strip(), (table_ref or "").strip(), now_iso(), command_id),
        )
        _bump_command_version(conn, command_id)
        _audit(conn, "command", command_id, "customer_info_changed", actor,
               f"{customer_name or ''} / {table_ref or ''}")


def cancel_command(command_id: int, actor: str = ""):
    with get_connection() as conn:
        cmd = conn.execute("SELECT * FROM commands WHERE id = ?", (command_id,)).fetchone()
        if not cmd:
            raise ServiceError("Comanda nao encontrada.")
        if cmd["status"] not in ("aberto", "aguardando_pagamento", "fiado"):
            raise ServiceError("Somente comandas em aberto ou fiado/pendente podem ser canceladas.")
        if cmd["status"] == "fiado":
            items = conn.execute("SELECT * FROM command_items WHERE command_id = ?", (command_id,)).fetchall()
            _restore_stock(conn, items)
        ts = now_iso()
        conn.execute("UPDATE commands SET status='cancelada', closed_at=?, updated_at=? WHERE id=?", (ts, ts, command_id))
        access_revoked = _revoke_active_command_access(conn, command_id, actor, ts)
        _bump_command_version(conn, command_id)
        if access_revoked:
            _audit(conn, "command", command_id, "access_revoked", actor, "revogacao automatica ao cancelar")
        _audit(conn, "command", command_id, "cancelled", actor, f"comanda #{cmd['number']}")


def _deduct_stock(conn, items):
    for item in items:
        if item["product_id"] is None:
            continue
        product = conn.execute("SELECT * FROM products WHERE id = ?", (item["product_id"],)).fetchone()
        if product and product["track_stock"]:
            conn.execute(
                "UPDATE products SET stock = stock - ?, updated_at = ? WHERE id = ?",
                (item["quantity"], now_iso(), item["product_id"]),
            )


def _restore_stock(conn, items):
    for item in items:
        if item["product_id"] is None:
            continue
        product = conn.execute("SELECT * FROM products WHERE id = ?", (item["product_id"],)).fetchone()
        if product and product["track_stock"]:
            conn.execute(
                "UPDATE products SET stock = stock + ?, updated_at = ? WHERE id = ?",
                (item["quantity"], now_iso(), item["product_id"]),
            )


def mark_as_pending(command_id: int, actor: str = ""):
    """Marca a comanda como fiado/pendente: baixa estoque (produto ja saiu), mas nao registra pagamento."""
    with get_connection() as conn:
        cmd = conn.execute("SELECT * FROM commands WHERE id = ?", (command_id,)).fetchone()
        if not cmd:
            raise ServiceError("Comanda nao encontrada.")
        _ensure_editable(cmd)
        items = conn.execute("SELECT * FROM command_items WHERE command_id = ?", (command_id,)).fetchall()
        if not items:
            raise ServiceError("Adicione ao menos um item antes de finalizar a comanda.")
        ts = now_iso()
        _deduct_stock(conn, items)
        conn.execute("UPDATE commands SET status='fiado', closed_at=?, updated_at=? WHERE id=?", (ts, ts, command_id))
        _bump_command_version(conn, command_id)
        _audit(conn, "command", command_id, "marked_pending", actor, f"comanda #{cmd['number']}")


def _validate_payments(total: float, payments: list):
    if not payments:
        raise ServiceError("Informe ao menos uma forma de pagamento.")
    soma_atribuida = 0.0
    for p in payments:
        if p["method"] not in PAYMENT_METHOD_LABELS:
            raise ServiceError("Forma de pagamento invalida.")
        if p["amount"] is None or float(p["amount"]) <= 0:
            raise ServiceError("O valor de cada pagamento deve ser maior que zero.")
        soma_atribuida += float(p["amount"])
        if p["method"] == "dinheiro":
            received = p.get("received_amount")
            if received is not None and float(received) < float(p["amount"]):
                raise ServiceError("O valor recebido em dinheiro nao pode ser menor que o valor atribuido a essa forma de pagamento.")
    if abs(soma_atribuida - total) > 0.01:
        raise ServiceError(
            f"A soma dos pagamentos (R$ {soma_atribuida:.2f}) precisa ser igual ao total da comanda (R$ {total:.2f})."
        )


def finalize_command(command_id: int, payments: list, actor: str = ""):
    """
    payments: lista de dicts {method, amount, received_amount(opcional, so dinheiro)}
    Se houver mais de um item na lista, e um pagamento misto.
    """
    with get_connection() as conn:
        cmd = conn.execute("SELECT * FROM commands WHERE id = ?", (command_id,)).fetchone()
        if not cmd:
            raise ServiceError("Comanda nao encontrada.")

        session = conn.execute("SELECT * FROM cash_sessions WHERE status='aberto'").fetchone()
        if not session:
            raise ServiceError("O caixa esta fechado. Abra o caixa antes de finalizar comandas.")

        items = conn.execute("SELECT * FROM command_items WHERE command_id = ?", (command_id,)).fetchall()
        if not items:
            raise ServiceError("Adicione ao menos um item antes de finalizar a comanda.")

        already_paid_stock = cmd["status"] == "fiado"
        if cmd["status"] not in ("aberto", "aguardando_pagamento", "fiado"):
            raise ServiceError(f"Comanda #{cmd['number']} ja esta com status '{STATUS_LABELS.get(cmd['status'])}'.")

        subtotal = sum(i["subtotal"] for i in items)
        total = round(max(subtotal - (cmd["discount"] or 0), 0), 2)

        _validate_payments(total, payments)

        ts = now_iso()
        for p in payments:
            amount = round(float(p["amount"]), 2)
            received = p.get("received_amount")
            change = None
            if p["method"] == "dinheiro":
                received = float(received) if received is not None else amount
                change = round(received - amount, 2)
            conn.execute(
                "INSERT INTO payments (command_id, method, amount, received_amount, change_amount, "
                "pix_confirmed, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (command_id, p["method"], amount, received, change,
                 1 if p["method"] == "pix" and p.get("pix_confirmed", True) else 0, ts),
            )

        if not already_paid_stock:
            _deduct_stock(conn, items)

        conn.execute(
            "UPDATE commands SET status='paga', closed_at=?, cash_session_id=?, updated_at=? WHERE id=?",
            (ts, session["id"], ts, command_id),
        )
        access_revoked = _revoke_active_command_access(conn, command_id, actor, ts)
        _bump_command_version(conn, command_id)
        if access_revoked:
            _audit(conn, "command", command_id, "access_revoked", actor, "revogacao automatica ao finalizar")
        methods = ", ".join(p["method"] for p in payments)
        _audit(conn, "command", command_id, "paid", actor, f"comanda #{cmd['number']} via {methods} - R$ {total:.2f}")

        return {"total": total, "payments": payments}


# ----------------------------------------------------------------------
# Caixa
# ----------------------------------------------------------------------

def get_open_cash_session():
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM cash_sessions WHERE status = 'aberto' ORDER BY id DESC LIMIT 1").fetchone()
        return dict(row) if row else None


def get_cash_session(cash_session_id: int):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM cash_sessions WHERE id = ?", (cash_session_id,)).fetchone()
        return dict(row) if row else None


def open_cash_session(opening_amount: float, operator_name: str = "", notes: str = "", actor: str = ""):
    if opening_amount is None or float(opening_amount) < 0:
        raise ServiceError("O fundo inicial nao pode ser negativo.")
    with get_connection() as conn:
        existing = conn.execute("SELECT id FROM cash_sessions WHERE status = 'aberto'").fetchone()
        if existing:
            raise ServiceError("Ja existe um caixa aberto. Feche o caixa atual antes de abrir outro.")
        ts = now_iso()
        cur = conn.execute(
            "INSERT INTO cash_sessions (opened_at, opening_amount, operator_name, open_notes, status, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, 'aberto', ?, ?)",
            (ts, float(opening_amount), operator_name or "", notes or "", ts, ts),
        )
        session_id = cur.lastrowid
        _audit(conn, "cash_session", session_id, "opened", actor, f"fundo inicial R$ {float(opening_amount):.2f}")
        return session_id


def add_movement(cash_session_id: int, mtype: str, amount: float, reason: str = "", actor: str = ""):
    if mtype not in ("sangria", "reforco"):
        raise ServiceError("Tipo de movimentacao invalido.")
    if amount is None or float(amount) <= 0:
        raise ServiceError("O valor deve ser maior que zero.")
    with get_connection() as conn:
        session = conn.execute("SELECT * FROM cash_sessions WHERE id = ? AND status = 'aberto'", (cash_session_id,)).fetchone()
        if not session:
            raise ServiceError("Caixa nao esta aberto.")
        conn.execute(
            "INSERT INTO cash_movements (cash_session_id, type, amount, reason, created_at) VALUES (?, ?, ?, ?, ?)",
            (cash_session_id, mtype, float(amount), reason or "", now_iso()),
        )
        _audit(conn, "cash_session", cash_session_id, mtype, actor, f"R$ {float(amount):.2f} - {reason or ''}")


def list_movements(cash_session_id: int):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM cash_movements WHERE cash_session_id = ? ORDER BY id DESC", (cash_session_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def _classify_command_payment_bucket(payment_methods: set):
    if len(payment_methods) > 1:
        return "misto"
    return next(iter(payment_methods)) if payment_methods else "misto"


def get_cash_summary(cash_session_id: int):
    with get_connection() as conn:
        session = conn.execute("SELECT * FROM cash_sessions WHERE id = ?", (cash_session_id,)).fetchone()
        if not session:
            raise ServiceError("Caixa nao encontrado.")
        session = dict(session)

        movements = conn.execute("SELECT * FROM cash_movements WHERE cash_session_id = ?", (cash_session_id,)).fetchall()
        reforcos = sum(m["amount"] for m in movements if m["type"] == "reforco")
        sangrias = sum(m["amount"] for m in movements if m["type"] == "sangria")

        commands = conn.execute(
            "SELECT * FROM commands WHERE cash_session_id = ? AND status = 'paga'", (cash_session_id,)
        ).fetchall()

        buckets = {"dinheiro": 0.0, "pix": 0.0, "debito": 0.0, "credito": 0.0, "misto": 0.0}
        bucket_counts = {"dinheiro": 0, "pix": 0, "debito": 0, "credito": 0, "misto": 0}
        raw_dinheiro_recebido = 0.0
        raw_troco = 0.0
        total_vendido = 0.0
        product_qty = {}

        for cmd in commands:
            items = conn.execute("SELECT * FROM command_items WHERE command_id = ?", (cmd["id"],)).fetchall()
            subtotal = sum(i["subtotal"] for i in items)
            cmd_total = round(max(subtotal - (cmd["discount"] or 0), 0), 2)
            total_vendido += cmd_total
            for i in items:
                product_qty[i["product_name"]] = product_qty.get(i["product_name"], 0) + i["quantity"]

            payments = conn.execute("SELECT * FROM payments WHERE command_id = ?", (cmd["id"],)).fetchall()
            methods = {p["method"] for p in payments}
            bucket = _classify_command_payment_bucket(methods)
            buckets[bucket] += cmd_total
            bucket_counts[bucket] += 1

            for p in payments:
                if p["method"] == "dinheiro":
                    raw_dinheiro_recebido += p["received_amount"] or p["amount"]
                    raw_troco += p["change_amount"] or 0

        counts = conn.execute(
            "SELECT status, COUNT(*) c FROM commands WHERE cash_session_id = ? OR (status IN ('aberto','aguardando_pagamento','fiado')) "
            "GROUP BY status", (cash_session_id,)
        ).fetchall()
        status_counts = {"paga": 0, "cancelada": 0, "aberto": 0, "fiado": 0, "aguardando_pagamento": 0}
        for r in counts:
            status_counts[r["status"]] = status_counts.get(r["status"], 0) + r["c"]

        # comandas canceladas dentro deste caixa (vinculadas por data de abertura durante a sessao)
        cancel_count = conn.execute(
            "SELECT COUNT(*) c FROM commands WHERE status='cancelada' AND opened_at >= ? "
            "AND (? = '' OR opened_at <= ?)",
            (session["opened_at"], session["closed_at"] or "", session["closed_at"] or "9999-12-31"),
        ).fetchone()["c"]

        top_products = sorted(product_qty.items(), key=lambda kv: kv[1], reverse=True)[:10]

        expected_cash = (
            session["opening_amount"] + reforcos - sangrias + raw_dinheiro_recebido - raw_troco
        )

        return {
            "session": session,
            "opening_amount": session["opening_amount"],
            "reforcos": reforcos,
            "sangrias": sangrias,
            "total_vendido": round(total_vendido, 2),
            "por_forma": {k: round(v, 2) for k, v in buckets.items()},
            "qtd_por_forma": bucket_counts,
            "qtd_pagas": len(commands),
            "qtd_canceladas": cancel_count,
            "qtd_abertas": status_counts.get("aberto", 0) + status_counts.get("aguardando_pagamento", 0),
            "qtd_pendentes": status_counts.get("fiado", 0),
            "produtos_mais_vendidos": top_products,
            "dinheiro_recebido_bruto": round(raw_dinheiro_recebido, 2),
            "troco_total": round(raw_troco, 2),
            "dinheiro_esperado": round(expected_cash, 2),
        }


def close_cash_session(cash_session_id: int, counted_amount: float, close_notes: str = "", closed_by: str = "", force: bool = False):
    with get_connection() as conn:
        session = conn.execute("SELECT * FROM cash_sessions WHERE id = ? AND status='aberto'", (cash_session_id,)).fetchone()
        if not session:
            raise ServiceError("Este caixa ja esta fechado ou nao existe.")

        open_count = conn.execute(
            "SELECT COUNT(*) c FROM commands WHERE status IN ('aberto', 'aguardando_pagamento')"
        ).fetchone()["c"]
        if open_count and not force:
            raise ServiceError(
                f"Existem {open_count} comanda(s) em aberto. Finalize ou cancele antes de fechar o caixa "
                f"(ou confirme o fechamento forcado)."
            )

    summary = get_cash_summary(cash_session_id)
    expected = summary["dinheiro_esperado"]
    counted = round(float(counted_amount or 0), 2)
    difference = round(counted - expected, 2)

    ts = now_iso()
    with get_connection() as conn:
        conn.execute(
            "UPDATE cash_sessions SET status='fechado', closed_at=?, counted_amount=?, expected_amount=?, "
            "difference=?, close_notes=?, closed_by=?, updated_at=? WHERE id=?",
            (ts, counted, expected, difference, close_notes or "", closed_by or "", ts, cash_session_id),
        )
        _audit(conn, "cash_session", cash_session_id, "closed", closed_by,
               f"esperado R$ {expected:.2f} / contado R$ {counted:.2f} / diferenca R$ {difference:.2f}")

    summary["counted_amount"] = counted
    summary["difference"] = difference
    summary["closed_at"] = ts
    return summary


def list_cash_sessions_history(limit: int = 50):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM cash_sessions WHERE status='fechado' ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


# ----------------------------------------------------------------------
# Dashboard / relatorios
# ----------------------------------------------------------------------

def get_dashboard_summary():
    today = today_str()
    with get_connection() as conn:
        session = conn.execute("SELECT * FROM cash_sessions WHERE status='aberto'").fetchone()

        open_count = conn.execute(
            "SELECT COUNT(*) c FROM commands WHERE status IN ('aberto','aguardando_pagamento')"
        ).fetchone()["c"]

        paid_today = conn.execute(
            "SELECT c.id FROM commands c WHERE c.status='paga' AND substr(c.closed_at,1,10) = ?", (today,)
        ).fetchall()

        total_vendido = 0.0
        buckets = {"dinheiro": 0.0, "pix": 0.0, "debito": 0.0, "credito": 0.0}
        for cmd_row in paid_today:
            cmd_id = cmd_row["id"]
            items = conn.execute("SELECT * FROM command_items WHERE command_id=?", (cmd_id,)).fetchall()
            cmd = conn.execute("SELECT * FROM commands WHERE id=?", (cmd_id,)).fetchone()
            subtotal = sum(i["subtotal"] for i in items)
            total = max(subtotal - (cmd["discount"] or 0), 0)
            total_vendido += total
            payments = conn.execute("SELECT * FROM payments WHERE command_id=?", (cmd_id,)).fetchall()
            for p in payments:
                buckets[p["method"]] = buckets.get(p["method"], 0) + p["amount"]

        pending_today = conn.execute(
            "SELECT COUNT(*) c FROM commands WHERE status='fiado' AND substr(opened_at,1,10) = ?", (today,)
        ).fetchone()["c"]

        return {
            "cash_open": session is not None,
            "session": dict(session) if session else None,
            "total_vendido_hoje": round(total_vendido, 2),
            "qtd_abertas": open_count,
            "qtd_finalizadas_hoje": len(paid_today),
            "qtd_pendentes_hoje": pending_today,
            "total_dinheiro": round(buckets.get("dinheiro", 0), 2),
            "total_pix": round(buckets.get("pix", 0), 2),
            "total_cartao": round(buckets.get("debito", 0) + buckets.get("credito", 0), 2),
        }


def sales_report(date_from: str, date_to: str):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM commands WHERE substr(opened_at,1,10) BETWEEN ? AND ? ORDER BY opened_at", (date_from, date_to)
        ).fetchall()
        result = []
        for r in rows:
            cmd = dict(r)
            items = conn.execute("SELECT * FROM command_items WHERE command_id=?", (cmd["id"],)).fetchall()
            subtotal = sum(i["subtotal"] for i in items)
            cmd["total"] = round(max(subtotal - (cmd["discount"] or 0), 0), 2)
            result.append(cmd)
        return result


def payment_totals_by_period(date_from: str, date_to: str):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT pay.method, SUM(pay.amount) total, COUNT(*) qtd FROM payments pay "
            "JOIN commands c ON c.id = pay.command_id "
            "WHERE substr(c.closed_at,1,10) BETWEEN ? AND ? AND c.status='paga' "
            "GROUP BY pay.method", (date_from, date_to)
        ).fetchall()
        return [dict(r) for r in rows]


def top_products_by_period(date_from: str, date_to: str, limit: int = 15):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT ci.product_name, SUM(ci.quantity) qty, SUM(ci.subtotal) total FROM command_items ci "
            "JOIN commands c ON c.id = ci.command_id "
            "WHERE c.status='paga' AND substr(c.closed_at,1,10) BETWEEN ? AND ? "
            "GROUP BY ci.product_name ORDER BY qty DESC LIMIT ?", (date_from, date_to, limit)
        ).fetchall()
        return [dict(r) for r in rows]
