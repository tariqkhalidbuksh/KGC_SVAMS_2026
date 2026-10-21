import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database

conn = database.get_db_connection()
raw = getattr(conn, "_conn", conn)
with raw.cursor() as cur:
    cur.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        ORDER BY table_name;
    """)
    tables = [r[0] for r in cur.fetchall()]
    print("--- LIVE POSTGRESQL DATABASE TABLES ---")
    for t in tables:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        cnt = cur.fetchone()[0]
        cur.execute("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position;
        """, (t,))
        cols = cur.fetchall()
        print(f"\n[TABLE] {t} ({cnt} rows)")
        for col_name, d_type, nullable, default in cols:
            default_str = f" DEFAULT {default}" if default else ""
            null_str = " NOT NULL" if nullable == "NO" else ""
            print(f"  - {col_name}: {d_type}{null_str}{default_str}")

conn.close()
