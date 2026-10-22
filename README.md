# Kiln for Gemini CLI

Version 0.10.1.

This branch is Kiln packaged for Gemini CLI. Gemini installs an extension from the top of a
branch, and the main branch of this repository is laid out for Claude Code, so the Gemini build
lives here. It is generated from the main branch; changes go there, not here.

What Kiln is and how to use it: [README](https://github.com/ajadi/kiln#readme) and
[GUIDE](https://github.com/ajadi/kiln/blob/master/GUIDE.md).

## Install

Once per computer:

```bash
gemini extensions install https://github.com/ajadi/kiln --ref gemini-extension --consent
gemini extensions disable kiln --scope user
```

Keep `--ref gemini-extension`: without it Gemini looks at the main branch and finds nothing to
install. The second line keeps Kiln off in folders that are not games. You need Python on PATH.

## Use it in a project

In your game folder:

```bash
gemini extensions enable kiln --scope workspace
```

Restart Gemini in that folder and type `/kiln:setup`. It asks a few questions, connects Blender
and your engine editor, and offers to copy Kiln's policy file to `~/.gemini/policies/kiln.toml`
(then Kiln's skills load without asking each time).

Commands are `/kiln:<name>`. The specialists are subagents named `kiln-<role>`; Gemini runs one
at a time.

## Update

```bash
gemini extensions update kiln
```

Restart Gemini, then type `/kiln:update all` in any Kiln project.

Tested with gemini-cli 0.64.0 against a local test server; not yet with a real Gemini model.
MIT licence ([LICENSE](LICENSE)). Changes: [CHANGELOG.md](CHANGELOG.md).
