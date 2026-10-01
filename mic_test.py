"""
Mic diagnostic for Clap Lock
------------------------------
Run this BEFORE brain.py if claps aren't registering at all.
It shows:
  1. every input device Windows/sounddevice can see, with its index
  2. a live level meter for 8 seconds so you can see if clapping moves it

Run:
    python mic_test.py
    python mic_test.py --device 3      (to test a specific device index)
"""

import argparse
import sys
import numpy as np
import sounddevice as sd

parser = argparse.ArgumentParser()
parser.add_argument("--device", type=int, default=None, help="device index to test")
args = parser.parse_args()

print("=== Available input devices ===")
for i, dev in enumerate(sd.query_devices()):
    if dev["max_input_channels"] > 0:
        marker = " <-- default" if i == sd.default.device[0] else ""
        print(f"[{i}] {dev['name']}  (inputs: {dev['max_input_channels']}){marker}")

device = args.device if args.device is not None else sd.default.device[0]
samplerate = int(sd.query_devices(device)["default_samplerate"])
print(f"\nUsing device index {device} at {samplerate}Hz. Testing for 8 seconds - CLAP a few times.\n")
print("If this bar never moves even when you clap loudly right next to the")
print("laptop, the wrong device is selected - rerun with --device <index>")
print("using one of the numbers listed above.\n")


peak_seen = 0.0


def callback(indata, frames, time_info, status):
    global peak_seen
    if status:
        print(status, file=sys.stderr)
    rms = float(np.sqrt(np.mean(indata.astype(np.float64) ** 2)))
    if rms > peak_seen:
        peak_seen = rms
        print(f"\nNEW PEAK: {rms:.4f}" + ("  <-- loud enough (> 0.12)" if rms > 0.12 else "  (still below 0.12)"))
    bar_len = min(int(rms * 200), 60)
    bar = "#" * bar_len
    print(f"\rlevel: {rms:6.4f} |{bar:<60}|", end="", flush=True)


try:
    with sd.InputStream(device=device, callback=callback, channels=1, samplerate=samplerate, blocksize=512):
        sd.sleep(8000)
except Exception as e:
    print(f"\nCould not open device {device}: {e}")

print(f"\n\nDone. Highest level seen during the whole test: {peak_seen:.4f}")
print("That should be well above ONSET_THRESHOLD (0.12) in brain.py during your loudest clap.")