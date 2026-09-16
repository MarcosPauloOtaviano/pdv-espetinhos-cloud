"""
Cliente HTTP do app desktop para o servidor embutido (app/server.py).
Espelha as assinaturas publicas de app/services.py para que a UI (ui/*.py)
quase nao precise mudar - so troca o import de `services` para `api_client`.

O desktop fala com o servidor exatamente como o celular falaria (mesma API),
so que sempre em 127.0.0.1 (o servidor roda no mesmo processo/computador).
"""
import requests

from app.services import PAYMENT_METHOD_LABELS, STATUS_LABELS, KITCHEN_STATUS_LABELS  # re-export, constantes puras
from app.utils import DEFAULT_PORT

BASE_URL = f"http://127.0.0.1:{DEFAULT_PORT}"

_token = None
_current_user = None


class ServiceError(Exception):
    """Erro vindo do servidor (validacao de negocio, permissao ou conexao)."""


def _headers():
    if _token:
        return {"Authorization": f"Bearer {_token}"}
    return {}


def _request(method: str, path: str, allow_404_none=False, **kwargs):
    try:
        resp = requests.request(method, f"{BASE_URL}{path}", headers=_headers(), timeout=10, **kwargs)
    except requests.exceptions.RequestException as exc:
        raise ServiceError(
            "Nao foi possivel conectar ao servidor local do DUDAIR-PDV. Tente reiniciar o programa."
        ) from exc

    if resp.status_code == 404 and allow_404_none:
        return None
    if not resp.ok:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text or f"Erro HTTP {resp.status_code}"
        raise ServiceError(detail)
    if resp.status_code == 204 or not resp.content:
        return None
    return resp.json()


# ----------------------------------------------------------------------
# Autenticacao
# ----------------------------------------------------------------------

def authenticate(username: str, password: str):
    global _token, _current_user
    try:
        data = _request("POST", "/api/auth/login", json={"username": username, "password": password})
    except ServiceError as exc:
        if "invalidos" in str(exc).lower():
            return None
        raise
    _token = data["token"]
    _current_user = data["user"]
    return data["user"]


def get_token():
    return _token


def logout():
    global _token, _current_user
    if _token:
        try:
            _request("POST", "/api/auth/logout")
        except ServiceError:
            pass
    _token = None
    _current_user = None


def change_password(user_id: int, new_password: str):
    _request("PUT", f"/api/users/{user_id}/password", json={"password": new_password})


def list_users():
    return _request("GET", "/api/users")


def create_user(username: str, password: str, role: str):
    _request("POST", "/api/users", json={"username": username, "password": password, "role": role})


def set_user_active(user_id: int, active: bool):
    _request("PUT", f"/api/users/{user_id}/active", json={"active": bool(active)})


# ----------------------------------------------------------------------
# Configuracoes
# ----------------------------------------------------------------------

def get_all_settings() -> dict:
    return _request("GET", "/api/settings")


def get_setting(key: str, default=None):
    try:
        if _token:
            data = _request("GET", "/api/settings")
        else:
            data = _request("GET", "/api/settings/public")
        return data.get(key, default)
    except ServiceError:
        return default


def set_setting(key: str, value: str):
    _request("PUT", "/api/settings", json={"values": {key: value}})


def set_settings_bulk(values: dict):
    _request("PUT", "/api/settings", json={"values": values})


# ----------------------------------------------------------------------
# Categorias / Produtos
# ----------------------------------------------------------------------

def list_categories():
    return _request("GET", "/api/categories")


def create_category(name: str):
    _request("POST", "/api/categories", json={"name": name})


def delete_category(category_id: int):
    raise ServiceError("Nao implementado nesta versao.")


def list_products(search: str = None, category_id: int = None, only_active: bool = True):
    params = {"only_active": only_active}
    if search:
        params["search"] = search
    if category_id:
        params["category_id"] = category_id
    return _request("GET", "/api/products", params=params)


def get_product(product_id: int):
    for p in list_products(only_active=False):
        if p["id"] == product_id:
            return p
    return None


def _product_payload(name, category_id, price, cost, track_stock, stock, low_stock_threshold, notes, active):
    return {
        "name": name, "category_id": category_id, "price": float(price or 0), "cost": float(cost or 0),
        "track_stock": bool(track_stock), "stock": float(stock or 0),
        "low_stock_threshold": float(low_stock_threshold or 5), "notes": notes or "", "active": bool(active),
    }


def create_product(name, category_id, price, cost=0, track_stock=False, stock=0,
                    low_stock_threshold=5, notes="", active=True):
    data = _request("POST", "/api/products",
                     json=_product_payload(name, category_id, price, cost, track_stock, stock,
                                            low_stock_threshold, notes, active))
    return data["id"]


def update_product(product_id, name, category_id, price, cost=0, track_stock=False,
                    stock=0, low_stock_threshold=5, notes="", active=True):
    _request("PUT", f"/api/products/{product_id}",
             json=_product_payload(name, category_id, price, cost, track_stock, stock,
                                    low_stock_threshold, notes, active))


def set_product_active(product_id: int, active: bool):
    _request("PUT", f"/api/products/{product_id}/active", json={"active": bool(active)})


def delete_product(product_id: int):
    _request("DELETE", f"/api/products/{product_id}")


# ----------------------------------------------------------------------
# Comandas
# ----------------------------------------------------------------------

def create_command(customer_name: str = "", table_ref: str = "", created_by: str = ""):
    data = _request("POST", "/api/commands", json={"customer_name": customer_name, "table_ref": table_ref})
    return data["id"]


def get_command(command_id: int):
    return _request("GET", f"/api/commands/{command_id}", allow_404_none=True)


def get_command_access(command_id: int):
    return _request("GET", f"/api/commands/{command_id}/access")


def regenerate_command_access(command_id: int):
    return _request("POST", f"/api/commands/{command_id}/access/regenerate")


def revoke_command_access(command_id: int):
    return _request("POST", f"/api/commands/{command_id}/access/revoke")


def list_open_commands():
    return _request("GET", "/api/commands/open")


def list_pending_commands():
    return _request("GET", "/api/commands/pending")


def search_commands(query: str = "", status: str = None, date_from: str = None, date_to: str = None):
    params = {"query": query or ""}
    if status:
        params["status"] = status
    if date_from:
        params["date_from"] = date_from
    if date_to:
        params["date_to"] = date_to
    return _request("GET", "/api/commands/search", params=params)


def add_item(command_id: int, product_id: int, quantity: float = 1, notes: str = "", actor: str = ""):
    _request("POST", f"/api/commands/{command_id}/items",
              json={"product_id": product_id, "quantity": quantity, "notes": notes or ""})


def update_item_quantity(item_id: int, quantity: float, actor: str = ""):
    _request("PUT", f"/api/commands/items/{item_id}/quantity", json={"quantity": quantity})


def remove_item(item_id: int, actor: str = ""):
    _request("DELETE", f"/api/commands/items/{item_id}")


def set_item_notes(item_id: int, notes: str, actor: str = ""):
    _request("PUT", f"/api/commands/items/{item_id}/notes", json={"notes": notes or ""})


def set_item_kitchen_status(item_id: int, status: str, actor: str = ""):
    _request("PUT", f"/api/commands/items/{item_id}/kitchen-status", json={"status": status})


def list_kitchen_queue():
    return _request("GET", "/api/kitchen/queue")


def set_discount(command_id: int, discount: float, actor: str = ""):
    _request("PUT", f"/api/commands/{command_id}/discount", json={"discount": discount})


def set_notes(command_id: int, notes: str, actor: str = ""):
    _request("PUT", f"/api/commands/{command_id}/notes", json={"notes": notes or ""})


def set_customer_info(command_id: int, customer_name: str, table_ref: str, actor: str = ""):
    _request("PUT", f"/api/commands/{command_id}/customer",
              json={"customer_name": customer_name or "", "table_ref": table_ref or ""})


def cancel_command(command_id: int, actor: str = ""):
    _request("POST", f"/api/commands/{command_id}/cancel")


def mark_as_pending(command_id: int, actor: str = ""):
    _request("POST", f"/api/commands/{command_id}/pending")


def finalize_command(command_id: int, payments: list, actor: str = ""):
    return _request("POST", f"/api/commands/{command_id}/finalize", json={"payments": payments})


# ----------------------------------------------------------------------
# Caixa
# ----------------------------------------------------------------------

def get_open_cash_session():
    return _request("GET", "/api/cash/current", allow_404_none=True)


def get_cash_session(cash_session_id: int):
    return _request("GET", f"/api/cash/{cash_session_id}", allow_404_none=True)


def open_cash_session(opening_amount: float, operator_name: str = "", notes: str = "", actor: str = ""):
    data = _request("POST", "/api/cash/open",
                     json={"opening_amount": opening_amount, "operator_name": operator_name or "", "notes": notes or ""})
    return data["id"]


def add_movement(cash_session_id: int, mtype: str, amount: float, reason: str = "", actor: str = ""):
    _request("POST", f"/api/cash/{cash_session_id}/movement", json={"type": mtype, "amount": amount, "reason": reason or ""})


def list_movements(cash_session_id: int):
    return _request("GET", f"/api/cash/{cash_session_id}/movements")


def get_cash_summary(cash_session_id: int):
    return _request("GET", f"/api/cash/{cash_session_id}/summary")


def close_cash_session(cash_session_id: int, counted_amount: float, close_notes: str = "", closed_by: str = "",
                        force: bool = False):
    return _request("POST", f"/api/cash/{cash_session_id}/close",
                     json={"counted_amount": counted_amount, "close_notes": close_notes or "", "force": bool(force)})


def list_cash_sessions_history(limit: int = 50):
    return _request("GET", "/api/cash/history")


# ----------------------------------------------------------------------
# Dashboard / relatorios
# ----------------------------------------------------------------------

def get_dashboard_summary():
    return _request("GET", "/api/reports/dashboard")


def sales_report(date_from: str, date_to: str):
    return _request("GET", "/api/reports/sales", params={"date_from": date_from, "date_to": date_to})


def payment_totals_by_period(date_from: str, date_to: str):
    return _request("GET", "/api/reports/payments", params={"date_from": date_from, "date_to": date_to})


def top_products_by_period(date_from: str, date_to: str, limit: int = 15):
    return _request("GET", "/api/reports/top-products", params={"date_from": date_from, "date_to": date_to})


def list_audit_log(limit: int = 200, entity_type: str = None, entity_id: int = None):
    params = {"limit": limit}
    if entity_type:
        params["entity_type"] = entity_type
    if entity_id is not None:
        params["entity_id"] = entity_id
    return _request("GET", "/api/reports/audit", params=params)


def trigger_backup():
    return _request("POST", "/api/backup")
