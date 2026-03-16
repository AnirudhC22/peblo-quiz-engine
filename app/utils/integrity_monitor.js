/**
 * Peblo Academic Integrity Monitor
 * ─────────────────────────────────
 * Drop this script into any quiz page.
 * It listens for suspicious events and reports them to the backend.
 *
 * Usage:
 *   const monitor = new PebloIntegrityMonitor({
 *     apiBase: "http://localhost:8000/api/v1",
 *     sessionToken: "token-from-POST-/sessions/start",
 *   });
 *   monitor.start();
 *   // ...later, when quiz ends:
 *   const report = await monitor.end();
 */

class PebloIntegrityMonitor {
  constructor({ apiBase, sessionToken, onFlag }) {
    this.apiBase = apiBase;
    this.sessionToken = sessionToken;
    this.onFlag = onFlag || null;  // optional callback when flagged
    this.active = false;
    this._handlers = {};
    this._lastAnswerTime = null;
    this._currentQuestionId = null;
    this._questionStartTime = null;
    this._devtoolsOpen = false;
  }

  // ── Public API ──────────────────────────────────────────────────────────

  start() {
    if (this.active) return;
    this.active = true;
    this._attachHandlers();
    console.info("[Peblo Monitor] Session monitoring active.");
  }

  async end() {
    if (!this.active) return null;
    this.active = false;
    this._detachHandlers();
    const resp = await fetch(
      `${this.apiBase}/sessions/${this.sessionToken}/end`,
      { method: "POST" }
    );
    const report = await resp.json();
    console.info("[Peblo Monitor] Session ended.", report);
    return report;
  }

  /** Call this whenever the student moves to a new question. */
  setCurrentQuestion(questionId) {
    this._currentQuestionId = questionId;
    this._questionStartTime = Date.now();
  }

  /** Call this right before submitting an answer. */
  async checkSubmitSpeed() {
    if (!this._questionStartTime) return;
    const elapsed = Math.floor((Date.now() - this._questionStartTime) / 1000);
    if (elapsed < 3) {
      await this._report("fast_submit", {
        question_id: this._currentQuestionId,
        detail: `Answered in ${elapsed}s`,
      });
    }
  }

  // ── Internal event handlers ─────────────────────────────────────────────

  _attachHandlers() {
    // 1. Tab switch / page visibility
    this._handlers.visibility = () => {
      if (document.hidden) {
        this._report("tab_switch", { detail: "Student switched tabs or minimized window" });
      }
    };
    document.addEventListener("visibilitychange", this._handlers.visibility);

    // 2. Window focus loss (alt+tab, clicking outside browser)
    this._handlers.blur = () => {
      this._report("focus_loss", { detail: "Browser window lost focus" });
    };
    window.addEventListener("blur", this._handlers.blur);

    // 3. Copy-paste attempts on question text
    this._handlers.copy = (e) => {
      const sel = window.getSelection()?.toString() || "";
      if (sel.length > 10) {
        this._report("copy_paste", {
          question_id: this._currentQuestionId,
          detail: `Copied ${sel.length} characters`,
        });
      }
    };
    document.addEventListener("copy", this._handlers.copy);

    // 4. Right-click attempt
    this._handlers.contextmenu = (e) => {
      e.preventDefault();
      this._report("right_click", {
        question_id: this._currentQuestionId,
        detail: "Right-click attempted",
      });
    };
    document.addEventListener("contextmenu", this._handlers.contextmenu);

    // 5. DevTools open detection (window size heuristic)
    this._handlers.devtools = this._startDevToolsDetection();
  }

  _detachHandlers() {
    document.removeEventListener("visibilitychange", this._handlers.visibility);
    window.removeEventListener("blur", this._handlers.blur);
    document.removeEventListener("copy", this._handlers.copy);
    document.removeEventListener("contextmenu", this._handlers.contextmenu);
    if (this._handlers.devtools) clearInterval(this._handlers.devtools);
  }

  _startDevToolsDetection() {
    // Heuristic: if window.outerHeight - window.innerHeight > 200, devtools is likely docked
    return setInterval(() => {
      const heightDiff = window.outerHeight - window.innerHeight;
      const widthDiff = window.outerWidth - window.innerWidth;
      const isOpen = heightDiff > 200 || widthDiff > 200;
      if (isOpen && !this._devtoolsOpen) {
        this._devtoolsOpen = true;
        this._report("devtools_open", { detail: "DevTools panel detected open" });
      } else if (!isOpen) {
        this._devtoolsOpen = false;
      }
    }, 2000);
  }

  async _report(eventType, { question_id, detail } = {}) {
    if (!this.active) return;
    try {
      const resp = await fetch(
        `${this.apiBase}/sessions/${this.sessionToken}/event`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            event_type: eventType,
            question_id: question_id || this._currentQuestionId || null,
            detail: detail || null,
          }),
        }
      );
      const data = await resp.json();

      console.warn(`[Peblo Monitor] Event: ${eventType} | Risk score: ${data.current_risk_score}`);

      if (data.flagged && this.onFlag) {
        this.onFlag(data);
      }
    } catch (err) {
      // Fail silently — don't break the quiz if monitoring fails
      console.error("[Peblo Monitor] Failed to report event:", err);
    }
  }
}

// ── Example usage ────────────────────────────────────────────────────────
/*
// 1. Start session (call your backend first to get a session token)
const { session_token } = await fetch("/api/v1/sessions/start", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ student_id: "S001" }),
}).then(r => r.json());

// 2. Initialize monitor
const monitor = new PebloIntegrityMonitor({
  apiBase: "http://localhost:8000/api/v1",
  sessionToken: session_token,
  onFlag: (data) => {
    alert("⚠️ Integrity warning: suspicious activity detected.");
  },
});
monitor.start();

// 3. When student views a question
monitor.setCurrentQuestion("question-uuid-here");

// 4. Before answer submission
await monitor.checkSubmitSpeed();
submitAnswer();

// 5. When quiz ends
const report = await monitor.end();
console.log("Final report:", report);
*/
