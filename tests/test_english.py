"""The Kiln repository is English only: code, comments, test data, skills, README and docs
(user decision for 0.7.0). Agents still talk to each user in that user's language at run time;
that happens in sessions, not in this repository.

Test data that needs a non-English language uses Polish (Latin script, three plural forms) or
French; no Cyrillic text anywhere in tracked files.
"""

import os
import re
import subprocess
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
CYRILLIC = re.compile("[" + chr(0x0400) + "-" + chr(0x04FF) + "]")  # escapes, not letters


class EnglishOnly(unittest.TestCase):
    def test_no_cyrillic_in_tracked_files(self):
        files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                               check=True).stdout.splitlines()
        found = []
        for name in files:
            try:
                with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
                    for number, line in enumerate(fh, 1):
                        if CYRILLIC.search(line):
                            found.append(f"{name}:{number}")
            except (UnicodeDecodeError, OSError):
                continue  # binary files
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
