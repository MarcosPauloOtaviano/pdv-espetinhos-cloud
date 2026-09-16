"""Backup e restauracao do banco SQLite (copia de arquivo com timestamp)."""
import shutil
from datetime import datetime
from pathlib import Path

from app.utils import get_db_path


def default_backup_name() -> str:
    ts = datetime.now().strftime("%Y-%m-%d-%H-%M")
    return f"backup-dudair-{ts}.db"


def backup_database(dest_folder: str) -> str:
    """Copia o banco atual para dest_folder com nome com data/hora. Retorna o caminho final."""
    dest_dir = Path(dest_folder)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / default_backup_name()
    shutil.copy2(get_db_path(), dest_path)
    return str(dest_path)


def restore_database(backup_file: str) -> str:
    """Substitui o banco atual pelo arquivo de backup informado. Faz uma copia de seguranca do atual antes."""
    src = Path(backup_file)
    if not src.exists():
        raise FileNotFoundError(f"Arquivo de backup nao encontrado: {backup_file}")

    current_db = get_db_path()
    if current_db.exists():
        safety_copy = current_db.parent / f"pre-restore-{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}.db"
        shutil.copy2(current_db, safety_copy)

    shutil.copy2(src, current_db)
    return str(current_db)
