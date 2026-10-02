/**
 * PhishMind background service worker.
 *
 * Everything that needs to leave the browser (talking to the PhishMind API)
 * happens here rather than in content.js, so it's unaffected by whatever
 * Content-Security-Policy the mail page itself sets, and so the backend URL
 * setting lives in one place.
 */

const DEFAULT_SETTINGS = {
  backendUrl: "http://localhost:8000",
  dashboardUrl: "http://localhost:5173",
  autoScan: true,
  showFeedbackPrompt: true,
};

async function getSettings() {
  const stored = await chrome.storage.sync.get(DEFAULT_SETTINGS);
  return { ...DEFAULT_SETTINGS, ...stored };
}

async function apiFetch(path, options = {}) {
  const { backendUrl } = await getSettings();
  const url = `${backendUrl.replace(/\/+$/, "")}${path}`;
  const res = await fetch(url, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  let body = null;
  try {
    body = await res.json();
  } catch {
    // no JSON body
  }
  if (!res.ok) {
    const message = body?.detail || body?.message || `Request failed (${res.status})`;
    throw new Error(typeof message === "string" ? message : JSON.stringify(message));
  }
  return body?.data ?? body;
}

async function scanEmail(rawEmailText) {
  const result = await apiFetch("/api/v1/scan", {
    method: "POST",
    body: JSON.stringify({ raw_email_text: rawEmailText }),
  });

  await chrome.storage.local.set({ lastScan: result, lastScanAt: Date.now() });

  // Only interrupt the reader with a system notification for a confirmed
  // PHISHING verdict. SUSPICIOUS still gets the quiet on-page badge (see
  // content.js), it just doesn't fire a popup notification anymore.
  if (result.verdict === "PHISHING") {
    const { showFeedbackPrompt } = await getSettings();
    if (showFeedbackPrompt) {
      chrome.notifications.create(`phishmind-${result.id ?? Date.now()}`, {
        type: "basic",
        iconUrl: "icons/icon128.png",
        title: "PhishMind: likely PHISHING",
        message: `Risk score ${result.risk_score}/100 — ${
          result.explanation ? result.explanation.slice(0, 150) : "Open Gmail to see why."
        }`,
        priority: 2,
      });
    }
  }

  return result;
}

async function submitFeedback(scanId, feedback) {
  return apiFetch(`/api/v1/scan/${scanId}/feedback`, {
    method: "POST",
    body: JSON.stringify({ feedback }),
  });
}

async function checkHealth() {
  try {
    await apiFetch("/api/v1/health");
    return true;
  } catch {
    return false;
  }
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  (async () => {
    try {
      switch (message?.type) {
        case "PHISHMIND_SCAN": {
          const result = await scanEmail(message.rawEmailText);
          sendResponse({ ok: true, data: result });
          break;
        }
        case "PHISHMIND_FEEDBACK": {
          const result = await submitFeedback(message.scanId, message.feedback);
          sendResponse({ ok: true, data: result });
          break;
        }
        case "PHISHMIND_GET_SETTINGS": {
          sendResponse({ ok: true, data: await getSettings() });
          break;
        }
        case "PHISHMIND_SET_SETTINGS": {
          await chrome.storage.sync.set(message.settings || {});
          sendResponse({ ok: true, data: await getSettings() });
          break;
        }
        case "PHISHMIND_CHECK_HEALTH": {
          sendResponse({ ok: true, data: await checkHealth() });
          break;
        }
        case "PHISHMIND_GET_LAST_SCAN": {
          const { lastScan, lastScanAt } = await chrome.storage.local.get([
            "lastScan",
            "lastScanAt",
          ]);
          sendResponse({ ok: true, data: { lastScan: lastScan || null, lastScanAt: lastScanAt || null } });
          break;
        }
        default:
          sendResponse({ ok: false, error: `Unknown message type: ${message?.type}` });
      }
    } catch (err) {
      sendResponse({ ok: false, error: err instanceof Error ? err.message : String(err) });
    }
  })();
  return true; // keep the message channel open for the async response
});
