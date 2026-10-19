"""Is this folder fit to become a Kiln project? Stdlib only. Exit 0 = yes, 1 = no (says why).

  python folder_check.py [folder]      # default: the current folder

Refuses the user's home folder, any folder above it, and a drive or file-system root: there a
project-scope install is the user scope (~/.claude/settings.json, ~/.codex/config.toml,
~/.codex/agents), `git init` takes in the whole profile, and the hooks would treat every folder
below as part of the project (install audit 2026-10-19). Run it before connecting a folder.
"""

import os
import sys


def problem(folder):
    path = os.path.normcase(os.path.realpath(os.path.abspath(folder)))
    home = os.path.normcase(os.path.realpath(os.path.expanduser("~")))
    if os.path.dirname(path) == path:
        return "it is a drive or file-system root"
    if path == home:
        return "it is your home folder"
    if home.startswith(path.rstrip(os.sep) + os.sep):
        return "your home folder is inside it"
    return None


def main():
    folder = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    why = problem(folder)
    if why:
        print(f"Not a project folder: {folder} - {why}. Kiln here would change settings for every "
              "project and put the whole folder under git. Create or open a folder for this game "
              "(for example ~/games/<name>) and run it there.")
        return 1
    print(f"ok: {folder}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
