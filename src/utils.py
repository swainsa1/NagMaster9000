import re
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


_LETTER_SCALE = [
    (97, "A+"), (93, "A"), (90, "A-"),
    (87, "B+"), (83, "B"), (80, "B-"),
    (77, "C+"), (73, "C"), (70, "C-"),
    (67, "D+"), (63, "D"), (60, "D-"),
]


def letter_for(pct: float) -> str:
    """Standard +/- letter grade for a percentage."""
    for floor, letter in _LETTER_SCALE:
        if pct >= floor:
            return letter
    return "F"


def percent_of(grade: str) -> float | None:
    """Pull the number out of a Schoology grade like 'A (99.98%)'."""
    m = re.search(r"([\d.]+)\s*%", grade)
    return float(m.group(1)) if m else None


async def screenshot(page, label: str):
    if DEBUG:
        path = f"debug_{label}.png"
        await page.screenshot(path=path, full_page=False)
        print(f"  📸 {path}")
