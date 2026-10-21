import psycopg2

conn = psycopg2.connect(host="127.0.0.1", port=5432, user="postgres", password="", dbname="kgc_vams")
cur = conn.cursor()
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
tables = [r[0] for r in cur.fetchall()]
for t in tables:
    cur.execute(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name='{t}'")
    cols = [f"{r[0]} ({r[1]})" for r in cur.fetchall()]
    print(f"Table '{t}':", ", ".join(cols))
conn.close()
