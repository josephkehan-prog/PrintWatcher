# Security Policy

## Supported versions

Security fixes land on the latest minor release on `main`. Older
versions are not patched.

| Version | Supported |
| ------- | --------- |
| 0.4.x   | yes       |
| < 0.4   | no        |

## Reporting a vulnerability

Please **do not** open a public GitHub issue for suspected security
vulnerabilities. Instead, send a private report:

1. Use GitHub's
   [private vulnerability reporting](https://github.com/josephkehan-prog/PrintWatcher/security/advisories/new),
   or
2. Email the maintainer (see `pyproject.toml` `authors`) with subject
   line `[security] PrintWatcher`.

We aim to acknowledge reports within 5 business days and ship a fix in
the next minor release. Critical issues (RCE, credential exposure) get
a patch release.

## Threat model

PrintWatcher is designed for a single Windows desktop. The threat model
is intentionally narrow:

### Trusted

- The local Windows user running PrintWatcher.
- The OneDrive client and folder owned by that user.
- The local filesystem (history, preferences, cache).

### Untrusted

- Files dropped into the watched inbox. PrintWatcher passes them to
  SumatraPDF; SumatraPDF's parser is the boundary. Malicious PDFs that
  exploit SumatraPDF are out of scope — keep SumatraPDF up to date.
- The network. The FastAPI backend binds **only to `127.0.0.1`** with
  bearer-token auth; the discovery file in `%LOCALAPPDATA%` is the
  only way the WinUI shell learns the port and token. There is no
  external-facing endpoint by design.

### Outbound network egress

PrintWatcher is loopback-only by default but does make **one outbound
HTTPS request per 24 hours** to ``api.github.com`` from the backend
when a client hits ``GET /api/update-check``:

- URL: ``https://api.github.com/repos/josephkehan-prog/PrintWatcher/releases/latest``
- Method: GET
- Body: none
- Headers: ``Accept: application/vnd.github+json``, ``User-Agent: PrintWatcher``
- Response cached in memory for 24 h
- Network errors are swallowed; the dashboard simply doesn't show a
  banner

No user data is included in the request. The endpoint is hardcoded;
no user input flows into the URL.

**Disabling the check.** Settings → Privacy → "Check for updates"
toggles ``preferences.update_check`` (default ``true``). When false,
``GET /api/update-check`` short-circuits to a no-update response
without making the outbound call. The toggle persists in
``preferences.json`` and survives restart.

### Out of scope

- Multi-tenant deployments. PrintWatcher is single-user single-machine.
- HTTPS for the loopback server. The transport never leaves the host.
- DRM / printing-policy enforcement. SumatraPDF prints what the user
  drops in.
- Resistance to a local attacker who already has filesystem access to
  `%LOCALAPPDATA%/PrintWatcher/server.json`. That file contains the
  bearer token; whoever can read it controls the running backend, by
  design.

## Hardening checklist for releases

- [ ] `ruff check printwatcher/` clean
- [ ] `bandit -r printwatcher/ -ll` clean (0 medium+ severity)
- [ ] `pytest` green, coverage ≥ 65%
- [ ] No new dependencies pulled in by `[dev,backend]` extras without
      review
- [ ] Discovery file is created with default permissions (user-owned,
      not world-readable)
- [ ] Bearer token is generated per-process via `secrets.token_hex` in
      `printwatcher/server/__main__.py`
- [ ] Loopback bind is preserved; CI greps for `host="0.0.0.0"` and
      fails the build if it appears

## Dependency audits

Run `pip-audit` periodically:

```bash
pip-audit
```

Critical advisories on direct dependencies (`fastapi`, `uvicorn`,
`pydantic`, `watchdog`, `pillow`) trigger a patch release within 7
days.
