# Setup Guide — PNARD Opportunity Bot

This walks you from zero to a working bot that pings your Telegram every hour with new Pakistan agriculture and development opportunities from ReliefWeb, ADB, and the World Bank.

Time to set up: about 30 minutes. No coding required — you'll be copying values between a few websites.

---

## What you need before you start

- A phone with Telegram installed
- A computer with a web browser
- An email address (for GitHub, if you don't already have an account)

That's it. No payment method, no server, no hosting account. Everything here is genuinely free.

---

## Step 1: Create the Telegram bot (5 minutes)

1. Open Telegram on your phone or computer.
2. In the search bar, type `@BotFather` and open the chat with the verified BotFather account (blue checkmark).
3. Tap **Start**.
4. Send the message: `/newbot`
5. BotFather asks for a name. Type something human-readable like: `PNARD Opportunities`
6. BotFather asks for a username. It must end in `bot`. Try: `pnard_opps_bot` (if taken, add a number: `pnard_opps_2_bot`).
7. BotFather replies with a message containing a long token that looks like this:
   ```
   8472619384:AAFxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
   **Copy this token somewhere safe.** Don't share it publicly — anyone with this token controls your bot.

8. Now open a chat with your new bot (tap the link BotFather gave you, then tap Start). Send it any message — "hi" works.

---

## Step 2: Get your Telegram chat ID (2 minutes)

The bot needs to know *which* chat to send alerts to. That's your personal chat ID.

1. In Telegram, search for `@userinfobot` and open it.
2. Tap **Start**.
3. It immediately replies with your chat ID — a number like `847261938`.
4. **Copy this number.**

---

## Step 3: Create a GitHub account (3 minutes — skip if you have one)

1. Go to https://github.com
2. Click **Sign up**. Use any email, pick a username, choose the free plan.
3. Verify your email.

---

## Step 4: Create the repository (5 minutes)

1. Once signed in to GitHub, click the **+** in the top right and choose **New repository**.
2. Name it: `pnard-bot`
3. Leave it set to **Public** — this is what makes GitHub Actions free without limits.
4. Check the box **Add a README file**. (It'll get overwritten in a moment — that's fine.)
5. Click **Create repository**.

---

## Step 5: Upload the bot files (10 minutes)

You should have received a zip file with all the bot code. Unzip it somewhere you can find it.

The unzipped folder contains:
```
bot.py
requirements.txt
seen.json
README.md
SETUP.md              (this file)
.gitignore
scrapers/
  __init__.py
  reliefweb.py
  adb.py
  worldbank.py
.github/
  workflows/
    bot.yml
```

**Upload them to GitHub:**

1. On your new repo page on GitHub, click **Add file** → **Upload files**.
2. In your file browser, select ALL the files and folders from the unzipped folder. Drag them into the GitHub upload area. (On some browsers you need to click "choose your files" and select everything — including inside the `scrapers/` and `.github/` folders.)
3. If the drag-and-drop misses the `.github/` folder (hidden folders are tricky), do this instead:
   - First upload `bot.py`, `requirements.txt`, `seen.json`, `README.md`, `SETUP.md`, `.gitignore` directly.
   - Then click **Add file** → **Create new file**. In the filename box, type: `scrapers/__init__.py` — GitHub will automatically create the folder. Leave the file empty and commit.
   - Repeat for `scrapers/reliefweb.py`, `scrapers/adb.py`, `scrapers/worldbank.py` — paste the contents from your downloaded files.
   - Then `.github/workflows/bot.yml` the same way.
4. At the bottom of the upload page, scroll down and click **Commit changes**.

**Check it worked:** your repo's file list should show `bot.py`, a `scrapers` folder (with 4 files inside), and a `.github` folder (with `workflows/bot.yml` inside).

---

## Step 6: Add your secrets (3 minutes)

Now we give GitHub Actions the Telegram token and chat ID, without putting them in the code where everyone could see them.

1. In your repo on GitHub, click **Settings** (top right of the repo page — not your personal settings).
2. In the left sidebar, click **Secrets and variables** → **Actions**.
3. Click **New repository secret**.
4. Name: `TELEGRAM_TOKEN` (exactly this, uppercase, with underscore)
5. Value: paste the long token from BotFather
6. Click **Add secret**.
7. Click **New repository secret** again.
8. Name: `TELEGRAM_CHAT_ID`
9. Value: paste your chat ID number from userinfobot
10. Click **Add secret**.

You should see two secrets listed: `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID`. The values are hidden — that's correct.

---

## Step 7: Run it once manually (2 minutes)

1. In your repo, click the **Actions** tab at the top.
2. If GitHub asks "Workflows aren't being run on this forked repository", click the green button to enable them.
3. In the left sidebar you'll see **PNARD opportunity bot**. Click it.
4. On the right, click **Run workflow** → **Run workflow** (the green button).
5. Wait about 30 seconds, then refresh. A yellow spinning icon means it's running. A green checkmark means it finished.
6. Click the run to see the logs. You're looking for lines like:
   ```
   [seen] loaded 0 known listing IDs
   [ReliefWeb] 25 listings
   [ADB] 4 listings
   [World Bank] 43 listings
   [match] 62 new listings above score 6
   [telegram] sent 62/62
   ```
7. **Check your Telegram.** You should have 60-ish messages from your bot — one per high-scoring listing.

The first run floods you because everything is new. Future runs will only send genuinely new listings — usually 0 to 5 per hour.

---

## Step 8: Done

From this point the bot runs itself. GitHub Actions triggers it every hour at :15 past. When it finds new matches, they appear in your Telegram. When it doesn't, it stays quiet.

---

## Troubleshooting

**No Telegram messages arrived after Step 7.**
- Open the run logs in the Actions tab. Look for a line starting with `[telegram]`. If it says `no credentials set`, your secrets aren't configured — go back to Step 6 and confirm the names are exactly `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID`.
- If it says `[telegram] 401` or `403`, the token is wrong. Re-copy from BotFather.
- If it says `[telegram] 400: chat not found`, the chat ID is wrong, or you haven't sent your bot a "hi" message yet (Step 1.8). Bots can't message you first until you've started the chat.

**The workflow shows a red X.**
- Click into the run and find the red step. The error message is usually clear. Most common: a typo in a filename during upload. Re-upload that file.

**It ran successfully but no messages in Telegram.**
- Check the log for `[match] 0 new listings`. That just means nothing new scored above the threshold — normal for quiet hours. Wait and check again in a few hours.

**Getting too many or too few alerts.**
- Edit `bot.py` directly on GitHub (click the file, then the pencil icon). Change `MIN_SCORE = 6` to a higher number (fewer, higher-quality alerts) or lower number (more alerts, more noise). Commit the change — the next scheduled run uses the new value.

**I want to add another keyword.**
- Edit `bot.py`, find the `KEYWORDS` dictionary near the top, add a line like `"your term": 3,` (the number is the weight — 1 to 5 is the normal range). Commit.

**I want to pause the bot.**
- Actions tab → PNARD opportunity bot → three-dot menu on the right → **Disable workflow**. Re-enable the same way.

**The bot sent me a listing that's irrelevant.**
- Normal. The keyword scoring is approximate. If a particular source keeps producing irrelevant noise, you can raise its threshold or remove a keyword that's triggering too loosely.

---

## What's next

Once the bot is running steadily, the real work is on the other end — reading alerts as they come in, shortlisting, and acting on the best ones. Useful habits:

- Star or forward genuinely interesting listings to a separate "bid candidates" chat so they don't get lost in the stream.
- Once a week, open the top few and decide: bid, watch, or ignore.
- If you go a week with zero bid-worthy alerts, the keyword set probably needs widening. If you're drowning, narrow it.

The bot's job is to remove the portal-sweeping step. Your job is still to read carefully and bid well.
