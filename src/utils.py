from datetime import date, timedelta
from src.config import COURSE_TAG_MAP, DEBUG


def next_school_day(from_date: date) -> date:
    """Returns the next school day (Mon–Fri) after from_date. Skips weekends."""
    d = from_date + timedelta(days=1)
    while d.weekday() >= 5:  # 5=Sat, 6=Sun
        d += timedelta(days=1)
    return d


def course_to_tag(course: str) -> str:
    """Map a Schoology course name to a Taskly tag. Defaults to 'Others'."""
    cl = course.lower()
    for key, tag in COURSE_TAG_MAP.items():
        if key in cl:
            return tag
    return "Others"


async def screenshot(page, label: str):
    if DEBUG:
        path = f"debug_{label}.png"
        await page.screenshot(path=path, full_page=False)
        print(f"  📸 {path}")
