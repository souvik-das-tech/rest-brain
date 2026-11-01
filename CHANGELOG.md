# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.0.0] - 2026-11-01

First public release.

### Added

- FastAPI REST API over the AGY (Antigravity) CLI.
- Chat sessions backed by a warm stream-json AGY process, with restart and transcript replay after
  a crash, time-out or turn limit, and a one-shot fallback.
- Stateless `POST /ask` with native JSON Schema enforcement.
- `json` and `schema` options that return the reply parsed as JSON.
- `GET /health` with AGY install and sign-in status and a suggested fix, cached for 60 seconds.
- `GET /models`, read live from `agy models`.
- HTTP Basic auth, CORS, a single error shape, Swagger UI and ReDoc.
- Configuration through `.env`, environment variables or command-line options.
- pm2 config and setup/run scripts for Windows and Linux.
- Test suite with a fake AGY, and CI on Ubuntu and Windows.

[Unreleased]: https://github.com/souvik-das-tech/rest-brain/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/souvik-das-tech/rest-brain/releases/tag/v2.0.0
