// Kiln for OpenCode: runs Kiln's Python hooks around OpenCode's tool calls.
// Copied into a project's .opencode/plugins/ by scripts/opencode_setup.py, which writes the
// Kiln plugin folder into KILN_ROOT below. Shapes recorded live from OpenCode 1.19.0:
// tool.execute.before(input {tool, sessionID}, output {args}); a subagent runs in a child
// session (session.created carries parentID); throwing denies the call.
import { spawnSync } from "node:child_process"
import { join } from "node:path"

const KILN_ROOT = process.env.KILN_PLUGIN_ROOT || "__KILN_ROOT__"
const PYTHON = process.platform === "win32" ? "python" : "python3"
const SERVERS = ["unreal-mcp-proxy", "unreal-mcp", "godot-ai", "blender", "unity", "unreal"]

function hook(directory, script, args, payload) {
  const p = spawnSync(PYTHON, ["-B", join(KILN_ROOT, "hooks", script), ...args, "--runtime", "opencode"], {
    input: JSON.stringify(payload),
    env: { ...process.env, CLAUDE_PROJECT_DIR: directory, CLAUDE_PLUGIN_ROOT: KILN_ROOT },
    encoding: "utf8",
    timeout: 30000,
  })
  const text = (p.stdout || "").trim()
  if (!text) return null
  try { return JSON.parse(text) } catch { return null }
}

// OpenCode tool call -> the Claude Code names and fields the Kiln hooks read
function toKiln(tool, args) {
  args = args || {}
  if (tool === "bash") return ["Bash", { command: args.command }]
  if (tool === "write") return ["Write", { file_path: args.filePath, content: args.content }]
  if (tool === "edit") return ["Edit", { file_path: args.filePath, old_string: args.oldString, new_string: args.newString }]
  if (tool === "task") return ["Agent", { subagent_type: args.subagent_type, prompt: args.prompt, description: args.description }]
  for (const server of SERVERS) {
    if (tool.startsWith(server + "_")) return [`mcp__${server}__${tool.slice(server.length + 1)}`, args]
  }
  return [null, null]
}

export const Kiln = async ({ directory, client }) => {
  const roles = {}      // child session -> its role (kiln-<role>)
  const pending = []    // roles started by task calls, waiting for their child session
  let main = null
  const start = hook(directory, "session.py", ["start"], {
    session_id: "", cwd: directory, hook_event_name: "SessionStart", source: "startup" })
  const context = [
    start?.hookSpecificOutput?.additionalContext || "",
    "Kiln in OpenCode: Kiln texts were written for Claude Code. Write/Edit = write/edit, " +
      "Bash = bash, the Skill tool = skill, a role kiln:<role> = the subagent kiln-<role> (task " +
      "tool). In Kiln skill files ${CLAUDE_SKILL_DIR} = .opencode/skills/<name> and " +
      "${CLAUDE_PLUGIN_ROOT} = " + KILN_ROOT + ". MCP tools mcp__<server>__<tool> are " +
      "<server>_<tool> here. A denial by the Kiln guard names the rule: follow it.",
  ].filter(Boolean).join("\n")

  return {
    "experimental.chat.system.transform": async (_input, output) => {
      output.system.push(context)
    },

    "tool.execute.before": async (input, output) => {
      const sid = input.sessionID
      if (!main && !roles[sid]) main = sid
      const [name, args] = toKiln(input.tool, output.args)
      if (!name) return
      const payload = { session_id: main || sid, cwd: directory, hook_event_name: "PreToolUse",
                        tool_name: name, tool_input: args }
      if (roles[sid]) Object.assign(payload, { agent_type: roles[sid], agent_id: sid })
      const res = hook(directory, "guard.py", [], payload)
      const spec = res?.hookSpecificOutput || {}
      if (spec.permissionDecision === "deny") throw new Error(spec.permissionDecisionReason)
      if (name === "Agent") {
        pending.push(output.args.subagent_type)
        const ctx = hook(directory, "session.py", ["subagent"], {
          ...payload, agent_type: output.args.subagent_type, hook_event_name: "SubagentStart" })
        const extra = ctx?.hookSpecificOutput?.additionalContext
        if (extra) output.args.prompt = extra + "\n\n" + output.args.prompt
      }
    },

    event: async ({ event }) => {
      const props = event.properties || {}
      if (event.type === "session.created") {
        const sid = props.info?.id || props.sessionID
        if (props.info?.parentID && pending.length) roles[sid] = pending.shift()
        else if (!props.info?.parentID && !main) main = sid  // the producer (live: a text-only turn names no tool)
      } else if (event.type === "session.idle") {
        const sid = props.sessionID
        if (roles[sid]) {
          hook(directory, "stop.py", ["subagent"], { session_id: main, cwd: directory,
            hook_event_name: "SubagentStop", agent_type: roles[sid], agent_id: sid,
            stop_hook_active: true })
          delete roles[sid]
        } else if (sid === main) {
          const res = hook(directory, "stop.py", ["stop"], { session_id: main, cwd: directory,
            hook_event_name: "Stop", stop_hook_active: false })
          if (res?.decision === "block" && client?.session?.prompt) {
            // the autopilot keeps going: the reason becomes the producer's next message
            await client.session.prompt({ path: { id: sid }, body: { parts: [{ type: "text", text: res.reason }] } })
          }
        }
      }
    },
  }
}
