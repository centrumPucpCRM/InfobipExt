import sqlite3
import json
from pathlib import Path


def main():
    db_path = Path.cwd() / "infobip.db"
    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return 1

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    try:
        cur.execute("SELECT * FROM conversation_ext ORDER BY id")
        rows = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        print(f"Error querying conversation_ext: {e}")
        return 2

    out_dir = Path.cwd() / "output"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / "conversation_ext_all.json"
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2, default=str)

    print(f"Wrote {len(rows)} records to {out_file}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
