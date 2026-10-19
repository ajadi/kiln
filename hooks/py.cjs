// Kiln hook launcher for Gemini CLI: run a Kiln hook script with the first Python 3.10+ found.
//   node py.cjs <hook script path> [args...]
// Gemini runs hook commands in PowerShell on Windows and bash elsewhere, and node is always there
// (Gemini CLI is a node program). macOS and many Linux systems have only python3, Windows
// usually only python or the py launcher (its python3 can be the Microsoft Store stub). The
// working interpreter (sys.executable) is cached.
"use strict"
const { spawnSync } = require("node:child_process")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")

const [script, ...args] = process.argv.slice(2)
const home = process.env.KILN_HOME || path.join(os.homedir(), ".kiln")
const cache = path.join(home, "hook-python.json")
const probe = "import sys; print(sys.executable) if sys.version_info >= (3, 10) else sys.exit(1)"
const candidates = process.platform === "win32"
  ? [["python"], ["py", "-3"], ["python3"]]
  : [["python3"], ["python"]]

function find() {
  try {
    const exe = JSON.parse(fs.readFileSync(cache, "utf8")).python
    if (exe && fs.existsSync(exe)) return exe
  } catch {}
  for (const [cmd, ...pre] of candidates) {
    const p = spawnSync(cmd, [...pre, "-c", probe], { encoding: "utf8", timeout: 10000 })
    const exe = p.status === 0 && (p.stdout || "").trim()
    if (exe && fs.existsSync(exe)) {
      try {
        fs.mkdirSync(home, { recursive: true })
        fs.writeFileSync(cache, JSON.stringify({ python: exe }) + "\n")
      } catch {}
      return exe
    }
  }
  return null
}

const python = find()
if (!python) {
  process.stderr.write("Kiln: no Python 3.10+ found (python, python3, py -3); Kiln's hooks " +
                      "(guard, session state) are not running. Install Python 3.11+ and restart.\n")
  process.exit(1)
}
let input = Buffer.alloc(0)
try { input = fs.readFileSync(0) } catch {}
const run = spawnSync(python, [script, ...args], { input, stdio: ["pipe", "inherit", "inherit"] })
process.exit(run.status === null ? 1 : run.status)
