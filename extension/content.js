/**
 * PhishMind content script — runs on mail.google.com.
 *
 * Watches the open Gmail message, scrapes subject/sender/body/links from the
 * DOM, sends it to the PhishMind backend (via the background worker, so it
 * isn't subject to Gmail's own CSP), and renders a small floating badge in
 * the corner of the page with the verdict. For SUSPICIOUS/PHISHING results
 * it also opens a short prompt asking the reader whether they think the
 * email is spam or legitimate, and records the answer.
 *
 * Gmail's DOM has no public API and its class names are minified/unstable
 * long-term, but `.hP` (subject), `.gD` (sender, with `email`/`name`
 * attributes) and `.a3s.aiL` (rendered message body) have been stable
 * selectors for years and are what most open-source Gmail tooling relies on.
 * Every lookup below fails soft — if Gmail changes its markup, the widget
 * simply doesn't appear rather than breaking the page.
 */

const VERDICT_META = {
  SAFE: { color: "#10B981", label: "Safe", icon: "✓" },
  SUSPICIOUS: { color: "#F59E0B", label: "Suspicious", icon: "!" },
  PHISHING: { color: "#EF4444", label: "Phishing", icon: "✕" },
};

let shadowRoot = null;
let hostEl = null;
let lastScannedKey = null;
let scanInFlight = false;

function sendMessage(message) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage(message, (response) => {
      if (chrome.runtime.lastError) {
        resolve({ ok: false, error: chrome.runtime.lastError.message });
        return;
      }
      resolve(response);
    });
  });
}

// --- Gmail DOM extraction -------------------------------------------------

function getOpenEmail() {
  const subjectEl = document.querySelector("h2.hP");
  const bodyEls = document.querySelectorAll(".a3s.aiL");
  const senderEls = document.querySelectorAll(".gD");

  if (!subjectEl || bodyEls.length === 0 || senderEls.length === 0) return null;

  const bodyEl = bodyEls[bodyEls.length - 1];
  const senderEl = senderEls[senderEls.length - 1];

  const subject = (subjectEl.innerText || "").replace(/\s+/g, " ").trim();
  const senderEmail = (senderEl.getAttribute("email") || "").trim();
  const senderName = (senderEl.getAttribute("name") || senderEl.innerText || "")
    .replace(/[\r\n"]+/g, " ")
    .trim();
  const bodyText = (bodyEl.innerText || "").trim();

  if (!bodyText) return null;

  const links = Array.from(bodyEl.querySelectorAll("a[href]"))
    .map((a) => a.href)
    .filter((href) => /^https?:\/\//i.test(href));

  return { subject, senderEmail, senderName, bodyText, links: Array.from(new Set(links)) };
}

function buildSyntheticEml({ subject, senderEmail, senderName, bodyText, links }) {
  const from = senderEmail ? `${senderName || senderEmail} <${senderEmail}>` : "unknown@unknown.invalid";
  const linksBlock = links.length ? `\n\nLinks in this email:\n${links.join("\n")}` : "";
  return [
    `From: ${from}`,
    `Subject: ${subject || "(no subject)"}`,
    `Content-Type: text/plain; charset="UTF-8"`,
    "",
    `${bodyText}${linksBlock}`,
  ].join("\n");
}

function emailKey(email) {
  return `${email.subject}|${email.senderEmail}|${email.bodyText.length}`;
}

// --- Widget UI (shadow DOM, isolated from Gmail's styles) ----------------

function ensureWidget() {
  if (hostEl) return shadowRoot;
  hostEl = document.createElement("div");
  hostEl.id = "phishmind-host";
  document.documentElement.appendChild(hostEl);
  shadowRoot = hostEl.attachShadow({ mode: "open" });

  const style = document.createElement("style");
  style.textContent = `
    :host { all: initial; }
    .pm-badge {
      position: fixed; top: 90px; right: 18px; z-index: 2147483647;
      width: 46px; height: 46px; border-radius: 50%;
      display: flex; align-items: center; justify-content: center;
      font: 700 15px/1 "Segoe UI", Arial, sans-serif; color: #fff;
      box-shadow: 0 4px 14px rgba(0,0,0,0.35);
      cursor: pointer; border: 2px solid rgba(255,255,255,0.85);
      transition: transform 0.15s ease;
      user-select: none;
    }
    .pm-badge:hover { transform: scale(1.08); }
    .pm-badge.pm-loading {
      background: #334155; animation: pm-pulse 1.2s ease-in-out infinite;
    }
    @keyframes pm-pulse { 0%,100% { opacity: 0.55; } 50% { opacity: 1; } }
    .pm-card {
      position: fixed; top: 90px; right: 18px; z-index: 2147483647;
      width: 320px; max-height: 70vh; overflow-y: auto;
      background: #1E293B; color: #F8FAFC; border-radius: 12px;
      box-shadow: 0 12px 32px rgba(0,0,0,0.45);
      border: 1px solid #334155;
      font: 400 13px/1.45 "Segoe UI", Arial, sans-serif;
      padding: 14px;
    }
    .pm-card h3 { margin: 0 0 8px; font-size: 14px; display:flex; align-items:center; gap:8px; }
    .pm-score { font-size: 26px; font-weight: 800; }
    .pm-pill {
      display: inline-block; padding: 2px 10px; border-radius: 999px;
      font-size: 11px; font-weight: 700; letter-spacing: 0.04em;
    }
    .pm-row { display:flex; justify-content: space-between; align-items:center; margin-bottom: 10px; }
    .pm-section { margin-top: 10px; padding-top: 10px; border-top: 1px solid #334155; }
    .pm-section h4 { margin: 0 0 6px; font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: #94A3B8; }
    .pm-section ul { margin: 0; padding-left: 16px; }
    .pm-section li { margin-bottom: 4px; }
    .pm-close { cursor: pointer; color: #94A3B8; font-size: 16px; line-height:1; background:none; border:none; padding:2px; }
    .pm-close:hover { color: #F8FAFC; }
    .pm-feedback { margin-top: 12px; padding-top: 12px; border-top: 1px solid #334155; }
    .pm-feedback p { margin: 0 0 8px; color: #F8FAFC; }
    .pm-feedback-btns { display: flex; gap: 8px; }
    .pm-btn {
      flex: 1; padding: 8px 6px; border-radius: 8px; border: 1px solid #334155;
      background: #0F172A; color: #F8FAFC; font-size: 12px; cursor: pointer; font-weight: 600;
    }
    .pm-btn:hover { border-color: #6366F1; }
    .pm-btn.pm-spam:hover { border-color: #EF4444; }
    .pm-btn.pm-valid:hover { border-color: #10B981; }
    .pm-thanks { color: #10B981; font-weight: 600; margin-top: 8px; }
    .pm-error { color: #F59E0B; }
  `;
  shadowRoot.appendChild(style);
  return shadowRoot;
}

function clearWidgetBody() {
  const root = ensureWidget();
  Array.from(root.querySelectorAll(".pm-badge, .pm-card")).forEach((el) => el.remove());
  return root;
}

function showLoadingBadge() {
  const root = clearWidgetBody();
  const badge = document.createElement("div");
  badge.className = "pm-badge pm-loading";
  badge.textContent = "…";
  root.appendChild(badge);
}

function showError(message) {
  const root = clearWidgetBody();
  const badge = document.createElement("div");
  badge.className = "pm-badge";
  badge.style.background = "#334155";
  badge.textContent = "!";
  badge.title = message;
  badge.addEventListener("click", () => {
    const card = document.createElement("div");
    card.className = "pm-card";
    card.innerHTML = `<div class="pm-row"><h3>PhishMind</h3><button class="pm-close">×</button></div><p class="pm-error">${escapeHtml(
      message
    )}</p><p style="color:#94A3B8">Check that the PhishMind backend is running (see the extension popup for the backend URL).</p>`;
    card.querySelector(".pm-close").addEventListener("click", () => {
      card.remove();
      badge.style.display = "flex";
    });
    badge.style.display = "none";
    ensureWidget().appendChild(card);
  });
  root.appendChild(badge);
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

function renderResult(result, { autoOpenFeedback }) {
  const root = clearWidgetBody();
  const meta = VERDICT_META[result.verdict] || VERDICT_META.SAFE;

  const badge = document.createElement("div");
  badge.className = "pm-badge";
  badge.style.background = meta.color;
  badge.textContent = result.risk_score;
  badge.title = `PhishMind: ${meta.label} (${result.risk_score}/100) — click for details`;
  root.appendChild(badge);

  function openCard(showFeedback) {
    root.querySelectorAll(".pm-card").forEach((el) => el.remove());
    const card = document.createElement("div");
    card.className = "pm-card";

    const evidenceHtml = (result.suspicious_evidence || [])
      .slice(0, 5)
      .map((e) => `<li>${escapeHtml(e)}</li>`)
      .join("");
    const adviceHtml = (result.actionable_advice || [])
      .slice(0, 4)
      .map((e) => `<li>${escapeHtml(e)}</li>`)
      .join("");
    const seHtml = (result.social_engineering || [])
      .slice(0, 4)
      .map((t) => `<li>[${escapeHtml(t.severity || "")}] ${escapeHtml(t.technique || "")}</li>`)
      .join("");

    card.innerHTML = `
      <div class="pm-row">
        <h3>🛡️ PhishMind</h3>
        <button class="pm-close">×</button>
      </div>
      <div class="pm-row">
        <span class="pm-score" style="color:${meta.color}">${result.risk_score}<span style="font-size:13px;color:#94A3B8">/100</span></span>
        <span class="pm-pill" style="background:${meta.color}22; color:${meta.color}; border:1px solid ${meta.color}66;">${meta.label.toUpperCase()}</span>
      </div>
      ${result.explanation ? `<div class="pm-section"><h4>Why</h4><p>${escapeHtml(result.explanation)}</p></div>` : ""}
      ${seHtml ? `<div class="pm-section"><h4>Social engineering</h4><ul>${seHtml}</ul></div>` : ""}
      ${evidenceHtml ? `<div class="pm-section"><h4>Evidence</h4><ul>${evidenceHtml}</ul></div>` : ""}
      ${adviceHtml ? `<div class="pm-section"><h4>Recommended action</h4><ul>${adviceHtml}</ul></div>` : ""}
      <div class="pm-feedback" data-feedback-area>
        <p>Do you think this email is spam, or is it valid?</p>
        <div class="pm-feedback-btns">
          <button class="pm-btn pm-spam" data-choice="spam">🚩 Spam</button>
          <button class="pm-btn pm-valid" data-choice="valid">✅ Valid</button>
        </div>
      </div>
    `;

    card.querySelector(".pm-close").addEventListener("click", () => {
      card.remove();
      badge.style.display = "flex";
    });

    card.querySelectorAll("[data-choice]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const choice = btn.getAttribute("data-choice");
        const area = card.querySelector("[data-feedback-area]");
        if (result.id) {
          await sendMessage({ type: "PHISHMIND_FEEDBACK", scanId: result.id, feedback: choice });
        }
        area.innerHTML = `<p class="pm-thanks">Thanks — logged as "${choice}".</p>`;
      });
    });

    badge.style.display = "none";
    root.appendChild(card);
  }

  badge.addEventListener("click", () => openCard(false));

  // Only pop the full card open automatically for a confirmed PHISHING
  // verdict — that's the one worth interrupting the reader for. SUSPICIOUS
  // just shows the small badge; the reader can click it if they're curious.
  if (autoOpenFeedback && result.verdict === "PHISHING") {
    openCard(true);
  }
}

// --- Scan orchestration ----------------------------------------------------

async function scanIfNewEmailOpen() {
  const settings = await sendMessage({ type: "PHISHMIND_GET_SETTINGS" });
  if (!settings.ok || !settings.data.autoScan) return;

  const email = getOpenEmail();
  if (!email) {
    // No email open right now (inbox list, search results, a thread that
    // hasn't rendered its body yet, etc). Without this, the last verdict's
    // badge/card just stayed on screen forever — including bleeding onto
    // whatever the reader looked at next, phishing or not.
    if (lastScannedKey !== null) {
      lastScannedKey = null;
      clearWidgetBody();
    }
    return;
  }

  const key = emailKey(email);
  if (key === lastScannedKey || scanInFlight) return;
  lastScannedKey = key;
  scanInFlight = true;

  showLoadingBadge();
  const rawEmailText = buildSyntheticEml(email);
  const response = await sendMessage({ type: "PHISHMIND_SCAN", rawEmailText });
  scanInFlight = false;

  if (!response || !response.ok) {
    showError(response?.error || "Could not reach the PhishMind backend.");
    return;
  }
  renderResult(response.data, { autoOpenFeedback: true });
}

// Gmail is a single-page app — no full navigations to hook into, so poll +
// observe mutations instead. Cheap: bails out instantly if nothing changed.
const observer = new MutationObserver(() => {
  scanIfNewEmailOpen();
});
observer.observe(document.body, { childList: true, subtree: true });

window.addEventListener("hashchange", scanIfNewEmailOpen);
setInterval(scanIfNewEmailOpen, 4000);
scanIfNewEmailOpen();

// Let the popup ask us to rescan the currently open email on demand.
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "PHISHMIND_FORCE_RESCAN") {
    lastScannedKey = null;
    scanIfNewEmailOpen().then(() => sendResponse({ ok: true }));
    return true;
  }
  return false;
});
