import sqlite3
import json
import sys
from pathlib import Path


def main():
    if len(sys.argv) < 2:
        print("Usage: query_conversation.py <conversation_id>|--all", file=sys.stderr)
        sys.exit(2)

    arg = sys.argv[1]
    conv_id = None
    list_all = False
    if arg == '--all':
        list_all = True
    else:
        conv_id = arg
    db_path = Path.cwd() / "infobip.db"
    if not db_path.exists():
        print(f"Database not found at {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    results = {}
    schema = {}

    # Discover all tables and their columns first
    try:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        all_tables = [r[0] for r in cur.fetchall()]
        for table in all_tables:
            try:
                cur.execute(f"PRAGMA table_info('{table}')")
                cols = [c[1] for c in cur.fetchall()]
                schema[table] = cols
            except Exception as e:
                schema[table] = {"error": str(e)}
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

    # Query only tables that have an id_conversation-like column
    id_column_candidates = ['id_cinversation', 'id_conversation']
    for table, cols in schema.items():
        if isinstance(cols, dict) and 'error' in cols:
            results[table] = cols
            continue
        column_to_use = None
        for cand in id_column_candidates:
            if cand in cols:
                column_to_use = cand
                break
        if column_to_use:
            try:
                if list_all:
                    cur.execute(f"SELECT * FROM {table}")
                    rows = [dict(r) for r in cur.fetchall()]
                else:
                    cur.execute(f"SELECT * FROM {table} WHERE {column_to_use}=?", (conv_id,))
                    rows = [dict(r) for r in cur.fetchall()]
                results[table] = rows
            except Exception as e:
                results[table] = {"error": str(e)}

    output = {"schema": schema, "results": results}
    print(json.dumps(output, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
