#!/usr/bin/env bash
# Mac/Linux: botu bir kez çalıştırır (cron / systemd timer tarafından saat başı tetiklenir).
set -u
cd "$(dirname "$0")"

# cron'un kısıtlı PATH'ine Claude Code'un olası konumlarını ekle
export PATH="$HOME/.local/bin:$HOME/.npm-global/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"

if [ -f ".venv/bin/python" ]; then
  PY=".venv/bin/python"
else
  PY="python3"
fi

exec "$PY" -m bot.main "$@"
