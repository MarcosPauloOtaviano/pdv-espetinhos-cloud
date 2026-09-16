"""Funcoes utilitarias compartilhadas: paths (dev/PyInstaller), formatacao e senha."""
import sys
import os
import socket
import hashlib
import hmac
import secrets
from datetime import datetime
from pathlib import Path

APP_NAME = "DUDAIR-PDV"
DEFAULT_PORT = int(os.environ.get("DUDAIR_PORT", 8765))


def get_lan_ip() -> str:
    """Melhor esforco para achar o IP da rede local do computador (para o celular acessar)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def app_base_dir() -> Path:
    """Pasta onde o executavel (ou main.py) esta rodando."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_path(relative: str) -> Path:
    """Caminho para assets, funciona tanto em dev quanto empacotado (PyInstaller _MEIPASS)."""
    if is_frozen() and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent.parent
    return base / relative


def _dir_is_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except Exception:
        return False


def get_data_dir() -> Path:
    """
    Resolve a pasta de dados gravavel:
    - Modo portatil (pendrive): usa <pasta_do_app>/data se for gravavel.
    - Modo instalado (Program Files, somente leitura): usa %LOCALAPPDATA%/DUDAIR-PDV.
    Pode ser forcado via variavel de ambiente DUDAIR_DATA_DIR.
    """
    forced = os.environ.get("DUDAIR_DATA_DIR")
    if forced:
        p = Path(forced)
        p.mkdir(parents=True, exist_ok=True)
        return p

    portable_dir = app_base_dir() / "data"
    if _dir_is_writable(portable_dir):
        return portable_dir

    local_app_data = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    installed_dir = Path(local_app_data) / APP_NAME
    installed_dir.mkdir(parents=True, exist_ok=True)
    return installed_dir


def get_db_path() -> Path:
    return get_data_dir() / "database.db"


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def format_currency(value) -> str:
    try:
        value = float(value or 0)
    except (TypeError, ValueError):
        value = 0.0
    text = f"{value:,.2f}"
    text = text.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {text}"


def parse_currency_input(text: str) -> float:
    """Converte texto digitado (aceita virgula ou ponto) em float. Retorna 0.0 se invalido."""
    if text is None:
        return 0.0
    cleaned = str(text).strip().replace("R$", "").strip()
    cleaned = cleaned.replace(".", "").replace(",", ".") if "," in cleaned else cleaned
    try:
        return round(float(cleaned), 2)
    except ValueError:
        return 0.0


def hash_password(password: str, salt: str = None) -> str:
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest_hex = stored.split("$", 1)
    except ValueError:
        return False
    check = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return hmac.compare_digest(check.hex(), digest_hex)
