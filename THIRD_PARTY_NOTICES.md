# Third-Party Notices

Rest Brain does **not** bundle or copy any third-party source code. The packages below are
installed separately by `pip` from `requirements.txt` and `requirements-dev.txt`, and each stays
under its own license.

## Runtime dependencies

| Package | License | Project |
|---|---|---|
| FastAPI | MIT | https://github.com/fastapi/fastapi |
| Starlette (via FastAPI) | BSD-3-Clause | https://github.com/encode/starlette |
| Pydantic (via FastAPI) | MIT | https://github.com/pydantic/pydantic |
| Uvicorn | BSD-3-Clause | https://github.com/encode/uvicorn |
| python-dotenv | BSD-3-Clause | https://github.com/theskumar/python-dotenv |

## Development dependencies

| Package | License | Project |
|---|---|---|
| pytest | MIT | https://github.com/pytest-dev/pytest |
| pytest-asyncio | Apache-2.0 | https://github.com/pytest-dev/pytest-asyncio |
| HTTPX | BSD-3-Clause | https://github.com/encode/httpx |

## External tools (not included)

| Tool | Notes |
|---|---|
| AGY (Google Antigravity) CLI | Proprietary. Installed and signed in by the user, under Google's terms. Rest Brain only runs it as a separate process. |
| pm2 | Optional process manager, AGPL-3.0. Installed separately with npm; Rest Brain only ships a config file for it and does not include or link its code. |
