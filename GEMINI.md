# Kiln in Gemini CLI

Kiln's skills and roles were written for Claude Code. Read them with these equivalences:

- Write / Edit = write_file / replace; Bash or PowerShell = run_shell_command; the Skill tool =
  activate_skill; AskUserQuestion = ask_user.
- A Kiln role `kiln:<role>` is the subagent `kiln-<role>`: delegate with invoke_agent
  (agent_name `kiln-<role>`). Subagents cannot start subagents.
- Kiln commands are `/kiln:<name>` (setup, pipeline, run, model, track, ...).
- MCP tools named `mcp__<server>__<tool>` in Kiln texts are `mcp_<server>_<tool>` here.
- Kiln's hooks run here too: a denial names the rule; follow it instead of working around it.
