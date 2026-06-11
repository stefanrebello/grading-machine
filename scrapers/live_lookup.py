"""
scrapers/live_lookup.py
------------------------
Real-time on-demand scraper for grading company pop report data.
Fires live Playwright requests to PSA, CGC, SGC, BGS simultaneously.

Usage:
    from scrapers.live_lookup import lookup_card

    results = lookup_card(
        player="Michael Jordan",
        year=1986,
        set_name="Fleer",
        card_number="57"
    )
"""

import asyncio
import re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

TIMEOUT_MS = 20000  # 20 seconds per grader


# ══════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════

async def lookup_card_async(player: str, year: int, set_name: str, card_number: str = "") -> dict:
    query = build_query(player, year, set_name, card_number)
    print(f"\n🔍 Live lookup: {query}")
    print("⏳ Querying PSA, CGC, SGC, BGS simultaneously...\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )

        results = await asyncio.gather(
            scrape_psa(browser, player, year, set_name, card_number),
            scrape_cgc(browser, query),
            scrape_sgc(browser, query),
            scrape_bgs(browser, query),
            return_exceptions=True
        )

        await browser.close()

    graders = ["PSA", "CGC", "SGC", "BGS"]
    output = {}
    for grader, result in zip(graders, results):
        if isinstance(result, Exception):
            output[grader] = {"status": "error", "grader": grader, "error": str(result)}
        else:
            output[grader] = result

    return output


def lookup_card(player: str, year: int, set_name: str, card_number: str = "") -> dict:
    """Synchronous wrapper — call this from the machine."""
    return asyncio.run(lookup_card_async(player, year, set_name, card_number))


def build_query(player, year, set_name, card_number):
    parts = [str(year), set_name, player]
    if card_number:
        parts.append(f"#{card_number}")
    return " ".join(parts)


# ══════════════════════════════════════════════════════════════
# PSA
# Pop report: psacard.com uses a React app.
# We search their pop report, wait for results table to render,
# then parse grade rows.
# ══════════════════════════════════════════════════════════════

async def scrape_psa(browser, player, year, set_name, card_number) -> dict:
    page = await browser.new_page()
    try:
        await page.set_extra_http_headers({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"})

        # PSA pop search URL
        q = f"{year} {set_name} {player}"
        url = f"https://www.psacard.com/pop/search?q={q.replace(' ', '%20')}"
        await page.goto(url, timeout=TIMEOUT_MS, wait_until="domcontentloaded")

        # Wait for results to render
        try:
            await page.wait_for_selector("table, .pop-result, [class*='pop']", timeout=8000)
        except:
            await page.wait_for_timeout(5000)

        content = await page.content()
        soup = BeautifulSoup(content, "html.parser")

        # PSA renders a table with grade columns across the top (1-10)
        # and card rows below. We look for grade header + total pop counts.
        pop_data = []

        # Try standard table parse
        tables = soup.find_all("table")
        for table in tables:
            headers = [th.get_text(strip=True) for th in table.find_all("th")]
            grade_headers = [h for h in headers if re.match(r'^(10|[1-9](\.[5])?|Auth|Poor)$', h)]
            if grade_headers:
                for row in table.find_all("tr")[1:]:
                    cells = [td.get_text(strip=True) for td in row.find_all("td")]
                    if cells and len(cells) >= len(grade_headers):
                        for i, grade in enumerate(grade_headers):
                            count_idx = headers.index(grade)
                            if count_idx < len(cells):
                                pop_data.append({"grade": grade, "pop": cells[count_idx]})
                        break  # first matching row is the card

        # Fallback: look for any grade-like text near numbers
        if not pop_data:
            pop_data = _fallback_parse(soup, "PSA", grades=[str(i) for i in range(1, 11)])

        return {
            "status": "success",
            "grader": "PSA",
            "url": url,
            "pop_data": pop_data,
            "grade_range": "1-10 (whole numbers)"
        }

    except Exception as e:
        return {"status": "error", "grader": "PSA", "error": str(e)}
    finally:
        await page.close()


# ══════════════════════════════════════════════════════════════
# CGC
# Pop report: cgccards.com/trading-cards/pop-report/
# CGC has a cleaner API-driven interface
# ══════════════════════════════════════════════════════════════

async def scrape_cgc(browser, query) -> dict:
    page = await browser.new_page()
    try:
        await page.set_extra_http_headers({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"})

        url = f"https://www.cgccards.com/trading-cards/pop-report/?search={query.replace(' ', '+')}"
        await page.goto(url, timeout=TIMEOUT_MS, wait_until="domcontentloaded")

        try:
            await page.wait_for_selector("table, .pop-report-results, [class*='result']", timeout=8000)
        except:
            await page.wait_for_timeout(5000)

        content = await page.content()
        soup = BeautifulSoup(content, "html.parser")

        pop_data = []
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cells = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cells) >= 2:
                    grade = cells[0]
                    count = cells[1]
                    if re.match(r'^(10|[1-9](\.5)?|NM|VF|FN|VG|GD|FR|PR)$', grade):
                        pop_data.append({"grade": grade, "pop": count})

        if not pop_data:
            cgc_grades = ["10", "9.8", "9.6", "9.4", "9.2", "9", "8.5", "8", "7.5", "7", "6.5", "6", "5.5", "5"]
            pop_data = _fallback_parse(soup, "CGC", grades=cgc_grades)

        return {
            "status": "success",
            "grader": "CGC",
            "url": url,
            "pop_data": pop_data,
            "grade_range": "1-10 (half grades)"
        }

    except Exception as e:
        return {"status": "error", "grader": "CGC", "error": str(e)}
    finally:
        await page.close()


# ══════════════════════════════════════════════════════════════
# SGC
# Pop report: sgccard.com/pop-report
# ══════════════════════════════════════════════════════════════

async def scrape_sgc(browser, query) -> dict:
    page = await browser.new_page()
    try:
        await page.set_extra_http_headers({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"})

        url = f"https://www.sgccard.com/pop-report?search={query.replace(' ', '+')}"
        await page.goto(url, timeout=TIMEOUT_MS, wait_until="domcontentloaded")

        try:
            await page.wait_for_selector("table, .pop-results, [class*='grade']", timeout=8000)
        except:
            await page.wait_for_timeout(5000)

        content = await page.content()
        soup = BeautifulSoup(content, "html.parser")

        pop_data = []
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cells = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cells) >= 2:
                    grade = cells[0]
                    count = cells[-1]
                    if re.match(r'^(10|[1-9](\.5)?|Auth)$', grade):
                        pop_data.append({"grade": grade, "pop": count})

        if not pop_data:
            sgc_grades = ["10", "9.5", "9", "8.5", "8", "7.5", "7", "6.5", "6", "5.5", "5"]
            pop_data = _fallback_parse(soup, "SGC", grades=sgc_grades)

        return {
            "status": "success",
            "grader": "SGC",
            "url": url,
            "pop_data": pop_data,
            "grade_range": "1-10 (half grades)"
        }

    except Exception as e:
        return {"status": "error", "grader": "SGC", "error": str(e)}
    finally:
        await page.close()


# ══════════════════════════════════════════════════════════════
# BGS / BECKETT
# Pop report: beckett.com/grading/pop
# BGS includes subgrades (centering, corners, edges, surface)
# ══════════════════════════════════════════════════════════════

async def scrape_bgs(browser, query) -> dict:
    page = await browser.new_page()
    try:
        await page.set_extra_http_headers({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"})

        url = f"https://www.beckett.com/grading/pop?search={query.replace(' ', '+')}"
        await page.goto(url, timeout=TIMEOUT_MS, wait_until="domcontentloaded")

        try:
            await page.wait_for_selector("table, .pop-table, [class*='grading-pop']", timeout=8000)
        except:
            await page.wait_for_timeout(5000)

        content = await page.content()
        soup = BeautifulSoup(content, "html.parser")

        pop_data = []
        subgrades = {}

        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            headers = [th.get_text(strip=True) for th in table.find_all("th")]

            # BGS has subgrade columns: Centering, Corners, Edges, Surface
            subgrade_cols = ["Centering", "Corners", "Edges", "Surface"]

            for row in rows:
                cells = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cells) >= 2:
                    grade = cells[0]
                    if re.match(r'^(Black Label|10|9\.5|[1-9](\.5)?)$', grade):
                        entry = {"grade": grade, "pop": cells[1] if len(cells) > 1 else "?"}
                        # Try to grab subgrades if present
                        for col in subgrade_cols:
                            if col in headers:
                                idx = headers.index(col)
                                if idx < len(cells):
                                    entry[col.lower()] = cells[idx]
                        pop_data.append(entry)

        if not pop_data:
            bgs_grades = ["Black Label", "10", "9.5", "9", "8.5", "8", "7.5", "7"]
            pop_data = _fallback_parse(soup, "BGS", grades=bgs_grades)

        return {
            "status": "success",
            "grader": "BGS",
            "url": url,
            "pop_data": pop_data,
            "grade_range": "1-10 (half grades) + Black Label + subgrades"
        }

    except Exception as e:
        return {"status": "error", "grader": "BGS", "error": str(e)}
    finally:
        await page.close()


# ══════════════════════════════════════════════════════════════
# FALLBACK PARSER
# Last resort — scan all text for grade patterns near numbers
# ══════════════════════════════════════════════════════════════

def _fallback_parse(soup, grader, grades):
    """Scan page text for grade values near population counts."""
    results = []
    text = soup.get_text(separator="\n", strip=True)
    lines = text.split("\n")
    for i, line in enumerate(lines):
        for grade in grades:
            if line.strip() == grade or line.strip() == f"PSA {grade}" or line.strip() == f"Grade {grade}":
                # Look at next few lines for a number
                for j in range(1, 4):
                    if i + j < len(lines):
                        candidate = lines[i + j].strip().replace(",", "")
                        if candidate.isdigit():
                            results.append({"grade": grade, "pop": candidate})
                            break
    return results


# ══════════════════════════════════════════════════════════════
# RESULT FORMATTER
# ══════════════════════════════════════════════════════════════

def format_results(results: dict) -> None:
    print("\n" + "═" * 55)
    print("  📊 LIVE GRADER POP REPORT RESULTS")
    print("═" * 55)

    for grader, data in results.items():
        print(f"\n📋 {grader}  ({data.get('grade_range', '')})")
        if data["status"] == "error":
            print(f"   ❌ {data.get('error', 'Unknown error')}")
        else:
            pop = data.get("pop_data", [])
            if pop:
                for entry in pop:
                    grade_str = f"Grade {entry['grade']:>10}"
                    pop_str = f"{entry['pop']:>6} graded"
                    extras = {k: v for k, v in entry.items() if k not in ("grade", "pop")}
                    extra_str = "  " + "  ".join(f"{k}: {v}" for k, v in extras.items()) if extras else ""
                    print(f"   {grade_str} → {pop_str}{extra_str}")
            else:
                print("   ⚠️  No pop data returned — parser may need tuning for this site's current HTML")
            print(f"   🔗 {data.get('url', '')}")

    print("\n" + "═" * 55)


# ══════════════════════════════════════════════════════════════
# TEST RUN
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    results = lookup_card(
        player="Michael Jordan",
        year=1986,
        set_name="Fleer",
        card_number="57"
    )
    format_results(results)
