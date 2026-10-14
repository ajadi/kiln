"""Is the user away from this PC? Stdlib only. Exit 0 = away (the autoplayer may take the screen),
1 = present.

  python presence.py [--min-idle 600]

Away when `.kiln/away` exists (the user said "I'm away"; delete it when back) or the OS input idle
time is >= --min-idle seconds: Windows GetLastInputInfo, Linux `xprintidle` (X11) when installed,
macOS `ioreg -c IOHIDSystem` HIDIdleTime. Unknown idle time counts as present.
Output: JSON {away, idle_s, reason}.
"""

import argparse
import json
import os
import platform
import re
import subprocess
import sys


def idle_seconds():
    system = platform.system()
    try:
        if system == "Windows":
            import ctypes

            class LASTINPUTINFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

            info = LASTINPUTINFO()
            info.cbSize = ctypes.sizeof(info)
            if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
                return None
            now = ctypes.windll.kernel32.GetTickCount() & 0xFFFFFFFF
            return ((now - info.dwTime) & 0xFFFFFFFF) / 1000.0
        if system == "Darwin":
            out = subprocess.run(["ioreg", "-c", "IOHIDSystem"], capture_output=True, text=True,
                                 timeout=5).stdout
            m = re.search(r'"HIDIdleTime" = (\d+)', out)
            return int(m.group(1)) / 1e9 if m else None
        out = subprocess.run(["xprintidle"], capture_output=True, text=True, timeout=5).stdout
        return int(out.strip()) / 1000.0 if out.strip().isdigit() else None
    except (OSError, ValueError, subprocess.SubprocessError, AttributeError):
        return None


def check(min_idle, root="."):
    if os.path.exists(os.path.join(root, ".kiln", "away")):
        return {"away": True, "idle_s": idle_seconds(), "reason": "flag .kiln/away"}
    idle = idle_seconds()
    if idle is not None and idle >= min_idle:
        return {"away": True, "idle_s": round(idle, 1), "reason": f"idle >= {min_idle} s"}
    return {"away": False, "idle_s": None if idle is None else round(idle, 1),
            "reason": "user present" if idle is not None else "idle time unknown: user present"}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--min-idle", type=float, default=600.0)
    a = ap.parse_args()
    res = check(a.min_idle)
    print(json.dumps(res))
    sys.exit(0 if res["away"] else 1)


if __name__ == "__main__":
    main()
