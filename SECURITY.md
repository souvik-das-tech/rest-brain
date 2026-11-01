# Security Policy

## Supported versions

Only the latest release gets security fixes.

| Version | Supported |
|---|---|
| 2.x | Yes |
| < 2.0 | No |

## Reporting a vulnerability

Please **do not** open a public issue for security problems.

Report them privately through GitHub:
[Report a vulnerability](https://github.com/souvik-das-tech/rest-brain/security/advisories/new)
(the **Security** tab of the repository, then **Report a vulnerability**).

Please include:

- what the problem is and what an attacker could do with it,
- steps to reproduce, or a proof of concept,
- the Rest Brain version, OS and Python version.

You can expect a first reply within 7 days. Once a fix is ready, it is released and the advisory is
published with credit to you, unless you prefer to stay anonymous.

## Deployment notes

Rest Brain gives callers the use of the AGY account signed in on the machine. To run it safely:

- Keep the default `BRAIN_HOST=127.0.0.1` unless other machines need access.
- Set `BRAIN_USERNAME` and `BRAIN_PASSWORD` to a long, random password before listening on the network.
- Put it behind HTTPS (for example nginx) when it is reachable over the internet: Basic auth sends
  the password with every request.
- Keep `BRAIN_CORS` to the origins that need it rather than `*`.
- Never commit your `.env` file.
