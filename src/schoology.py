"""Schoology scraping: login, discover children, overdue, due today/tomorrow."""

import re
from datetime import date, timedelta
from playwright.async_api import async_playwright

from src.config import (
    SCHOOLOGY_USER, SCHOOLOGY_PASS, SCHOOLOGY_DOMAIN,
    STUDENT_NAMES, MAX_DAYS_OVERDUE, DEBUG,
)
from src.utils import next_school_day, screenshot


async def _login(page):
    print("Logging in to Schoology...")
    await page.goto(f"https://{SCHOOLOGY_DOMAIN}/login")
    await page.wait_for_load_state("networkidle")
    await page.fill("input[name='mail']", SCHOOLOGY_USER)
    await page.fill("input[name='pass']", SCHOOLOGY_PASS)
    await page.click("input[type='submit']")
    await page.wait_for_load_state("networkidle")
    print(f"Logged in → {await page.title()}")


async def discover_children(page) -> dict[str, str]:
    """Returns {student_name: student_id} from the parent dropdown."""
    await page.goto(f"https://{SCHOOLOGY_DOMAIN}/parent/home")
    await page.wait_for_load_state("networkidle")

    await page.evaluate("""() => {
        const btn = [...document.querySelectorAll('button')]
            .find(b => b.querySelector('img') && b.textContent.trim().length > 0);
        if (btn) btn.click();
    }""")
    await page.wait_for_timeout(600)

    links    = await page.query_selector_all("a[href*='/parent/switch_child/']")
    children = {}
    for link in links:
        text = await link.inner_text()
        name = text.strip().split("\n")[0].strip()
        href = await link.get_attribute("href")
        m    = re.search(r"/parent/switch_child/(\d+)", href)
        if m:
            children[name] = m.group(1)
            print(f"  Found: {name} (id={m.group(1)})")

    return children


async def get_overdue(page, student_id: str) -> list[str]:
    """Fetch overdue assignments within MAX_DAYS_OVERDUE days."""
    await page.goto(f"https://{SCHOOLOGY_DOMAIN}/home/overdue-popup/{student_id}/parent")
    await page.wait_for_load_state("networkidle")
    await screenshot(page, f"overdue_{student_id}")

    text    = await page.inner_text("main")
    pattern = re.compile(r"(.+?)\s+(\d+)\s+days?\s+overdue\s*(.+?)(?=\n|$)", re.MULTILINE)
    results = []

    for m in pattern.finditer(text):
        name, days, course = m.group(1).strip(), int(m.group(2)), m.group(3).strip()
        if name.lower() in ("assignment.", "discussion.", "assignment", "discussion"):
            continue
        if days > MAX_DAYS_OVERDUE:
            continue
        results.append(f"{name} | {course} | {days} day{'s' if days != 1 else ''} overdue")
        print(f"  🔴 {days}d — {name} ({course})")

    return results


async def get_due_on(page, student_id: str, targets: list[date]) -> list[str]:
    """
    Fetch assignments due on any of the target dates.
    Scrapes the UPCOMING section of /parent/home in one page load.
    """
    await page.goto(f"https://{SCHOOLOGY_DOMAIN}/parent/switch_child/{student_id}")
    await page.wait_for_load_state("networkidle")
    await page.goto(f"https://{SCHOOLOGY_DOMAIN}/parent/home")
    await page.wait_for_load_state("networkidle")
    await screenshot(page, f"home_{student_id}")

    text  = await page.inner_text("main")
    lines = [l.strip() for l in text.splitlines()]

    today   = date.today()
    results = []
    seen    = set()

    for target in targets:
        target_str = target.strftime("%A, %B %-d, %Y")
        if target == today:
            day_label = "Today"
        elif target == today + timedelta(days=1):
            day_label = "Tomorrow"
        else:
            day_label = target.strftime("%A")
        print(f"  Looking for: '{target_str}' ({day_label})")

        for i, line in enumerate(lines):
            if not line.startswith("Due ") or target_str not in line:
                continue
            time_m   = re.search(r"at\s+(\d+:\d+\s*[ap]m)", line, re.IGNORECASE)
            time_str = time_m.group(1) if time_m else ""

            name = ""
            for j in range(i - 1, max(0, i - 5), -1):
                candidate = lines[j]
                if candidate and candidate.lower() not in (
                    "assignment.", "discussion.", "assignment", "discussion",
                    "upcoming", "overdue", ""
                ):
                    name = candidate
                    break

            course = lines[i + 1] if i + 1 < len(lines) else ""
            key    = (name, target_str)

            if name and key not in seen:
                seen.add(key)
                results.append(f"{name} | {course} | {day_label} at {time_str}")
                print(f"  📅 [{day_label}] {name} ({course}) at {time_str}")

    return results


async def scrape_all() -> tuple[dict, dict, str, date, date]:
    """
    Main entry point: login once, scrape overdue + due for all students.
    Returns (overdue_results, due_results, due_label, today, tomorrow).
    """
    today    = date.today()
    tomorrow = next_school_day(today)
    targets  = [today, tomorrow] if today != tomorrow else [today]
    label    = "Today & Tomorrow"
    print(f"Today: {today}  |  Next school day: {tomorrow}")

    overdue_results: dict[str, list[str]] = {}
    due_results:     dict[str, list[str]] = {}

    from playwright.async_api import async_playwright as apw
    async with apw() as p:
        browser = await p.chromium.launch(headless=not DEBUG)
        page    = await browser.new_page()

        await _login(page)

        print("\nDiscovering children...")
        children = await discover_children(page)

        for student_name in STUDENT_NAMES:
            print(f"\n--- {student_name} ---")

            sid = next(
                (s for n, s in children.items()
                 if student_name.lower() in n.lower() or n.lower() in student_name.lower()),
                None,
            )

            if not sid:
                print(f"  ⚠️  '{student_name}' not found. Known: {list(children.keys())}")
                overdue_results[student_name] = [f"⚠️ Could not find '{student_name}'"]
                due_results[student_name]     = []
                continue

            print("  Checking overdue...")
            overdue_results[student_name] = await get_overdue(page, sid)

            print(f"  Checking due {label}...")
            due_results[student_name] = await get_due_on(page, sid, targets)

        await browser.close()

    return overdue_results, due_results, label, today, tomorrow
