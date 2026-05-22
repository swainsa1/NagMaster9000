import asyncio
import os
import re
import smtplib
import requests
from datetime import date, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.parse import quote
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv()

SCHOOLOGY_USER    = os.environ["SCHOOLOGY_USER"]
SCHOOLOGY_PASS    = os.environ["SCHOOLOGY_PASS"]
SCHOOLOGY_DOMAIN  = os.environ.get("SCHOOLOGY_DOMAIN", "app.schoology.com")
STUDENT_NAMES     = [n.strip() for n in os.environ["STUDENT_NAMES"].split(",")]
WHATSAPP_NUM      = os.environ.get("WHATSAPP_NUM", "")
CALLMEBOT_KEY     = os.environ.get("CALLMEBOT_KEY", "")
GMAIL_USER        = os.environ.get("GMAIL_USER", "")
GMAIL_APP_PASSWORD= os.environ.get("GMAIL_APP_PASSWORD", "")
EMAIL_TO          = os.environ.get("EMAIL_TO", "")
MAX_DAYS_OVERDUE  = int(os.environ.get("MAX_DAYS_OVERDUE", "14"))
DEBUG             = os.environ.get("DEBUG", "0") == "1"

TASKLY_URL        = os.environ.get("TASKLY_URL", "").rstrip("/")
TASKLY_ADMIN_USER = os.environ.get("TASKLY_ADMIN_USER", "")
TASKLY_ADMIN_PASS = os.environ.get("TASKLY_ADMIN_PASS", "")

# Schoology course name → Taskly tag (falls back to "Others")
COURSE_TAG_MAP = {
    "math":          "Math",
    "science":       "Science",
    "english":       "English",
    "eng/lang":      "English",
    "reading":       "Reading",
    "band":          "Band",
    "art":           "Art",
    "global studies":"Global Studies",
    "mn studies":    "MN Studies",
    "technology":    "Technology",
}

def course_to_tag(course: str) -> str:
    cl = course.lower()
    for key, tag in COURSE_TAG_MAP.items():
        if key in cl:
            return tag
    return "Others"


def next_school_day(from_date: date) -> date:
    """Returns the next school day (Mon–Fri) after from_date. Skips weekends."""
    d = from_date + timedelta(days=1)
    while d.weekday() >= 5:   # 5=Sat, 6=Sun
        d += timedelta(days=1)
    return d


async def screenshot(page, label: str):
    if DEBUG:
        path = f"debug_{label}.png"
        await page.screenshot(path=path, full_page=False)
        print(f"  📸 {path}")


async def discover_children(page) -> dict[str, str]:
    """Returns {student_name: student_id} by reading the parent dropdown."""
    await page.goto(f"https://{SCHOOLOGY_DOMAIN}/parent/home")
    await page.wait_for_load_state("networkidle")

    await page.evaluate("""() => {
        const btn = [...document.querySelectorAll('button')]
            .find(b => b.querySelector('img') && b.textContent.trim().length > 0);
        if (btn) btn.click();
    }""")
    await page.wait_for_timeout(600)

    links = await page.query_selector_all("a[href*='/parent/switch_child/']")
    children = {}
    for link in links:
        text  = await link.inner_text()
        name  = text.strip().split("\n")[0].strip()
        href  = await link.get_attribute("href")
        m     = re.search(r"/parent/switch_child/(\d+)", href)
        if m:
            children[name] = m.group(1)
            print(f"  Found: {name} (id={m.group(1)})")

    return children


async def get_overdue(page, student_id: str) -> list[str]:
    """Returns overdue assignments within MAX_DAYS_OVERDUE days."""
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


async def get_due_on(page, student_id: str, targets: list) -> list[str]:
    """
    Returns assignments due on any of the `targets` dates for this student.
    Each result is prefixed with the day label (Today / Tomorrow / Monday etc).
    Scrapes the UPCOMING section of /parent/home in one page load.
    """
    await page.goto(f"https://{SCHOOLOGY_DOMAIN}/parent/switch_child/{student_id}")
    await page.wait_for_load_state("networkidle")
    await page.goto(f"https://{SCHOOLOGY_DOMAIN}/parent/home")
    await page.wait_for_load_state("networkidle")
    await screenshot(page, f"home_{student_id}")

    text  = await page.inner_text("main")
    lines = [l.strip() for l in text.splitlines()]

    today = date.today()
    results = []
    seen    = set()

    for target in targets:
        # Schoology formats dates like "Thursday, May 21, 2026"
        target_str = target.strftime("%A, %B %-d, %Y")
        if target == today:
            day_label = "Today"
        elif target == today + timedelta(days=1):
            day_label = "Tomorrow"
        else:
            day_label = target.strftime("%A")   # e.g. "Monday"
        print(f"  Looking for: '{target_str}' ({day_label})")

        for i, line in enumerate(lines):
            if not line.startswith("Due ") or target_str not in line:
                continue
            time_m   = re.search(r"at\s+(\d+:\d+\s*[ap]m)", line, re.IGNORECASE)
            time_str = time_m.group(1) if time_m else ""

            # Assignment name: nearest non-noise line above
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

            key = (name, target_str)
            if name and key not in seen:
                seen.add(key)
                results.append(f"{name} | {course} | {day_label} at {time_str}")
                print(f"  📅 [{day_label}] {name} ({course}) at {time_str}")

    return results


async def run():
    today   = date.today()
    tomorrow = next_school_day(today)
    targets  = [today, tomorrow] if today != tomorrow else [today]
    label    = "Today & Tomorrow"
    print(f"Today: {today}  |  Next school day: {tomorrow}")

    overdue_results: dict[str, list[str]] = {}
    due_results:     dict[str, list[str]] = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not DEBUG)
        page    = await browser.new_page()

        print("\nLogging in...")
        await page.goto(f"https://{SCHOOLOGY_DOMAIN}/login")
        await page.wait_for_load_state("networkidle")
        await page.fill("input[name='mail']", SCHOOLOGY_USER)
        await page.fill("input[name='pass']", SCHOOLOGY_PASS)
        await page.click("input[type='submit']")
        await page.wait_for_load_state("networkidle")
        print(f"Logged in → {await page.title()}")

        print("\nDiscovering children...")
        children = await discover_children(page)

        for student_name in STUDENT_NAMES:
            print(f"\n--- {student_name} ---")

            sid = next(
                (s for n, s in children.items()
                 if student_name.lower() in n.lower() or n.lower() in student_name.lower()),
                None
            )

            if not sid:
                print(f"  ⚠️  '{student_name}' not found. Known: {list(children.keys())}")
                overdue_results[student_name] = [f"⚠️ Could not find '{student_name}'"]
                due_results[student_name]     = []
                continue

            print(f"  Checking overdue...")
            overdue_results[student_name] = await get_overdue(page, sid)

            print(f"  Checking due today & tomorrow...")
            due_results[student_name] = await get_due_on(page, sid, targets)

        await browser.close()

    return overdue_results, due_results, label, today, tomorrow


def build_message(overdue: dict, due: dict, due_label: str) -> str:
    lines = ["🤖 *Beep Boop! Your Homework Overlord Has Spoken!*\n"]
    for name in overdue:
        first = name.split()[0].title()
        o_items = overdue[name]
        d_items = due[name]

        if o_items:
            lines.append(f"📛 *{first}* — {len(o_items)} overdue:")
            for item in o_items:
                lines.append(f"  • {item}")
        else:
            lines.append(f"✅ *{first}* — No overdue!")

        if d_items:
            lines.append(f"\n  📅 Due {due_label}:")
            for item in d_items:
                lines.append(f"  • {item}")
        else:
            lines.append(f"  📅 Due {due_label}: nothing due")

        lines.append("")
    return "\n".join(lines).strip()


def _assignment_rows(items: list[str], col3_label: str) -> str:
    rows = ""
    for item in items:
        parts  = item.split(" | ")
        name   = parts[0] if len(parts) > 0 else ""
        course = parts[1] if len(parts) > 1 else ""
        status = parts[2] if len(parts) > 2 else ""
        rows += (
            f"<tr>"
            f"<td style='padding:6px 12px;border-bottom:1px solid #eee'>{name}</td>"
            f"<td style='padding:6px 12px;border-bottom:1px solid #eee;color:#666'>{course}</td>"
            f"<td style='padding:6px 12px;border-bottom:1px solid #eee;color:#E84040;white-space:nowrap'>{status}</td>"
            f"</tr>"
        )
    return f"""
    <table style='border-collapse:collapse;width:100%;font-family:sans-serif;font-size:14px'>
      <tr style='background:#f5f5f5'>
        <th style='padding:8px 12px;text-align:left'>Assignment</th>
        <th style='padding:8px 12px;text-align:left'>Course</th>
        <th style='padding:8px 12px;text-align:left'>{col3_label}</th>
      </tr>
      {rows}
    </table>"""


def send_email(overdue: dict, due: dict, due_label: str):
    if not GMAIL_USER or not GMAIL_APP_PASSWORD or GMAIL_APP_PASSWORD == "your_16_char_app_password":
        print("Email: skipped (not configured)")
        return

    has_overdue = any(items for items in overdue.values())
    subject = "🚨 Beep Boop! Homework Overlord Has Findings!" if has_overdue else "✅ Beep Boop! Kids Are Off the Hook Today!"

    html_body = ""
    for name in overdue:
        first   = name.split()[0].title()
        o_items = overdue[name]
        d_items = due[name]

        html_body += f"<h3 style='margin-top:28px;color:#333'>👤 {first}</h3>"

        if o_items:
            html_body += f"<p style='color:#E84040;font-weight:bold'>📛 {len(o_items)} Overdue</p>"
            html_body += _assignment_rows(o_items, "Overdue")
        else:
            html_body += "<p style='color:green'>✅ No overdue assignments!</p>"

        if d_items:
            html_body += f"<p style='color:#2563EB;font-weight:bold;margin-top:16px'>📅 Due {due_label}</p>"
            html_body += _assignment_rows(d_items, "Due At")
        else:
            html_body += f"<p style='color:#999'>📅 Nothing due on {due_label}</p>"

    html = f"""
    <div style='font-family:sans-serif;max-width:660px;margin:0 auto;color:#222'>
      <h2 style='color:#333'>🤖 Beep Boop! Your Homework Overlord Has Spoken!</h2>
      {html_body}
      <p style='color:#aaa;font-size:11px;margin-top:32px'>
        Overdue = last {MAX_DAYS_OVERDUE} days only.
      </p>
    </div>"""

    recipients = [e.strip() for e in EMAIL_TO.split(",") if e.strip()]
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_USER
    msg["To"]      = ", ".join(recipients)
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        smtp.sendmail(GMAIL_USER, recipients, msg.as_string())
    print(f"Email: sent to {', '.join(recipients)}")


def taskly_login() -> requests.Session | None:
    """Login to Taskly as admin, return an authenticated session."""
    if not TASKLY_URL or not TASKLY_ADMIN_USER or not TASKLY_ADMIN_PASS:
        return None
    session = requests.Session()
    resp = session.post(
        f"{TASKLY_URL}/api/v1/auth/login",
        json={"username": TASKLY_ADMIN_USER, "password": TASKLY_ADMIN_PASS},
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"Taskly login failed: {resp.status_code} {resp.text[:200]}")
        return None
    print(f"Taskly: logged in as {resp.json().get('display_name')}")
    return session


def taskly_existing_tasks(session: requests.Session, owner_id: int) -> set[tuple]:
    """Return set of (description, due_date) for all existing tasks for this user."""
    resp = session.get(
        f"{TASKLY_URL}/api/v1/admin/tasks",
        params={"userId": owner_id, "filter": "all"},
        timeout=15,
    )
    if resp.status_code != 200:
        return set()
    return {(t["description"], t["due_date"]) for t in resp.json()}


def taskly_create_tasks(session: requests.Session, owner_id: int,
                        items: list[str], due_date: date):
    """Create Taskly tasks for `items`, skipping duplicates."""
    existing = taskly_existing_tasks(session, owner_id)
    due_str  = due_date.strftime("%Y-%m-%d")
    created  = 0

    for item in items:
        parts  = item.split(" | ")
        name   = parts[0][:120]   # Taskly description max 120 chars
        course = parts[1] if len(parts) > 1 else ""
        tag    = course_to_tag(course)

        if (name, due_str) in existing:
            print(f"  Taskly: skip (exists) — {name}")
            continue

        resp = session.post(
            f"{TASKLY_URL}/api/v1/admin/tasks",
            json={"owner_id": owner_id, "description": name,
                  "due_date": due_str, "tag": tag},
            timeout=15,
        )
        if resp.status_code == 201:
            print(f"  Taskly: created — {name} [{tag}] on {due_str}")
            created += 1
        else:
            print(f"  Taskly: error {resp.status_code} — {resp.text[:200]}")

    return created


def push_to_taskly(due: dict, today: date, tomorrow: date):
    """Push due-today and due-tomorrow assignments into Taskly for each student."""
    if not TASKLY_URL:
        print("Taskly: skipped (not configured)")
        return

    session = taskly_login()
    if not session:
        return

    # Map student names to Taskly user IDs
    resp = session.get(f"{TASKLY_URL}/api/v1/admin/users", timeout=15)
    if resp.status_code != 200:
        print(f"Taskly: could not fetch users ({resp.status_code})")
        return

    users = {u["display_name"].lower(): u["id"] for u in resp.json()}

    for student_name, items in due.items():
        # Match by display_name (case-insensitive)
        uid = next(
            (uid for dname, uid in users.items()
             if student_name.lower() in dname or dname in student_name.lower()),
            None,
        )
        if not uid:
            print(f"  Taskly: no account found for '{student_name}'")
            continue

        first = student_name.split()[0].title()
        print(f"\n  Taskly → {first} (id={uid})")

        # Split items by whether they're today or tomorrow
        today_items    = [i for i in items if "Today at"    in i]
        tomorrow_items = [i for i in items if "Tomorrow at" in i or
                          (tomorrow.strftime("%A") in i and "at" in i)]

        if today_items:
            taskly_create_tasks(session, uid, today_items, today)
        if tomorrow_items:
            taskly_create_tasks(session, uid, tomorrow_items, tomorrow)


def send_whatsapp(message: str):
    if not WHATSAPP_NUM or not CALLMEBOT_KEY or CALLMEBOT_KEY == "your_callmebot_api_key":
        print("WhatsApp: skipped (not configured)")
        return
    url = (
        "https://api.callmebot.com/whatsapp.php"
        f"?phone={WHATSAPP_NUM}&text={quote(message)}&apikey={CALLMEBOT_KEY}"
    )
    resp = requests.get(url, timeout=15)
    print(f"WhatsApp: {resp.status_code} {resp.text[:200]}")


async def main():
    overdue, due, due_label, today, tomorrow = await run()
    msg = build_message(overdue, due, due_label)
    print("\n--- Message ---")
    print(msg)
    if not DEBUG:
        send_whatsapp(msg)
        send_email(overdue, due, due_label)
        print("\nPushing to Taskly...")
        push_to_taskly(due, today, tomorrow)
    else:
        print("\n(Notifications skipped in DEBUG mode)")
        print("Pushing to Taskly (debug mode still runs)...")
        push_to_taskly(due, today, tomorrow)


asyncio.run(main())
