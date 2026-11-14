# Security Policy

**English** · [简体中文](SECURITY.zh-CN.md)

## Supported versions

Security fixes land in the latest release. When a report affects an older
version, we will say so in the advisory and in the changelog. There are no
long-term support branches during the 0.x series.

## Reporting a vulnerability

Please report privately, not in a public issue:

1. Open the repository's **Security** tab and choose **Report a vulnerability**.
   This creates a private advisory visible to the maintainer.
2. If that option is unavailable, open a minimal issue asking for a private
   channel. Do not include vulnerability details, exploit code or personal data
   in the issue itself.

A useful report includes the version, the operating system, the steps to
reproduce, the impact you believe it has, and a minimal proof of concept. Please
avoid testing against systems or data you do not own.

## Dependency review

`uv.lock` is the source of truth for the versions that ship. The release
pre-flight checks open Dependabot and CodeQL alerts; that check is a gate, not a
complete vulnerability audit. As of 2026-11-08 the lock contains PySide6 6.12.0
and httpx 0.28.1, and does not contain `brotli` or `brotlicffi`.

Two advisories need to be read by affected library, not by package name alone:

- **CVE-2026-84975** is a libxml2 arbitrary-code-execution advisory. PySide6
  appears in distribution rebuilds because it can link libxml2; whether a
  bundle is affected depends on the libxml2 it actually carries. Inspect the
  packaged libraries rather than inferring exposure from the PySide6 version.
- **CVE-2026-111497** is an out-of-bounds write in Brotli 1.0.3 through 1.2.0.
  The project does not lock Brotli today; if a future dependency adds it, require
  a fixed release above 1.2.0.

For a source install, review the resolved set with:

```bash
uv export --frozen --format requirements-txt --no-dev --no-hashes --no-emit-project
```

Run `pip-audit` or an OSV scan against that export when adding or updating a
dependency, and treat an advisory as reachable only with a path through the
application.
On 2026-11-08, `pip-audit --no-deps` against that export (excluding the `vina`
source package, which has no wheel to audit) reported no known vulnerabilities.
This is a dated record, not a permanent guarantee; rerun it after dependency
changes.

## Scope

The application runs locally: a Qt window, a FastAPI service bound to loopback,
and spawned docking processes. Reports are in scope when they involve, for
example:

- a request from a foreign web page being able to change local state, or the
  WebSocket handshake accepting an untrusted origin;
- another local user or process driving the loopback API without the
  per-session token, or a web page reaching it through a rebound host name;
- escaping the workspace through an artifact, project or upload path;
- reading or writing files outside the workspace through a crafted structure or
  project file;
- a dependency vulnerability that is reachable through the application;
- the packaged installer or bundled binaries behaving differently from the
  source tree in a security-relevant way.

Out of scope: issues that require an already-compromised machine or an attacker
with local administrator rights; an attacker who can read the running process's
memory, attach a debugger, or access the application's browser profile under the
same user account; social engineering; denial of service against your own
installation; and reports that only restate a dependency advisory without a
path through the application.

## What happens next

We aim to acknowledge a report within a few days. If the report is valid, we will
agree on a disclosure date, prepare a fix and credit you in the advisory unless
you prefer to stay anonymous. There is no bug bounty.

## Code of conduct

Conduct issues are handled under [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md), not
this policy.
