#!/bin/bash
# -----------------------------------------
# Script to launch VL53L0X sensor app and Chromium kiosk inside venv
# -----------------------------------------

# Path to your project folder
PROJECT_DIR="/home/admin/Remote_Access_IA"

# Activate virtual environment inside project folder
source "$PROJECT_DIR/venv/bin/activate"

# Run the Python app
python3 "$PROJECT_DIR/LED-flash2.py"
