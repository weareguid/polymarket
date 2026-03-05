#!/bin/bash
# ──────────────────────────────────────────────────────────────────
# run_dashboard_chrome.sh
#
# Genera el dashboard de Polymarket y lo abre en Chrome.
# Diseñado para correr via cron lunes a viernes.
#
# Cron entry:
#   0 9 * * 1-5 /Users/santiagobattezzati/repos/Polymarket/scripts/run_dashboard_chrome.sh >> /Users/santiagobattezzati/repos/Polymarket/logs/dashboard_cron.log 2>&1
# ──────────────────────────────────────────────────────────────────

REPO_DIR="/Users/santiagobattezzati/repos/Polymarket"
PYTHON="/Users/santiagobattezzati/.pyenv/versions/3.11.12/bin/python3"
TODAY=$(date +%Y-%m-%d)
DASHBOARD="$REPO_DIR/data/processed/dashboard_$TODAY.html"
LOG_DIR="$REPO_DIR/logs"

mkdir -p "$LOG_DIR"

echo "──────────────────────────────────────"
echo "Polymarket dashboard — $TODAY $(date +%H:%M)"
echo "──────────────────────────────────────"

cd "$REPO_DIR"
"$PYTHON" generate_dashboard.py --no-open

if [ -f "$DASHBOARD" ]; then
    echo "Dashboard guardado: $DASHBOARD"
    open -a "Google Chrome" "file://$DASHBOARD"
    echo "Abierto en Chrome."
else
    echo "ERROR: dashboard no encontrado en $DASHBOARD"
    exit 1
fi
