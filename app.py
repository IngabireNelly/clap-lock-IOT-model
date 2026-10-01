"""
Clap Lock - Backend (the "cloud")
----------------------------------
One source of truth: the enrolled clap rhythm.
Two jobs:
  1. Let the brain (laptop) enroll a rhythm and check a new rhythm against it.
  2. Let the body (ESP32) poll for the latest decision and act on it.

Run:
    pip install flask
    python app.py
Default: http://0.0.0.0:5000

Endpoints
---------
POST /enroll
    body: {"intervals": [0.32, 0.58]}
    Stores this as the reference rhythm. Overwrites any previous enrollment.

POST /check
    body: {"intervals": [0.30, 0.61]}
    Compares against the stored reference. Always succeeds (200) and returns
    a decision; it also queues that decision for the ESP32 to pick up.
    returns: {"match": true/false, "action": "unlock"/"deny", "reason": "..."}

GET /latest
    The ESP32 calls this. Returns the most recent *unconsumed* decision and
    marks it consumed, so each clap event triggers the body exactly once:
        {"action": "unlock"/"deny"/"none"}
    "none" means nothing new since the ESP32 last asked.

GET /status
    Debug/demo helper: shows whether a rhythm is enrolled and the last few
    check results. Not used by the ESP32.
"""

from flask import Flask, request, jsonify
import time

app = Flask(__name__)

# ---- "One truth" lives here ----
state = {
    "reference_intervals": None,   # e.g. [0.32, 0.58] - seconds between claps
    "pending_action": None,        # "unlock" | "deny" | None (already consumed)
    "last_results": [],            # small history for the /status debug view
}

# How much timing wiggle room we allow, as a fraction of each interval.
# 0.35 means an interval can be 35% faster or slower than enrolled and still match.
TOLERANCE = 0.35


def compare_patterns(reference, attempt):
    """Return (match: bool, reason: str)."""
    if reference is None:
        return False, "no rhythm enrolled yet"

    if len(reference) != len(attempt):
        return False, f"expected {len(reference)} gaps between claps, got {len(attempt)}"

    for i, (ref, got) in enumerate(zip(reference, attempt)):
        allowed = ref * TOLERANCE
        if abs(ref - got) > allowed:
            return False, f"gap {i + 1} off: expected ~{ref:.2f}s, got {got:.2f}s"

    return True, "rhythm matched"


@app.route("/enroll", methods=["POST"])
def enroll():
    data = request.get_json(force=True)
    intervals = data.get("intervals")

    if not intervals or not isinstance(intervals, list):
        return jsonify({"ok": False, "error": "send {'intervals': [...]}"}), 400

    state["reference_intervals"] = intervals
    print(f"[ENROLL] stored reference rhythm: {intervals}")
    return jsonify({"ok": True, "stored": intervals})


@app.route("/check", methods=["POST"])
def check():
    data = request.get_json(force=True)
    intervals = data.get("intervals")

    if not intervals or not isinstance(intervals, list):
        return jsonify({"ok": False, "error": "send {'intervals': [...]}"}), 400

    match, reason = compare_patterns(state["reference_intervals"], intervals)
    action = "unlock" if match else "deny"

    state["pending_action"] = action
    state["last_results"].append({
        "ts": time.time(),
        "intervals": intervals,
        "match": match,
        "reason": reason,
    })
    state["last_results"] = state["last_results"][-10:]  # keep it short

    print(f"[CHECK] {intervals} -> {action} ({reason})")
    return jsonify({"match": match, "action": action, "reason": reason})


@app.route("/latest", methods=["GET"])
def latest():
    """Polled by the ESP32. Consumes the pending action so it only fires once."""
    action = state["pending_action"] or "none"
    state["pending_action"] = None
    return jsonify({"action": action})


@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "enrolled": state["reference_intervals"] is not None,
        "reference_intervals": state["reference_intervals"],
        "last_results": state["last_results"],
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
