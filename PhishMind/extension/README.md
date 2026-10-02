# PhishMind — Chrome Extension

Scores the email you have open in Gmail against the same PhishMind engine
that powers the dashboard, and shows a small colored badge in the top-right
corner of the page. Click it for the full explanation. On a **SUSPICIOUS**
or **PHISHING** result it also opens a short prompt asking whether *you*
think the email is spam or legitimate, and logs your answer.

## Prerequisites

The extension is a thin client — it needs the PhishMind **backend** running
locally first (see `../backend/README.md` or the root `README.md`).

```
cd ../backend
uvicorn main:app --reload --port 8000
```

## Load it into Chrome

1. Open `chrome://extensions`.
2. Turn on **Developer mode** (top-right toggle).
3. Click **Load unpacked**.
4. Select this `extension/` folder.
5. Open Gmail (`https://mail.google.com`) in a tab, open any email — a
   colored badge appears near the top-right of the page within a couple
   of seconds.

## Using it

- The badge color/number is the PhishMind risk score (green/amber/red,
  0–100). Click it to expand the full breakdown: explanation, detected
  social-engineering techniques, evidence, and recommended action.
- For SUSPICIOUS/PHISHING emails, the card auto-opens with two buttons:
  **🚩 Spam** / **✅ Valid** — pick whichever matches what you think, and
  it's recorded against that scan (visible via
  `GET /api/v1/scan/{id}` → `user_feedback`, or in the extension popup).
- The toolbar icon (click the shield in Chrome's extension bar) opens a
  small popup: backend connection status, your last scan, a **Rescan open
  email** button, a shortcut to open the full dashboard, and settings
  (backend URL, dashboard URL, whether to auto-scan, whether to prompt for
  feedback).

## Notes / limitations (be upfront about these in your demo)

- Gmail doesn't expose the raw `.eml` source (headers, SPF/DKIM/DMARC) to
  the page DOM — only what's rendered visually. The extension reconstructs
  a synthetic message from the subject, sender address, visible body text,
  and every link `href` in the message, and scans that. That's enough for
  the AI/semantic pass (intent, social engineering, AI-generated-text
  tells) and the URL heuristics to run at full strength; the technical
  (SPF/DKIM/DMARC) category will usually read low from the extension since
  those headers aren't visible in the UI. The dashboard's **paste raw
  `.eml`** flow and the IMAP live listener *do* see full headers and score
  that category properly — mention both paths in your demo.
- Gmail's DOM classes (`.hP`, `.gD`, `.a3s.aiL`) are unofficial but have
  been stable for years and are what most open-source Gmail tooling relies
  on; if Gmail changes its markup the badge just won't appear rather than
  breaking the page.
- All requests go to `http://localhost:8000` by default — change it in the
  popup's Settings section if your backend runs elsewhere.
