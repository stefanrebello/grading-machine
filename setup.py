"""
grading_machine_db/setup.py
----------------------------
Sets up the SQLite version of the grading machine database
for local development / on-machine use.

Switch to PostgreSQL for production by swapping the connection string.
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "grading_machine.db")


def get_connection():
    """Return a database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # allows dict-style access
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def setup_database():
    """Create all tables and seed grading companies."""
    conn = get_connection()
    cursor = conn.cursor()

    # ── GRADING COMPANIES ──────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS grading_companies (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            code             TEXT UNIQUE NOT NULL,
            full_name        TEXT NOT NULL,
            website          TEXT,
            grade_min        REAL,
            grade_max        REAL,
            uses_half_grades INTEGER DEFAULT 0,
            uses_subgrades   INTEGER DEFAULT 0,
            notes            TEXT,
            created_at       TEXT DEFAULT (datetime('now'))
        )
    """)

    # ── GRADE SCALES ──────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS grade_scales (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id   INTEGER REFERENCES grading_companies(id) ON DELETE CASCADE,
            grade_value  REAL NOT NULL,
            grade_label  TEXT,
            grade_short  TEXT,
            description  TEXT,
            UNIQUE(company_id, grade_value)
        )
    """)

    # ── ITEMS ─────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            item_type    TEXT DEFAULT 'trading_card',
            sport        TEXT,
            card_year    INTEGER,
            manufacturer TEXT,
            set_name     TEXT,
            card_number  TEXT,
            player_name  TEXT,
            variation    TEXT,
            rookie_card  INTEGER DEFAULT 0,
            parallel     TEXT,
            print_run    INTEGER,
            notes        TEXT,
            created_at   TEXT DEFAULT (datetime('now'))
        )
    """)

    # ── POPULATION REPORTS ────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS population_reports (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id      INTEGER REFERENCES items(id) ON DELETE CASCADE,
            company_id   INTEGER REFERENCES grading_companies(id) ON DELETE CASCADE,
            grade_value  REAL NOT NULL,
            pop_count    INTEGER DEFAULT 0,
            pop_higher   INTEGER DEFAULT 0,
            scraped_at   TEXT DEFAULT (datetime('now')),
            source_url   TEXT,
            UNIQUE(item_id, company_id, grade_value)
        )
    """)

    # ── SALE PRICES ───────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sale_prices (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id      INTEGER REFERENCES items(id) ON DELETE CASCADE,
            company_id   INTEGER REFERENCES grading_companies(id) ON DELETE CASCADE,
            grade_value  REAL NOT NULL,
            cert_number  TEXT,
            sale_price   REAL NOT NULL,
            sale_date    TEXT,
            platform     TEXT,
            listing_url  TEXT,
            scraped_at   TEXT DEFAULT (datetime('now'))
        )
    """)

    # ── REFERENCE IMAGES ──────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reference_images (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id      INTEGER REFERENCES items(id) ON DELETE CASCADE,
            company_id   INTEGER REFERENCES grading_companies(id) ON DELETE CASCADE,
            grade_value  REAL,
            image_path   TEXT,
            image_url    TEXT,
            image_side   TEXT DEFAULT 'front',
            cert_number  TEXT,
            scraped_at   TEXT DEFAULT (datetime('now'))
        )
    """)

    # ── GRADING CRITERIA ──────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS grading_criteria (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id   INTEGER REFERENCES grading_companies(id) ON DELETE CASCADE,
            grade_value  REAL,
            category     TEXT,
            description  TEXT NOT NULL,
            tolerance    TEXT,
            source_url   TEXT,
            created_at   TEXT DEFAULT (datetime('now'))
        )
    """)

    # ── SCRAPE LOG ────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scrape_log (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id     INTEGER REFERENCES grading_companies(id),
            source_url     TEXT,
            scrape_type    TEXT,
            status         TEXT DEFAULT 'pending',
            records_added  INTEGER DEFAULT 0,
            error_message  TEXT,
            scraped_at     TEXT DEFAULT (datetime('now'))
        )
    """)

    # ── INDEXES ───────────────────────────────────────────────
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_player   ON items(player_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_set      ON items(set_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pop_item       ON population_reports(item_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pop_company    ON population_reports(company_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sales_item     ON sale_prices(item_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sales_grade    ON sale_prices(grade_value)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sales_date     ON sale_prices(sale_date)")

    # ── SEED GRADING COMPANIES ────────────────────────────────
    companies = [
        ("PSA", "Professional Sports Authenticator",  "www.psacard.com",    1, 10, 0, 0, "Most widely recognized. Grades 1-10 whole numbers only."),
        ("BGS", "Beckett Grading Services",           "www.beckett.com",    1, 10, 1, 1, "Uses half grades. Has 4 subgrades: centering, corners, edges, surface."),
        ("SGC", "Sportscard Guaranty Corporation",    "www.sgccard.com",    1, 10, 1, 0, "Uses half grades. Known for vintage cards."),
        ("CGC", "Certified Guaranty Company",         "www.cgccards.com",   1, 10, 1, 0, "Expanding into trading cards from comics."),
        ("HGA", "Hybrid Grading Approach",            "www.hgagrading.com", 1, 10, 1, 1, "Algorithmic grading. Uses subgrades."),
        ("ACE", "ACE Grading",                        "www.acegrading.com", 1, 10, 1, 0, "UK-based, growing internationally."),
        ("GMA", "Global Maker Authentication",        "www.gmagrading.com", 1, 10, 0, 0, "Budget grading option."),
    ]

    cursor.executemany("""
        INSERT OR IGNORE INTO grading_companies 
        (code, full_name, website, grade_min, grade_max, uses_half_grades, uses_subgrades, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, companies)

    conn.commit()
    conn.close()
    print(f"✅ Database created at: {DB_PATH}")
    print("✅ Tables created: grading_companies, grade_scales, items, population_reports, sale_prices, reference_images, grading_criteria, scrape_log")
    print("✅ Seeded 7 grading companies: PSA, BGS, SGC, CGC, HGA, ACE, GMA")


if __name__ == "__main__":
    setup_database()
