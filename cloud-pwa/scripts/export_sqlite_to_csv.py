import argparse
import csv
import sqlite3
from pathlib import Path


TABLES = [
    "users",
    "categories",
    "products",
    "cash_sessions",
    "cash_movements",
    "commands",
    "command_items",
    "payments",
    "settings",
    "audit_log",
]


def export_table(conn, table, out_dir):
    try:
        rows = conn.execute(f"select * from {table}").fetchall()
    except sqlite3.OperationalError:
        return
    path = out_dir / f"{table}.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        if not rows:
            cols = [row[1] for row in conn.execute(f"pragma table_info({table})")]
            writer = csv.writer(handle, delimiter=";")
            writer.writerow(cols)
            return
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(rows[0].keys())
        for row in rows:
            writer.writerow([row[key] for key in row.keys()])


def main():
    parser = argparse.ArgumentParser(description="Exporta o SQLite do DU'DAIR PDV para CSV.")
    parser.add_argument("--db", required=True, help="Caminho do database.db local")
    parser.add_argument("--out", required=True, help="Pasta de saida dos CSVs")
    args = parser.parse_args()

    db_path = Path(args.db)
    out_dir = Path(args.out)
    if not db_path.exists():
        raise SystemExit(f"Banco nao encontrado: {db_path}")
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        for table in TABLES:
            export_table(conn, table, out_dir)
    finally:
        conn.close()

    print(f"CSVs exportados em: {out_dir}")


if __name__ == "__main__":
    main()
