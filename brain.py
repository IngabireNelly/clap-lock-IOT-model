"""
Clap Lock - Brain (runs on your laptop)
-----------------------------------------
Listens on the laptop mic, tells a clap apart from a cough / dropped pen /
talking, groups claps into one rhythm "event", then sends that rhythm to the
backend to either ENROLL it (first run) or CHECK it (every run after).

While the real ESP32 isn't attached yet, this prints what the body WOULD do
("fake body") so you can test the whole brain+cloud chain alone, exactly as
the brief asks.

Install:
    pip install sounddevice numpy requests

Run:
    python brain.py                      # first time: enrolls your rhythm
    python brain.py                      # every time after: checks it
    python brain.py --enroll             # force re-enrollment
"""

import argparse
import threading
import time
import numpy as np
import requests
import sounddevice as sd

BACKEND_URL = "http://127.0.0.1:5000"   # change to your backend's address

SAMPLE_RATE = 44100
BLOCK_SIZE = 512                 # ~11.6ms per block -> fine time resolution

# ---- What counts as a clap vs. noise ----
ONSET_THRESHOLD = 0.12           # RMS level that starts an "event"
OFFSET_THRESHOLD = 0.05          # RMS level that ends an "event" (hysteresis)
MAX_CLAP_DURATION = 0.14         # seconds: claps are short & percussive.
                                 # A cough or spoken word runs noticeably longer.
MIN_CLAP_DURATION = 0.005        # seconds: filters out single-sample spikes

# ---- Grouping claps into one rhythm "event" ----
MAX_GAP_BETWEEN_CLAPS = 1.2      # seconds: longer silence than this ends the sequence
MIN_CLAPS_PER_SEQUENCE = 2       # need at least 2 claps to have a rhythm (1+ gaps)


class ClapListener:
    def __init__(self):
        self.in_event = False
        self.event_start = None
        self.event_peak = 0.0
        self.clap_times = []       # timestamps of accepted claps in the current sequence
        self.last_clap_time = None
        self.on_sequence_done = None   # callback(intervals: list[float])

    def _block_rms(self, indata):
        return float(np.sqrt(np.mean(indata.astype(np.float64) ** 2)))

    def _accept_or_reject(self, duration, peak):
        if duration < MIN_CLAP_DURATION:
            return False, "too short / spurious"
        if duration > MAX_CLAP_DURATION:
            return False, "too long for a clap (cough/talk/dropped item?)"
        return True, "clap"

    def _maybe_close_sequence(self, now):
        if not self.clap_times:
            return
        if now - self.last_clap_time > MAX_GAP_BETWEEN_CLAPS:
            claps = self.clap_times
            self.clap_times = []
            self.last_clap_time = None
            if len(claps) >= MIN_CLAPS_PER_SEQUENCE:
                intervals = [round(b - a, 3) for a, b in zip(claps, claps[1:])]
                if self.on_sequence_done:
                    self.on_sequence_done(intervals)
            else:
                print(f"(only {len(claps)} clap(s), need at least {MIN_CLAPS_PER_SEQUENCE} - ignored)")

    def audio_callback(self, indata, frames, time_info, status):
        now = time.time()
        rms = self._block_rms(indata)

        if not self.in_event and rms > ONSET_THRESHOLD:
            self.in_event = True
            self.event_start = now
            self.event_peak = rms

        elif self.in_event:
            self.event_peak = max(self.event_peak, rms)
            if rms < OFFSET_THRESHOLD:
                duration = now - self.event_start
                self.in_event = False
                ok, reason = self._accept_or_reject(duration, self.event_peak)
                if ok:
                    self.clap_times.append(now)
                    self.last_clap_time = now
                    print(f"clap accepted (duration {duration*1000:.0f}ms, peak {self.event_peak:.2f})")
                else:
                    print(f"ignored sound: {reason} (duration {duration*1000:.0f}ms)")

        self._maybe_close_sequence(now)


def fake_body_act(decision):
    """Stand-in for the ESP32 while it isn't attached. Mirrors the real pins."""
    action = decision.get("action")
    reason = decision.get("reason", "")
    print("\n--- fake body ---")
    if action == "unlock":
        print("SERVO  -> open")
        print("LED    -> GREEN")
        print("BUZZER -> short beep")
    else:
        print("SERVO  -> stays shut")
        print("LED    -> RED")
        print("BUZZER -> long buzz")
    print(f"(reason: {reason})")
    print("-----------------\n")


def enroll(intervals):
    print(f"Enrolling rhythm with gaps {intervals} ...")
    r = requests.post(f"{BACKEND_URL}/enroll", json={"intervals": intervals})
    r.raise_for_status()
    print("Enrolled:", r.json())


def check(intervals):
    print(f"Checking rhythm with gaps {intervals} ...")
    r = requests.post(f"{BACKEND_URL}/check", json={"intervals": intervals})
    r.raise_for_status()
    decision = r.json()
    print("Backend says:", decision)
    fake_body_act(decision)


def backend_has_enrollment():
    r = requests.get(f"{BACKEND_URL}/status")
    r.raise_for_status()
    return r.json().get("enrolled", False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--enroll", action="store_true", help="force (re)enrollment")
    args = parser.parse_args()

    should_enroll = args.enroll or not backend_has_enrollment()

    if should_enroll:
        # Enrollment is deliberate and one-shot: wait for the user, capture
        # exactly ONE rhythm, store it, then stop. This is what was missing
        # before - without a gate, every ambient sound sequence (background
        # noise, talking) got auto-enrolled, overwriting the real rhythm.
        input(f"\nPress ENTER, then clap the rhythm you want to lock in "
              f"({MIN_CLAPS_PER_SEQUENCE}+ claps, pause between each). ")
        print(f"Listening... clap now, then pause > {MAX_GAP_BETWEEN_CLAPS}s when done.\n")

        done = threading.Event()

        def enroll_once(intervals):
            enroll(intervals)
            done.set()

        listener = ClapListener()
        listener.on_sequence_done = enroll_once

        with sd.InputStream(callback=listener.audio_callback,
                             channels=1, samplerate=SAMPLE_RATE, blocksize=BLOCK_SIZE):
            while not done.is_set():
                time.sleep(0.05)

        print("\nRhythm locked in. Run `python brain.py` again (no flags) to test matching it.")
        return

    # Check mode: runs continuously, exactly like it will on grading day -
    # every detected rhythm gets checked against what's enrolled.
    print("Clap Lock brain running. CHECKING claps against your enrolled rhythm.")
    print(f"Clap your rhythm ({MIN_CLAPS_PER_SEQUENCE}+ claps), then pause > {MAX_GAP_BETWEEN_CLAPS}s. Ctrl+C to stop.\n")

    listener = ClapListener()
    listener.on_sequence_done = check

    with sd.InputStream(callback=listener.audio_callback,
                         channels=1,
                         samplerate=SAMPLE_RATE,
                         blocksize=BLOCK_SIZE):
        while True:
            time.sleep(0.05)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")