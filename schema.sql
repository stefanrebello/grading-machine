-- ============================================================
-- GRADING MACHINE DATABASE SCHEMA
-- ============================================================
-- Supports: PSA, BGS/Beckett, SGC, CGC, HGA
-- ============================================================


-- ============================================================
-- GRADING COMPANIES
-- ============================================================
CREATE TABLE grading_companies (
    id              SERIAL PRIMARY KEY,
    code            VARCHAR(10) UNIQUE NOT NULL,   -- e.g. 'PSA', 'BGS', 'SGC'
    full_name       VARCHAR(100) NOT NULL,          -- e.g. 'Professional Sports Authenticator'
    website         VARCHAR(255),
    grade_min       DECIMAL(4,1),                  -- lowest grade (e.g. 1.0)
    grade_max       DECIMAL(4,1),                  -- highest grade (e.g. 10.0)
    uses_half_grades BOOLEAN DEFAULT FALSE,         -- BGS uses 9.5, 8.5 etc.
    uses_subgrades  BOOLEAN DEFAULT FALSE,          -- BGS has centering/corners/edges/surface
    notes           TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Seed the major grading companies
INSERT INTO grading_companies (code, full_name, website, grade_min, grade_max, uses_half_grades, uses_subgrades, notes) VALUES
('PSA',     'Professional Sports Authenticator',  'www.psacard.com',      1,   10,  FALSE, FALSE, 'Most widely recognized. Grades 1-10 whole numbers only.'),
('BGS',     'Beckett Grading Services',           'www.beckett.com',      1,   10,  TRUE,  TRUE,  'Uses half grades. Has 4 subgrades: centering, corners, edges, surface.'),
('SGC',     'Sportscard Guaranty Corporation',    'www.sgccard.com',      1,   10,  TRUE,  FALSE, 'Uses half grades. Known for vintage cards.'),
('CGC',     'Certified Guaranty Company',         'www.cgccards.com',     1,   10,  TRUE,  FALSE, 'Expanding into trading cards from comics.'),
('HGA',     'Hybrid Grading Approach',            'www.hgagrading.com',   1,   10,  TRUE,  TRUE,  'Algorithmic grading. Uses subgrades.'),
('ACE',     'ACE Grading',                        'www.acegrading.com',   1,   10,  TRUE,  FALSE, 'UK-based, growing internationally.'),
('GMA',     'Global Marker Authentication',       'www.gmagrading.com',   1,   10,  FALSE, FALSE, 'Budget grading option.');


-- ============================================================
-- GRADING SCALES PER COMPANY
-- (Each valid grade value a company can assign)
-- ============================================================
CREATE TABLE grade_scales (
    id              SERIAL PRIMARY KEY,
    company_id      INT REFERENCES grading_companies(id) ON DELETE CASCADE,
    grade_value     DECIMAL(4,1) NOT NULL,          -- e.g. 10, 9.5, 9, 8.5
    grade_label     VARCHAR(50),                    -- e.g. 'Gem Mint', 'Mint', 'Near Mint'
    grade_short     VARCHAR(20),                    -- e.g. 'GM', 'MT', 'NM'
    description     TEXT,
    UNIQUE(company_id, grade_value)
);


-- ============================================================
-- ITEMS / CARDS
-- (The actual collectible being graded)
-- ============================================================
CREATE TABLE items (
    id              SERIAL PRIMARY KEY,
    item_type       VARCHAR(50) DEFAULT 'trading_card',  -- trading_card, comic, coin, etc.
    sport           VARCHAR(50),                   -- football, basketball, baseball, pokemon, etc.
    card_year       INT,
    manufacturer    VARCHAR(100),                  -- Topps, Panini, Upper Deck, etc.
    set_name        VARCHAR(255),                  -- e.g. '1986-87 Fleer Basketball'
    card_number     VARCHAR(50),                   -- e.g. '#57'
    player_name     VARCHAR(255),
    variation       VARCHAR(255),                  -- e.g. 'Holo', 'Refractor', '1st Edition'
    rookie_card     BOOLEAN DEFAULT FALSE,
    parallel        VARCHAR(100),                  -- e.g. 'Gold', 'Silver', 'Rainbow'
    print_run       INT,                           -- numbered cards e.g. /25
    notes           TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_items_player ON items(player_name);
CREATE INDEX idx_items_set ON items(set_name);
CREATE INDEX idx_items_year ON items(card_year);


-- ============================================================
-- POPULATION REPORTS
-- (How many of each grade exist per grader)
-- ============================================================
CREATE TABLE population_reports (
    id              SERIAL PRIMARY KEY,
    item_id         INT REFERENCES items(id) ON DELETE CASCADE,
    company_id      INT REFERENCES grading_companies(id) ON DELETE CASCADE,
    grade_value     DECIMAL(4,1) NOT NULL,
    pop_count       INT DEFAULT 0,                 -- number graded at this grade
    pop_higher      INT DEFAULT 0,                 -- number graded higher (for PSA qualifier)
    scraped_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_url      VARCHAR(500),
    UNIQUE(item_id, company_id, grade_value)
);

CREATE INDEX idx_pop_item ON population_reports(item_id);
CREATE INDEX idx_pop_company ON population_reports(company_id);


-- ============================================================
-- SALE PRICES
-- (Historical sales data per item, grader, grade)
-- ============================================================
CREATE TABLE sale_prices (
    id              SERIAL PRIMARY KEY,
    item_id         INT REFERENCES items(id) ON DELETE CASCADE,
    company_id      INT REFERENCES grading_companies(id) ON DELETE CASCADE,
    grade_value     DECIMAL(4,1) NOT NULL,
    cert_number     VARCHAR(100),                  -- grading cert/serial number if known
    sale_price      DECIMAL(10,2) NOT NULL,
    sale_date       DATE,
    platform        VARCHAR(100),                  -- eBay, PWCC, Goldin, etc.
    listing_url     VARCHAR(500),
    scraped_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_sales_item ON sale_prices(item_id);
CREATE INDEX idx_sales_company ON sale_prices(company_id);
CREATE INDEX idx_sales_date ON sale_prices(sale_date);
CREATE INDEX idx_sales_grade ON sale_prices(grade_value);


-- ============================================================
-- REFERENCE IMAGES
-- (Images of graded examples per item/grader/grade)
-- ============================================================
CREATE TABLE reference_images (
    id              SERIAL PRIMARY KEY,
    item_id         INT REFERENCES items(id) ON DELETE CASCADE,
    company_id      INT REFERENCES grading_companies(id) ON DELETE CASCADE,
    grade_value     DECIMAL(4,1),                  -- NULL if ungraded reference
    image_path      VARCHAR(500),                  -- local file path
    image_url       VARCHAR(500),                  -- original source URL
    image_side      VARCHAR(20) DEFAULT 'front',   -- front, back, top, bottom, left, right
    cert_number     VARCHAR(100),
    scraped_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_images_item ON reference_images(item_id);
CREATE INDEX idx_images_company ON reference_images(company_id);


-- ============================================================
-- GRADING CRITERIA / STANDARDS
-- (The rubric each company uses — for ML training)
-- ============================================================
CREATE TABLE grading_criteria (
    id              SERIAL PRIMARY KEY,
    company_id      INT REFERENCES grading_companies(id) ON DELETE CASCADE,
    grade_value     DECIMAL(4,1),                  -- NULL = general standard
    category        VARCHAR(100),                  -- centering, corners, edges, surface, print
    description     TEXT NOT NULL,
    tolerance       VARCHAR(100),                  -- e.g. '55/45 or better'
    source_url      VARCHAR(500),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ============================================================
-- SCRAPE LOG
-- (Track what was scraped, when, and status)
-- ============================================================
CREATE TABLE scrape_log (
    id              SERIAL PRIMARY KEY,
    company_id      INT REFERENCES grading_companies(id),
    source_url      VARCHAR(500),
    scrape_type     VARCHAR(50),                   -- pop_report, sale_price, reference_image
    status          VARCHAR(20) DEFAULT 'pending', -- pending, success, failed, skipped
    records_added   INT DEFAULT 0,
    error_message   TEXT,
    scraped_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ============================================================
-- VIEWS — handy queries pre-built
-- ============================================================

-- Average sale price per item per grader per grade
CREATE VIEW avg_prices AS
SELECT 
    i.player_name,
    i.card_year,
    i.set_name,
    i.card_number,
    gc.code AS grader,
    sp.grade_value,
    COUNT(sp.id) AS num_sales,
    ROUND(AVG(sp.sale_price), 2) AS avg_price,
    MIN(sp.sale_price) AS min_price,
    MAX(sp.sale_price) AS max_price
FROM sale_prices sp
JOIN items i ON sp.item_id = i.id
JOIN grading_companies gc ON sp.company_id = gc.id
GROUP BY i.player_name, i.card_year, i.set_name, i.card_number, gc.code, sp.grade_value
ORDER BY avg_price DESC;


-- Population summary per item across all graders
CREATE VIEW pop_summary AS
SELECT
    i.player_name,
    i.card_year,
    i.set_name,
    i.card_number,
    gc.code AS grader,
    pr.grade_value,
    pr.pop_count,
    pr.scraped_at
FROM population_reports pr
JOIN items i ON pr.item_id = i.id
JOIN grading_companies gc ON pr.company_id = gc.id
ORDER BY i.player_name, gc.code, pr.grade_value DESC;
