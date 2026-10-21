import psycopg2

def setup_functions():
    conn = psycopg2.connect(host='127.0.0.1', port=5432, dbname='kgc_vams', user='postgres')
    cur = conn.cursor()
    cur.execute("""
    CREATE OR REPLACE FUNCTION strftime(fmt text, ts timestamp) RETURNS text AS $$
    BEGIN
        IF fmt = '%H' THEN
            RETURN to_char(ts, 'HH24');
        ELSIF fmt = '%Y-%m-%d' THEN
            RETURN to_char(ts, 'YYYY-MM-DD');
        ELSE
            RETURN to_char(ts, 'YYYY-MM-DD HH24:MI:SS');
        END IF;
    END;
    $$ LANGUAGE plpgsql IMMUTABLE;
    """)
    conn.commit()
    cur.execute("SELECT strftime('%H', timestamp) FROM daily_logs LIMIT 1")
    res = cur.fetchone()[0]
    print(f"PostgreSQL strftime installed successfully. Verification result: {res}")
    conn.close()

if __name__ == '__main__':
    setup_functions()
