// pm2 config, same file on Windows and Linux:  pm2 start ecosystem.config.js
// Settings (port, username, password, ...) go in .env next to this file; see .env.example.
const path = require("path");

const python = process.platform === "win32"
  ? path.join(__dirname, ".venv", "Scripts", "python.exe")
  : path.join(__dirname, ".venv", "bin", "python");

module.exports = {
  apps: [
    {
      name: "rest-brain",
      cwd: __dirname,
      script: "main.py",
      interpreter: python,
      autorestart: true,
      max_restarts: 10,
      min_uptime: "10s",
      restart_delay: 3000,
      kill_timeout: 10000, // time to stop the AGY processes cleanly
      env: {
        PYTHONUNBUFFERED: "1",
        PYTHONIOENCODING: "utf-8",
      },
    },
  ],
};
