# NagMaster9000 🤖

> Logs into Schoology, hunts down your overdue and missing assignments, and WhatsApp-yells at you about them.

Runs automatically on a schedule via GitHub Actions — no server needed, completely free.

---

## Setup

### 1. WhatsApp (CallMeBot) — one-time

1. Add **+34 644 31 79 92** to your WhatsApp contacts (name it "CallMeBot" or anything)
2. Send it this message via WhatsApp: `I allow callmebot to send me messages`
3. You'll receive your API key back within seconds

### 2. GitHub Secrets

In your GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**, add:

| Secret | Value |
|--------|-------|
| `SCHOOLOGY_USER` | Your Schoology login email |
| `SCHOOLOGY_PASS` | Your Schoology password |
| `SCHOOLOGY_DOMAIN` | Your school's domain, e.g. `myschool.schoology.com` (or leave blank for `app.schoology.com`) |
| `WHATSAPP_NUM` | Your number in international format, no `+` — e.g. `15551234567` |
| `CALLMEBOT_KEY` | The API key you got from CallMeBot |

### 3. Push & run

```bash
git push origin main
```

Then go to **Actions → NagMaster9000 → Run workflow** to test it manually before waiting for the schedule.

---

## Schedule

Runs on **weekdays at 7am, 1pm, and 7pm Eastern** by default.
Edit the cron line in [`.github/workflows/nag.yml`](.github/workflows/nag.yml) to change the timing.

---

## Local testing

```bash
cp .env.example .env
# fill in your values in .env

pip install playwright requests
playwright install chromium --with-deps

python checker.py
```

---

## How it works

1. Playwright launches a headless Chromium browser
2. Logs into your Schoology account
3. Scrapes the homepage and grades page for overdue/missing items
4. Sends you a WhatsApp message via CallMeBot with the results
