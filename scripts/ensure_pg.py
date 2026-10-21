import psycopg2
import os

PG_HOST = os.environ.get("PG_HOST", "127.0.0.1")
PG_PORT = int(os.environ.get("PG_PORT", "5432"))
PG_USER = os.environ.get("PG_USER", "postgres")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "")

def ensure_dbs():
    conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASSWORD, dbname="postgres")
    conn.autocommit = True
    cur = conn.cursor()
    for db in ["kgc_vams", "kgc_vams_test"]:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db,))
        if not cur.fetchone():
            cur.execute(f'CREATE DATABASE "{db}"')
            print(f"Created database {db}")
        else:
            print(f"Database {db} exists.")
    cur.close()
    conn.close()

if __name__ == "__main__":
    ensure_dbs()
