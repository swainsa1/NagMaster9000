"""NagMaster9000 — entry point."""

import asyncio
from src.config import DEBUG
from src.schoology import scrape_all
from src.notify import build_message, send_email, send_slack
from src.taskly import push_to_taskly


async def main():
    overdue, due, due_label, today, tomorrow = await scrape_all()

    msg = build_message(overdue, due, due_label)
    print("\n--- Message ---")
    print(msg)

    if not DEBUG:
        send_slack(msg)
        send_email(overdue, due, due_label)

    print("\nPushing to Taskly...")
    push_to_taskly(due, today, tomorrow)

    if DEBUG:
        print("\n(Email + WhatsApp skipped in DEBUG mode)")


asyncio.run(main())
