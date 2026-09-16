"""
Servidor central do DUDAIR-PDV: FastAPI + WebSocket, rodando embutido no
mesmo programa que abre no computador. Donos dos dados: SQLite local
(app/database.py) + regras de negocio (app/services.py). O app desktop e a
PWA do celular falam com este servidor via HTTP/WebSocket - nunca acessam o
banco diretamente.
"""
import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Header, WebSocket, WebSocketDisconnect, Depends, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import services, backup as backup_module
from app.database import init_db
from app.pix import generate_qr_bytes
from app.services import ServiceError
from app.utils import now_iso, get_data_dir, get_lan_ip, resource_path

AUTO_BACKUP_INTERVAL_SECONDS = int(os.environ.get("DUDAIR_AUTO_BACKUP_SECONDS", 30 * 60))  # a cada 30 minutos
AUTO_BACKUP_KEEP = 20


# ----------------------------------------------------------------------
# WebSocket hub
# ----------------------------------------------------------------------

class ConnectionManager:
    def __init__(self):
        self.active: List[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self.active.append(ws)

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            if ws in self.active:
                self.active.remove(ws)

    async def broadcast(self, event_type: str, **data):
        payload = json.dumps({"event": event_type, "data": data, "ts": now_iso()}, ensure_ascii=False)
        async with self._lock:
            targets = list(self.active)
        dead = []
        for ws in targets:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    if ws in self.active:
                        self.active.remove(ws)


manager = ConnectionManager()


# ----------------------------------------------------------------------
# Auth helpers
# ----------------------------------------------------------------------

def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Token ausente. Faca login novamente.")
    token = authorization.split(" ", 1)[1].strip()
    user = services.get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Sessao expirada ou invalida. Faca login novamente.")
    return user


def require_roles(*roles):
    def _dep(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Seu perfil nao tem permissao para esta acao.")
        return user
    return _dep


ANYONE = get_current_user
MONEY_ROLES = require_roles("admin", "caixa")
ORDER_ROLES = require_roles("admin", "caixa", "garcom")
KITCHEN_ROLES = require_roles("admin", "cozinha")
ADMIN_ONLY = require_roles("admin")
ACCESS_ROLES = require_roles("admin", "garcom")


# ----------------------------------------------------------------------
# Schemas
# ----------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str


class PasswordChange(BaseModel):
    password: str


class CommandCreate(BaseModel):
    customer_name: str = ""
    table_ref: str = ""


class CustomerInfoUpdate(BaseModel):
    customer_name: str = ""
    table_ref: str = ""


class ItemAdd(BaseModel):
    product_id: int
    quantity: float = 1
    notes: str = ""


class QuantityUpdate(BaseModel):
    quantity: float


class NotesUpdate(BaseModel):
    notes: str = ""


class KitchenStatusUpdate(BaseModel):
    status: str


class DiscountUpdate(BaseModel):
    discount: float


class PaymentEntry(BaseModel):
    method: str
    amount: float
    received_amount: Optional[float] = None
    pix_confirmed: Optional[bool] = True


class FinalizeRequest(BaseModel):
    payments: List[PaymentEntry]


class CashOpenRequest(BaseModel):
    opening_amount: float
    operator_name: str = ""
    notes: str = ""


class MovementRequest(BaseModel):
    type: str
    amount: float
    reason: str = ""


class CashCloseRequest(BaseModel):
    counted_amount: float
    close_notes: str = ""
    force: bool = False


class ProductCreate(BaseModel):
    name: str
    category_id: Optional[int] = None
    price: float
    cost: float = 0
    track_stock: bool = False
    stock: float = 0
    low_stock_threshold: float = 5
    notes: str = ""
    active: bool = True


class CategoryCreate(BaseModel):
    name: str


class UserCreate(BaseModel):
    username: str
    password: str
    role: str


class ActiveUpdate(BaseModel):
    active: bool


class SettingsUpdate(BaseModel):
    values: dict


# ----------------------------------------------------------------------
# App factory
# ----------------------------------------------------------------------

def create_app() -> FastAPI:
    async def _auto_backup_loop():
        backups_dir = get_data_dir() / "backups"
        while True:
            await asyncio.sleep(AUTO_BACKUP_INTERVAL_SECONDS)
            try:
                backup_module.backup_database(str(backups_dir))
                _prune_old_backups(backups_dir, AUTO_BACKUP_KEEP)
            except Exception:
                pass

    @asynccontextmanager
    async def _lifespan(_app: FastAPI):
        init_db()
        backup_task = asyncio.create_task(_auto_backup_loop())
        try:
            yield
        finally:
            backup_task.cancel()
            try:
                await backup_task
            except asyncio.CancelledError:
                pass

    app = FastAPI(title="DUDAIR-PDV", docs_url="/api/docs", redoc_url=None, lifespan=_lifespan)

    def _prune_old_backups(folder: Path, keep: int):
        if not folder.exists():
            return
        files = sorted(folder.glob("backup-dudair-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[keep:]:
            try:
                old.unlink()
            except Exception:
                pass

    @app.exception_handler(ServiceError)
    async def _service_error_handler(request, exc: ServiceError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    # ---------------- Auth ----------------
    @app.post("/api/auth/login")
    async def login(payload: LoginRequest):
        user = services.authenticate(payload.username, payload.password)
        if not user:
            raise HTTPException(status_code=401, detail="Usuario ou senha invalidos.")
        token = services.create_session(user["id"])
        return {
            "token": token,
            "user": {
                "id": user["id"], "username": user["username"], "role": user["role"],
                "must_change_password": bool(user["must_change_password"]),
            },
        }

    @app.post("/api/auth/logout")
    async def logout(authorization: Optional[str] = Header(None)):
        if authorization and authorization.lower().startswith("bearer "):
            services.revoke_session(authorization.split(" ", 1)[1].strip())
        return {"ok": True}

    @app.get("/api/auth/me")
    async def me(user: dict = Depends(get_current_user)):
        return {"id": user["id"], "username": user["username"], "role": user["role"]}

    @app.put("/api/auth/me/password")
    async def change_my_password(payload: PasswordChange, user: dict = Depends(get_current_user)):
        services.change_password(user["id"], payload.password)
        return {"ok": True}

    # ---------------- Settings ----------------
    @app.get("/api/settings/public")
    async def public_settings():
        return {"establishment_name": services.get_setting("establishment_name", "Espetinho DU'DAIR")}

    @app.get("/api/settings")
    async def get_settings(user: dict = Depends(ADMIN_ONLY)):
        return services.get_all_settings()

    @app.put("/api/settings")
    async def update_settings(payload: SettingsUpdate, user: dict = Depends(ADMIN_ONLY)):
        services.set_settings_bulk(payload.values)
        return {"ok": True}

    # ---------------- Usuarios ----------------
    @app.get("/api/users")
    async def list_users(user: dict = Depends(ADMIN_ONLY)):
        return services.list_users()

    @app.post("/api/users")
    async def create_user(payload: UserCreate, user: dict = Depends(ADMIN_ONLY)):
        services.create_user(payload.username, payload.password, payload.role)
        return {"ok": True}

    @app.put("/api/users/{user_id}/password")
    async def reset_password(user_id: int, payload: PasswordChange, user: dict = Depends(ADMIN_ONLY)):
        services.change_password(user_id, payload.password)
        return {"ok": True}

    @app.put("/api/users/{user_id}/active")
    async def set_user_active(user_id: int, payload: ActiveUpdate, user: dict = Depends(ADMIN_ONLY)):
        services.set_user_active(user_id, payload.active)
        return {"ok": True}

    # ---------------- Categorias / Produtos ----------------
    @app.get("/api/categories")
    async def list_categories(user: dict = Depends(ANYONE)):
        return services.list_categories()

    @app.post("/api/categories")
    async def create_category(payload: CategoryCreate, user: dict = Depends(ADMIN_ONLY)):
        services.create_category(payload.name)
        return {"ok": True}

    @app.get("/api/products")
    async def list_products(search: str = None, category_id: int = None, only_active: bool = True,
                             user: dict = Depends(ANYONE)):
        return services.list_products(search=search, category_id=category_id, only_active=only_active)

    @app.post("/api/products")
    async def create_product(payload: ProductCreate, user: dict = Depends(ADMIN_ONLY)):
        pid = services.create_product(payload.name, payload.category_id, payload.price, payload.cost,
                                       payload.track_stock, payload.stock, payload.low_stock_threshold,
                                       payload.notes, payload.active, actor=user["username"])
        await manager.broadcast("product.changed", product_id=pid)
        return {"id": pid}

    @app.put("/api/products/{product_id}")
    async def update_product(product_id: int, payload: ProductCreate, user: dict = Depends(ADMIN_ONLY)):
        services.update_product(product_id, payload.name, payload.category_id, payload.price, payload.cost,
                                 payload.track_stock, payload.stock, payload.low_stock_threshold,
                                 payload.notes, payload.active)
        await manager.broadcast("product.changed", product_id=product_id)
        return {"ok": True}

    @app.put("/api/products/{product_id}/active")
    async def set_product_active(product_id: int, payload: ActiveUpdate, user: dict = Depends(ADMIN_ONLY)):
        services.set_product_active(product_id, payload.active)
        await manager.broadcast("product.changed", product_id=product_id)
        return {"ok": True}

    @app.delete("/api/products/{product_id}")
    async def delete_product(product_id: int, user: dict = Depends(ADMIN_ONLY)):
        services.delete_product(product_id)
        await manager.broadcast("product.changed", product_id=product_id)
        return {"ok": True}

    # ---------------- Comandas ----------------
    @app.post("/api/commands")
    async def create_command(payload: CommandCreate, user: dict = Depends(ORDER_ROLES)):
        cmd_id = services.create_command(payload.customer_name, payload.table_ref, user["username"])
        await manager.broadcast("command.created", command_id=cmd_id, actor=user["username"])
        return services.get_command(cmd_id)

    @app.get("/api/commands/open")
    async def list_open(user: dict = Depends(ANYONE)):
        return services.list_open_commands()

    @app.get("/api/commands/pending")
    async def list_pending(user: dict = Depends(ANYONE)):
        return services.list_pending_commands()

    @app.get("/api/commands/search")
    async def search_commands(query: str = "", status: str = None, date_from: str = None, date_to: str = None,
                               user: dict = Depends(ANYONE)):
        return services.search_commands(query, status, date_from, date_to)

    @app.get("/api/commands/{command_id}")
    async def get_command(command_id: int, user: dict = Depends(ANYONE)):
        cmd = services.get_command(command_id)
        if not cmd:
            raise HTTPException(status_code=404, detail="Comanda nao encontrada.")
        return cmd

    def _access_response(request: Request, access: dict):
        result = dict(access)
        token = result.get("token")
        hostname = request.url.hostname or "127.0.0.1"
        if hostname in ("127.0.0.1", "localhost", "0.0.0.0", "::1"):
            hostname = get_lan_ip()
        port = f":{request.url.port}" if request.url.port else ""
        base_url = f"{request.url.scheme}://{hostname}{port}"
        result["access_url"] = f"{base_url}/app/?access={quote(token)}" if token else None
        return result

    @app.get("/api/commands/{command_id}/access")
    async def get_command_access(command_id: int, request: Request, user: dict = Depends(ACCESS_ROLES)):
        return _access_response(request, services.get_command_access(command_id))

    @app.post("/api/commands/{command_id}/access/regenerate")
    async def regenerate_command_access(command_id: int, request: Request, user: dict = Depends(ACCESS_ROLES)):
        access = services.generate_command_access(command_id, actor=user["username"])
        await manager.broadcast("command.access_changed", command_id=command_id, actor=user["username"])
        return _access_response(request, access)

    @app.post("/api/commands/{command_id}/access/revoke")
    async def revoke_command_access(command_id: int, request: Request, user: dict = Depends(ACCESS_ROLES)):
        access = services.revoke_command_access(command_id, actor=user["username"])
        await manager.broadcast("command.access_changed", command_id=command_id, actor=user["username"])
        return _access_response(request, access)

    @app.get("/api/commands/{command_id}/access/qr")
    async def command_access_qr(command_id: int, request: Request, user: dict = Depends(ACCESS_ROLES)):
        access = _access_response(request, services.get_command_access(command_id))
        if not access.get("access_url"):
            raise HTTPException(status_code=404, detail="A comanda nao possui acesso digital ativo.")
        return Response(content=generate_qr_bytes(access["access_url"]), media_type="image/png")

    @app.get("/api/customer/command")
    async def customer_command(token: str):
        command = services.get_command_by_access_token(token)
        if not command:
            raise HTTPException(status_code=404, detail="Acesso invalido, revogado ou indisponivel.")
        return command

    @app.post("/api/commands/{command_id}/items")
    async def add_item(command_id: int, payload: ItemAdd, user: dict = Depends(ORDER_ROLES)):
        services.add_item(command_id, payload.product_id, payload.quantity, payload.notes, actor=user["username"])
        await manager.broadcast("command.updated", command_id=command_id, actor=user["username"])
        return services.get_command(command_id)

    @app.put("/api/commands/items/{item_id}/quantity")
    async def update_item_quantity(item_id: int, payload: QuantityUpdate, user: dict = Depends(ORDER_ROLES)):
        services.update_item_quantity(item_id, payload.quantity, actor=user["username"])
        await manager.broadcast("command.updated", item_id=item_id, actor=user["username"])
        return {"ok": True}

    @app.delete("/api/commands/items/{item_id}")
    async def remove_item(item_id: int, user: dict = Depends(ORDER_ROLES)):
        services.remove_item(item_id, actor=user["username"])
        await manager.broadcast("command.updated", item_id=item_id, actor=user["username"])
        return {"ok": True}

    @app.put("/api/commands/items/{item_id}/notes")
    async def set_item_notes(item_id: int, payload: NotesUpdate, user: dict = Depends(ORDER_ROLES)):
        services.set_item_notes(item_id, payload.notes, actor=user["username"])
        await manager.broadcast("command.updated", item_id=item_id, actor=user["username"])
        return {"ok": True}

    @app.put("/api/commands/items/{item_id}/kitchen-status")
    async def set_item_kitchen_status(item_id: int, payload: KitchenStatusUpdate, user: dict = Depends(KITCHEN_ROLES)):
        services.set_item_kitchen_status(item_id, payload.status, actor=user["username"])
        await manager.broadcast("kitchen.updated", item_id=item_id, status=payload.status, actor=user["username"])
        return {"ok": True}

    @app.get("/api/kitchen/queue")
    async def kitchen_queue(user: dict = Depends(KITCHEN_ROLES)):
        return services.list_kitchen_queue()

    @app.put("/api/commands/{command_id}/discount")
    async def set_discount(command_id: int, payload: DiscountUpdate, user: dict = Depends(ORDER_ROLES)):
        services.set_discount(command_id, payload.discount, actor=user["username"])
        await manager.broadcast("command.updated", command_id=command_id, actor=user["username"])
        return {"ok": True}

    @app.put("/api/commands/{command_id}/notes")
    async def set_notes(command_id: int, payload: NotesUpdate, user: dict = Depends(ORDER_ROLES)):
        services.set_notes(command_id, payload.notes, actor=user["username"])
        await manager.broadcast("command.updated", command_id=command_id, actor=user["username"])
        return {"ok": True}

    @app.put("/api/commands/{command_id}/customer")
    async def set_customer_info(command_id: int, payload: CustomerInfoUpdate, user: dict = Depends(ORDER_ROLES)):
        services.set_customer_info(command_id, payload.customer_name, payload.table_ref, actor=user["username"])
        await manager.broadcast("command.updated", command_id=command_id, actor=user["username"])
        return {"ok": True}

    @app.post("/api/commands/{command_id}/cancel")
    async def cancel_command(command_id: int, user: dict = Depends(ORDER_ROLES)):
        services.cancel_command(command_id, actor=user["username"])
        await manager.broadcast("command.closed", command_id=command_id, actor=user["username"])
        return {"ok": True}

    @app.post("/api/commands/{command_id}/pending")
    async def mark_pending(command_id: int, user: dict = Depends(ORDER_ROLES)):
        services.mark_as_pending(command_id, actor=user["username"])
        await manager.broadcast("command.updated", command_id=command_id, actor=user["username"])
        return {"ok": True}

    @app.post("/api/commands/{command_id}/finalize")
    async def finalize_command(command_id: int, payload: FinalizeRequest, user: dict = Depends(MONEY_ROLES)):
        payments = [p.dict() for p in payload.payments]
        result = services.finalize_command(command_id, payments, actor=user["username"])
        await manager.broadcast("command.closed", command_id=command_id, actor=user["username"])
        return result

    # ---------------- Caixa ----------------
    @app.get("/api/cash/current")
    async def current_cash(user: dict = Depends(ANYONE)):
        return services.get_open_cash_session()

    @app.get("/api/cash/history")
    async def cash_history(user: dict = Depends(MONEY_ROLES)):
        return services.list_cash_sessions_history()

    @app.get("/api/cash/{session_id}")
    async def get_cash(session_id: int, user: dict = Depends(MONEY_ROLES)):
        session = services.get_cash_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Caixa nao encontrado.")
        return session

    @app.get("/api/cash/{session_id}/summary")
    async def cash_summary(session_id: int, user: dict = Depends(MONEY_ROLES)):
        return services.get_cash_summary(session_id)

    @app.post("/api/cash/open")
    async def open_cash(payload: CashOpenRequest, user: dict = Depends(MONEY_ROLES)):
        session_id = services.open_cash_session(payload.opening_amount, payload.operator_name or user["username"],
                                                  payload.notes, actor=user["username"])
        await manager.broadcast("cash.opened", session_id=session_id, actor=user["username"])
        return {"id": session_id}

    @app.post("/api/cash/{session_id}/movement")
    async def add_movement(session_id: int, payload: MovementRequest, user: dict = Depends(MONEY_ROLES)):
        services.add_movement(session_id, payload.type, payload.amount, payload.reason, actor=user["username"])
        await manager.broadcast("cash.movement", session_id=session_id, actor=user["username"])
        return {"ok": True}

    @app.get("/api/cash/{session_id}/movements")
    async def list_movements(session_id: int, user: dict = Depends(MONEY_ROLES)):
        return services.list_movements(session_id)

    @app.post("/api/cash/{session_id}/close")
    async def close_cash(session_id: int, payload: CashCloseRequest, user: dict = Depends(ADMIN_ONLY)):
        result = services.close_cash_session(session_id, payload.counted_amount, payload.close_notes,
                                              user["username"], force=payload.force)
        await manager.broadcast("cash.closed", session_id=session_id, actor=user["username"])
        return result

    # ---------------- Relatorios ----------------
    @app.get("/api/reports/dashboard")
    async def dashboard(user: dict = Depends(ANYONE)):
        return services.get_dashboard_summary()

    @app.get("/api/reports/sales")
    async def sales_report(date_from: str, date_to: str, user: dict = Depends(ADMIN_ONLY)):
        return services.sales_report(date_from, date_to)

    @app.get("/api/reports/payments")
    async def payment_totals(date_from: str, date_to: str, user: dict = Depends(ADMIN_ONLY)):
        return services.payment_totals_by_period(date_from, date_to)

    @app.get("/api/reports/top-products")
    async def top_products(date_from: str, date_to: str, user: dict = Depends(ADMIN_ONLY)):
        return services.top_products_by_period(date_from, date_to)

    @app.get("/api/reports/audit")
    async def audit_log(entity_type: str = None, entity_id: int = None, limit: int = 200,
                        user: dict = Depends(ADMIN_ONLY)):
        return services.list_audit_log(limit=limit, entity_type=entity_type, entity_id=entity_id)

    # ---------------- Backup ----------------
    @app.post("/api/backup")
    async def trigger_backup(user: dict = Depends(ADMIN_ONLY)):
        backups_dir = get_data_dir() / "backups"
        path = backup_module.backup_database(str(backups_dir))
        return {"path": path}

    # ---------------- WebSocket ----------------
    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket, token: str = None):
        user = services.get_user_by_token(token) if token else None
        if not user:
            await websocket.close(code=4401)
            return
        await manager.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            await manager.disconnect(websocket)

    # ---------------- PWA estatica ----------------
    webapp_dir = resource_path("webapp")
    if webapp_dir.exists():
        app.mount("/app", StaticFiles(directory=str(webapp_dir), html=True), name="pwa")

    @app.get("/")
    async def root():
        if webapp_dir.exists():
            return JSONResponse({"ok": True, "pwa": "/app/", "docs": "/api/docs"})
        return JSONResponse({"ok": True})

    return app


app = create_app()
