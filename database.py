import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")


def query(sql, params=None):
    """Run a SELECT and return list of dicts."""
    conn = get_conn()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    c.execute(sql, params or ())
    rows = [dict(r) for r in c.fetchall()]
    c.close()
    conn.close()
    return rows


def execute(sql, params=None):
    """Run an INSERT/UPDATE/DELETE."""
    conn = get_conn()
    c = conn.cursor()
    c.execute(sql, params or ())
    conn.commit()
    c.close()
    conn.close()


def get_conn():
    conn = psycopg2.connect(DATABASE_URL)
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS flavors (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            category TEXT,                  
            description TEXT,
            is_available BOOLEAN DEFAULT TRUE,
            is_vegan BOOLEAN DEFAULT FALSE,
            is_dairy_free BOOLEAN DEFAULT FALSE,
            contains_nuts BOOLEAN DEFAULT FALSE,
            popularity_score REAL DEFAULT 5.0,  
            season TEXT,                    
            days_since_last_featured INTEGER DEFAULT 999,
            created_at TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS daily_features (
            id SERIAL PRIMARY KEY,
            date TEXT NOT NULL,
            flavor_id INTEGER REFERENCES flavors(id),
            slot INTEGER CHECK (slot IN (1, 2, 3)),  -- position 1, 2, or 3
            reason TEXT,                              -- why this flavor was chosen
            UNIQUE (date, slot)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS feature_rules (
            id SERIAL PRIMARY KEY,
            rule_key TEXT UNIQUE NOT NULL,
            rule_value TEXT NOT NULL,
            description TEXT
        )
    """)

    conn.commit()
    c.close()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("Database initialised.")