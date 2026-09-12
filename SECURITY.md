# Security policy

## Supported versions

Only the latest release of Robot Reel receives security fixes. Older tags are
not patched; upgrade to the current release before reporting.

## Reporting a vulnerability

Report vulnerabilities privately through GitHub's private vulnerability
reporting for this repository:

https://github.com/noteflowai/robot-reel/security/advisories/new

Do not open a public issue for security problems. Include the affected
subcommand or page, a reproducible command, and the observed behaviour. There
is no dedicated e-mail address; the advisory form is the only private channel.

## Scope

The `robot-reel mcp` subcommand runs an MCP director server over stdio. It
exposes filesystem-backed tools (`inspect_recording`, `create_storyboard`)
whose `source` and `output` paths are meant to stay inside the workspace passed
with `--root`. `scripts/check_director_mcp.py` exercises these boundaries in CI.
Any way to read or write outside that workspace root through the MCP tools is
in scope and should be reported.

Also in scope:

- Path handling in the CLI exporters (`direct`, `compare`, `blender`, `newton`,
  `vla`, `stress`) that lets a crafted recording or plan write outside the
  chosen `--output` directory.
- Injection into the exported self-contained HTML pages through crafted
  recording or storyboard data.

Out of scope:

- Issues in third-party simulators, models, or Blender itself; report those
  upstream.
- Use of the optional billable Bedrock agent (`--agent`) with the reporter's
  own credentials.
