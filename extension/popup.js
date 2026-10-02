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

const VERDICT_COLOR = { SAFE: "#10B981", SUSPICIOUS: "#F59E0B", PHISHING: "#EF4444" };

async function refreshStatus() {
  const dot = document.getElementById("status-dot");
  const text = document.getElementById("status-text");
  const health = await sendMessage({ type: "PHISHMIND_CHECK_HEALTH" });
  const online = health.ok && health.data;
  dot.className = `dot ${online ? "dot-online" : "dot-offline"}`;
  text.textContent = online
    ? "Backend connected"
    : "Backend unreachable — start it from VS Code (see backend/README.md)";
}

async function refreshLastScan() {
  const res = await sendMessage({ type: "PHISHMIND_GET_LAST_SCAN" });
  const section = document.getElementById("last-scan");
  if (!res.ok || !res.data.lastScan) {
    section.classList.add("hidden");
    return;
  }
  const scan = res.data.lastScan;
  section.classList.remove("hidden");
  const scoreEl = document.getElementById("scan-score");
  scoreEl.textContent = scan.risk_score;
  scoreEl.style.color = VERDICT_COLOR[scan.verdict] || "#F8FAFC";
  const verdictEl = document.getElementById("scan-verdict");
  verdictEl.textContent = scan.verdict;
  verdictEl.style.color = VERDICT_COLOR[scan.verdict] || "#F8FAFC";
  document.getElementById("scan-subject").textContent = scan.subject || "(no subject)";
}

async function loadSettings() {
  const res = await sendMessage({ type: "PHISHMIND_GET_SETTINGS" });
  if (!res.ok) return;
  document.getElementById("backend-url").value = res.data.backendUrl;
  document.getElementById("dashboard-url").value = res.data.dashboardUrl;
  document.getElementById("auto-scan").checked = !!res.data.autoScan;
  document.getElementById("show-feedback").checked = !!res.data.showFeedbackPrompt;
}

document.getElementById("save-settings").addEventListener("click", async () => {
  const settings = {
    backendUrl: document.getElementById("backend-url").value.trim() || "http://localhost:8000",
    dashboardUrl: document.getElementById("dashboard-url").value.trim() || "http://localhost:5173",
    autoScan: document.getElementById("auto-scan").checked,
    showFeedbackPrompt: document.getElementById("show-feedback").checked,
  };
  await sendMessage({ type: "PHISHMIND_SET_SETTINGS", settings });
  const confirm = document.getElementById("save-confirm");
  confirm.classList.remove("hidden");
  setTimeout(() => confirm.classList.add("hidden"), 1500);
  refreshStatus();
});

document.getElementById("rescan-btn").addEventListener("click", async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !tab.url?.includes("mail.google.com")) {
    alert("Open a Gmail message in the active tab first.");
    return;
  }
  chrome.tabs.sendMessage(tab.id, { type: "PHISHMIND_FORCE_RESCAN" }, () => {
    // Rescan runs async on the page; give it a moment then refresh the popup's view.
    setTimeout(refreshLastScan, 1500);
  });
});

document.getElementById("dashboard-btn").addEventListener("click", async () => {
  const res = await sendMessage({ type: "PHISHMIND_GET_SETTINGS" });
  const url = res.ok ? res.data.dashboardUrl : "http://localhost:5173";
  chrome.tabs.create({ url });
});

loadSettings();
refreshStatus();
refreshLastScan();
