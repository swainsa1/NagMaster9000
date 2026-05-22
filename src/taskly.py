"""Taskly integration: login, fetch existing tasks, create new ones."""

import requests
from datetime import date

from src.config import TASKLY_URL, TASKLY_ADMIN_USER, TASKLY_ADMIN_PASS
from src.utils import course_to_tag


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
                        items: list[str], due_date: date) -> int:
    """Create Taskly tasks for items, skipping duplicates."""
    existing = taskly_existing_tasks(session, owner_id)
    due_str  = due_date.strftime("%Y-%m-%d")
    created  = 0

    for item in items:
        parts  = item.split(" | ")
        name   = parts[0][:120]
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

    resp = session.get(f"{TASKLY_URL}/api/v1/admin/users", timeout=15)
    if resp.status_code != 200:
        print(f"Taskly: could not fetch users ({resp.status_code})")
        return

    users = {u["display_name"].lower(): u["id"] for u in resp.json()}

    for student_name, items in due.items():
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

        today_items    = [i for i in items if "Today at" in i]
        tomorrow_items = [i for i in items if "Tomorrow at" in i or
                          (tomorrow.strftime("%A") in i and "at" in i)]

        if today_items:
            taskly_create_tasks(session, uid, today_items, today)
        if tomorrow_items:
            taskly_create_tasks(session, uid, tomorrow_items, tomorrow)
