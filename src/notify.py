"""Notifications: WhatsApp via CallMeBot and HTML email via Gmail."""

import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from src.config import (
    SLACK_WEBHOOK_URL,
    GMAIL_USER, GMAIL_APP_PASSWORD, EMAIL_TO,
    MAX_DAYS_OVERDUE,
)


def build_message(overdue: dict, due: dict, due_label: str) -> str:
    lines = ["🤖 *Beep Boop! Your Homework Overlord Has Spoken!*\n"]
    for name in overdue:
        first   = name.split()[0].title()
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
    subject = (
        "🚨 Beep Boop! Homework Overlord Has Findings!"
        if has_overdue else
        "✅ Beep Boop! Kids Are Off the Hook Today!"
    )

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


def send_slack(message: str):
    if not SLACK_WEBHOOK_URL:
        print("Slack: skipped (not configured)")
        return
    resp = requests.post(SLACK_WEBHOOK_URL, json={"text": message}, timeout=15)
    print(f"Slack: {resp.status_code} {resp.text[:200]}")
