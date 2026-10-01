"""
List audio devices grouped by host API (MME, WASAPI, WDM-KS, etc).
On Windows, the same physical mic often shows up once per backend, and
PortAudio can sometimes only capture from the WASAPI version of a modern
"Smart Sound" array mic, not the older MME one.

Run:
    python list_devices.py
"""

import sounddevice as sd

hostapis = sd.query_hostapis()
devices = sd.query_devices()

for hi, hostapi in enumerate(hostapis):
    print(f"\n=== Host API [{hi}]: {hostapi['name']} ===")
    for i in hostapi["devices"]:
        dev = devices[i]
        if dev["max_input_channels"] > 0:
            default_marker = " <-- default input" if i == sd.default.device[0] else ""
            print(f"  [{i}] {dev['name']}  "
                  f"(in:{dev['max_input_channels']}, rate:{dev['default_samplerate']:.0f}){default_marker}")

print(f"\nDefault input device overall: {sd.default.device[0]}")
print("\nIf a WASAPI entry exists for your mic, try that index with mic_test.py --device <n>.")
