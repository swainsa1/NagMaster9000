import asyncio
import os
import re
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.parse import quote
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv()

SCHOOLOGY_USER   = os.environ["SCHOOLOGY_USER"]
SCHOOLOGY_PASS   = os.environ["SCHOOLOGY_PASS"]
SCHOOLOGY_DOMAIN = os.environ.get("SCHOOLOGY_DOMAIN", "app.schoology.com")
STUDENT_NAMES    = [n.strip() for n in os.environ["STUDENT_NAMES"].split(",")]
WHATSAPP_NUM      = os.environ.get("WHATSAPP_NUM", "")
CALLMEBOT_KEY     = os.environ.get("CALLMEBOT_KEY", "")
GMAIL_USER        = os.environ.get("GMAIL_USER", "")
GMAIL_APP_PASSWORD= os.environ.get("GMAIL_APP_PASSWORD", "")
EMAIL_TO          = os.environ.get("EMAIL_TO", "")
MAX_DAYS_OVERDUE  = int(os.environ.get("MAX_DAYS_OVERDUE", "30"))
DEBUG             = os.environ.get("DEBUG", "0") == "1"


async def screenshot(page, label: str):
    if DEBUG:
        path = f"debug_{label}.png"
        await page.screenshot(path=path, full_page=False)
        print(f"  📸 {path}")


async def discover_children(page) -> dict[str, str]:
    """
    Returns {student_name: student_id} by reading the parent dropdown.
    Switch URLs look like /parent/switch_child/{id} — we extract the id.
    """
    await page.goto(f"https://{SCHOOLOGY_DOMAIN}/parent/home")
    await page.wait_for_load_state("networkidle")

    # Open the top-right user dropdown
    await page.evaluate("""() => {
        const btn = [...document.querySelectorAll('button')]
            .find(b => b.querySelector('img') && b.textContent.trim().length > 0);
        if (btn) btn.click();
    }""")
    await page.wait_for_timeout(600)

    links = await page.query_selector_all("a[href*='/parent/switch_child/']")
    children = {}
    for link in links:
        text   = await link.inner_text()
        name   = text.strip().split("\n")[0].strip()
        href   = await link.get_attribute("href")
        match  = re.search(r"/parent/switch_child/(\d+)", href)
        if match:
            student_id = match.group(1)
            children[name] = student_id
            print(f"  Found: {name} (id={student_id})")

    return children


async def get_overdue(page, student_id: str) -> list[str]:
    """
    Fetches /home/overdue-popup/{student_id}/parent and returns assignments
    that are overdue within MAX_DAYS_OVERDUE days.
    """
    url = f"https://{SCHOOLOGY_DOMAIN}/home/overdue-popup/{student_id}/parent"
    await page.goto(url)
    await page.wait_for_load_state("networkidle")
    await screenshot(page, f"overdue_{student_id}")

    text = await page.inner_text("main")

    # Each item looks like: "{name} {N} days? overdue{course}"
    pattern = re.compile(r"(.+?)\s+(\d+)\s+days?\s+overdue\s*(.+?)(?=\n|$)", re.MULTILINE)
    results = []
    for m in pattern.finditer(text):
        name   = m.group(1).strip()
        days   = int(m.group(2))
        course = m.group(3).strip()

        # Skip noise lines like "Assignment." or "Discussion."
        if name.lower() in ("assignment.", "discussion.", "assignment", "discussion"):
            continue
        if days > MAX_DAYS_OVERDUE:
            continue

        results.append(f"{name} | {course} | {days} day{'s' if days != 1 else ''} overdue")
        print(f"  ✅ {days}d — {name} ({course})")

    return results


async def run():
    results: dict[str, list[str]] = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not DEBUG)
        page    = await browser.new_page()

        print("Logging in...")
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

            match = next(
                (sid for name, sid in children.items()
                 if student_name.lower() in name.lower() or name.lower() in student_name.lower()),
                None
            )

            if not match:
                print(f"  ⚠️  '{student_name}' not found. Known: {list(children.keys())}")
                results[student_name] = [f"⚠️ Could not find '{student_name}' in Schoology"]
                continue

            overdue = await get_overdue(page, match)
            results[student_name] = overdue
            print(f"  → {len(overdue)} item(s) within {MAX_DAYS_OVERDUE} days")

        await browser.close()

    return results


def build_message(results: dict[str, list[str]]) -> str:
    lines = ["🤖 *NagMaster9000 Report*\n"]
    for name, items in results.items():
        first = name.split()[0].title()
        if items:
            lines.append(f"📛 *{first}* — {len(items)} overdue:")
            for item in items:
                lines.append(f"  • {item}")
        else:
            lines.append(f"✅ *{first}* — All clear!")
        lines.append("")
    return "\n".join(lines).strip()


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


def send_email(results: dict[str, list[str]]):
    if not GMAIL_USER or not GMAIL_APP_PASSWORD or GMAIL_APP_PASSWORD == "your_16_char_app_password":
        print("Email: skipped (not configured)")
        return

    has_overdue = any(items for items in results.values())
    subject = "🚨 Gentle Reminder— Overdue Assignments" if has_overdue else "✅  All Clear"

    # Build HTML body
    html_rows = ""
    for name, items in results.items():
        first = name.split()[0].title()
        if items:
            rows = "".join(
                f"<tr><td style='padding:6px 12px;border-bottom:1px solid #eee'>{item.split(' | ')[0]}</td>"
                f"<td style='padding:6px 12px;border-bottom:1px solid #eee;color:#666'>{item.split(' | ')[1] if ' | ' in item else ''}</td>"
                f"<td style='padding:6px 12px;border-bottom:1px solid #eee;color:#E84040;white-space:nowrap'>{item.split(' | ')[2] if item.count(' | ') >= 2 else ''}</td></tr>"
                for item in items
            )
            html_rows += f"""
            <h3 style='color:#E84040;margin-top:24px'>📛 {first} — {len(items)} overdue</h3>
            <table style='border-collapse:collapse;width:100%;font-family:sans-serif;font-size:14px'>
              <tr style='background:#f5f5f5'>
                <th style='padding:8px 12px;text-align:left'>Assignment</th>
                <th style='padding:8px 12px;text-align:left'>Course</th>
                <th style='padding:8px 12px;text-align:left'>Overdue</th>
              </tr>
              {rows}
            </table>"""
        else:
            html_rows += f"<p>✅ <strong>{first}</strong> — All clear!</p>"

    html = f"""
    <div style='font-family:sans-serif;max-width:640px;margin:0 auto'>
      <h2 style='color:#333'>🤖 NagMaster9000 - Assignment Helper Report </h2>
      {html_rows}
      <p style='color:#999;font-size:12px;margin-top:32px'>
        Only showing assignments overdue within the last {MAX_DAYS_OVERDUE} days.
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
    print(f"Email: sent to {EMAIL_TO}")


async def main():
    results = await run()
    msg = build_message(results)
    print("\n--- Message ---")
    print(msg)
    if not DEBUG:
        send_whatsapp(msg)
        send_email(results)
    else:
        print("\n(Notifications skipped in DEBUG mode)")


asyncio.run(main())
