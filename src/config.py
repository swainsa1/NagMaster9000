import os
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

# Schoology course name → Taskly tag
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
