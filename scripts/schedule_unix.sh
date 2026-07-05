#!/bin/bash
# ============================================================
#  Schedule daily pipeline execution via cron (Linux/macOS)
# ============================================================
echo ""
echo "==================================================="
echo "  Agendando Pipeline B3 - Cron"
echo "==================================================="
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PYTHON_EXE="$PROJECT_ROOT/.venv/bin/python"
PIPELINE_SCRIPT="$PROJECT_ROOT/src/pipeline.py"
LOG_DIR="$PROJECT_ROOT/logs"

# Check Python
if [ ! -f "$PYTHON_EXE" ]; then
    echo "[ERROR] Python virtual environment not found at:"
    echo "        $PYTHON_EXE"
    echo ""
    echo "Please create it first:"
    echo "  python3 -m venv .venv"
    echo "  source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

mkdir -p "$LOG_DIR"

# Cron: run daily at 8 AM BRT (weekdays)
CRON_LINE="0 8 * * 1-5 $PYTHON_EXE $PIPELINE_SCRIPT >> $LOG_DIR/cron.log 2>&1"

echo "Adding the following cron entry:"
echo "  $CRON_LINE"
echo ""

read -p "Proceed? (y/N): " CONFIRM
if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
    echo "Aborted."
    exit 0
fi

# Add to crontab (avoid duplicate)
EXISTING=$(crontab -l 2>/dev/null | grep -F "$PIPELINE_SCRIPT")
if [ -n "$EXISTING" ]; then
    echo "A cron entry for this pipeline already exists. Removing it first..."
    crontab -l 2>/dev/null | grep -v -F "$PIPELINE_SCRIPT" | crontab -
fi

(crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -

echo ""
echo "✅ Cron job scheduled!"
echo "   The pipeline will run daily at 08:00 (weekdays)."
echo "   Logs: $LOG_DIR/cron.log"
echo ""
echo "To verify:  crontab -l"
echo "To remove:  crontab -e  (and delete the Radar line)"
echo ""
