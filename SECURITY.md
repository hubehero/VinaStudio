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

## Scope

The application runs locally: a Qt window, a FastAPI service bound to loopback,
and spawned docking processes. Reports are in scope when they involve, for
example:

- a request from a foreign web page being able to change local state, or the
  WebSocket handshake accepting an untrusted origin;
- escaping the workspace through an artifact, project or upload path;
- reading or writing files outside the workspace through a crafted structure or
  project file;
- a dependency vulnerability that is reachable through the application;
- the packaged installer or bundled binaries behaving differently from the
  source tree in a security-relevant way.

Out of scope: issues that require an already-compromised machine or an attacker
with local administrator rights; social engineering; denial of service against
your own installation; and reports that only restate a dependency advisory
without a path through the application.

## What happens next

We aim to acknowledge a report within a few days. If the report is valid, we will
agree on a disclosure date, prepare a fix and credit you in the advisory unless
you prefer to stay anonymous. There is no bug bounty.

## Code of conduct

Conduct issues are handled under [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md), not
this policy.
