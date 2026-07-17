/**
 * FanFlow AI — frontend logic.
 * Vanilla JS, no build step, so the demo runs from a single Flask process.
 * All DOM insertion of server data uses textContent (never innerHTML) to
 * avoid reflecting untrusted content as HTML.
 */
(() => {
  "use strict";

  const zoneListEl = document.getElementById("zone-list");
  const crowdStatusEl = document.getElementById("crowd-status");
  const refreshBtn = document.getElementById("refresh-crowd");
  const findGateBtn = document.getElementById("find-gate");
  const gateSuggestionEl = document.getElementById("gate-suggestion");
  const chatForm = document.getElementById("chat-form");
  const chatInput = document.getElementById("chat-input");
  const chatLog = document.getElementById("chat-log");
  const chatErrorEl = document.getElementById("chat-error");

  const history = [];

  async function fetchJSON(url, options) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.error || `Request failed (${response.status})`);
    }
    return data;
  }

  function renderCrowd(data) {
    zoneListEl.innerHTML = "";
    data.zones.forEach((zone) => {
      const li = document.createElement("li");
      li.className = "zone-row";

      const name = document.createElement("span");
      name.className = "zone-name";
      name.textContent = zone.zone;

      const pct = document.createElement("span");
      pct.className = "zone-pct";
      pct.textContent = `${zone.occupancy_pct}%`;

      const track = document.createElement("div");
      track.className = "zone-bar-track";
      const fill = document.createElement("div");
      fill.className = `zone-bar-fill level-${zone.level}`;
      fill.style.width = `${zone.occupancy_pct}%`;
      track.appendChild(fill);

      const rec = document.createElement("span");
      rec.className = "zone-recommendation";
      rec.textContent = zone.recommendation;

      li.append(name, pct, track, rec);
      zoneListEl.appendChild(li);
    });

    crowdStatusEl.textContent =
      data.critical_count > 0
        ? `${data.critical_count} zone(s) at critical occupancy.`
        : "All zones within normal operating range.";
  }

  async function loadCrowd() {
    crowdStatusEl.textContent = "Loading current occupancy…";
    try {
      const data = await fetchJSON("/api/crowd");
      renderCrowd(data);
    } catch (err) {
      crowdStatusEl.textContent = "Couldn't load occupancy data right now.";
    }
  }

  async function findGate() {
    gateSuggestionEl.textContent = "Checking current occupancy…";
    try {
      const data = await fetchJSON("/api/navigate", { method: "POST" });
      gateSuggestionEl.textContent = data.suggestion;
    } catch (err) {
      gateSuggestionEl.textContent = "Couldn't fetch a suggestion right now.";
    }
  }

  function appendBubble(text, role) {
    const bubble = document.createElement("div");
    bubble.className = `chat-bubble chat-bubble-${role}`;
    bubble.textContent = text;
    chatLog.appendChild(bubble);
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  async function sendMessage(event) {
    event.preventDefault();
    chatErrorEl.textContent = "";
    const message = chatInput.value.trim();
    if (!message) return;

    appendBubble(message, "user");
    chatInput.value = "";
    chatInput.disabled = true;

    try {
      const data = await fetchJSON("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, history }),
      });
      appendBubble(data.reply, "assistant");
      history.push({ role: "user", content: message });
      history.push({ role: "assistant", content: data.reply });
    } catch (err) {
      chatErrorEl.textContent = err.message;
    } finally {
      chatInput.disabled = false;
      chatInput.focus();
    }
  }

  refreshBtn.addEventListener("click", loadCrowd);
  findGateBtn.addEventListener("click", findGate);
  chatForm.addEventListener("submit", sendMessage);

  loadCrowd();
})();
