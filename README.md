# Grading Machine Database

## Overview
SQLite database (upgradeable to PostgreSQL) that stores reference data
from all major card grading companies to power the in-store grading machine.

---

## Files
| File | Purpose |
|------|---------|
| `setup.py` | Creates the database, all tables, and seeds grading companies |
| `schema.sql` | PostgreSQL version of the schema (for production upgrade) |
| `grading_machine.db` | The live SQLite database file |

---

## Tables

### `grading_companies`
One row per grader. Pre-seeded with 7 companies.
| Company | Code | Half Grades | Subgrades |
|---------|------|-------------|-----------|
| Professional Sports Authenticator | PSA | ❌ | ❌ |
| Beckett Grading Services | BGS | ✅ | ✅ |
| Sportscard Guaranty Corporation | SGC | ✅ | ❌ |
| Certified Guaranty Company | CGC | ✅ | ❌ |
| Hybrid Grading Approach | HGA | ✅ | ✅ |
| ACE Grading | ACE | ✅ | ❌ |
| Global Maker Authentication | GMA | ❌ | ❌ |

### `grade_scales`
Valid grade values + labels per company (e.g. PSA 10 = "Gem Mint")

### `items`
Every card/collectible in the reference database.
Includes: year, manufacturer, set, card number, player, variation, rookie flag, parallel, print run.

### `population_reports`
How many of each grade exist per item per grader.
Scraped from PSA pop report, Beckett, etc.

### `sale_prices`
Historical sale prices per item/grader/grade.
Scraped from eBay sold listings, PWCC, Goldin, 130point, Mavin.

### `reference_images`
Images of graded examples — front and back — per item/grader/grade.
Stored as local file paths + original source URLs.

### `grading_criteria`
The rubric each company uses (centering tolerances, corner standards, etc.)
Used for ML model training.

### `scrape_log`
Tracks every scrape job — URL, type, status, records added, errors.

---

## Next Steps
- [ ] Build scrapers per company/source
- [ ] Add `grade_scales` seed data per company
- [ ] Add grading criteria text per company
- [ ] Build query helpers (lookup by player, set, grade)
- [ ] Connect to machine vision pipeline
