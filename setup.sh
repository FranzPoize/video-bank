#!/usr/bin/env bash
# Video Bank — Ubuntu self-hosting setup script
#
# Usage:
#   chmod +x setup.sh && ./setup.sh
#
# This script installs system dependencies and sets up a Python venv.
# Run it once on a fresh Ubuntu server.

set -euo pipefail

echo "==> Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv ffmpeg

echo "==> Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

echo "==> Installing Python packages..."
pip install -r requirements.txt

echo "==> Creating data and upload directories..."
mkdir -p data uploads/videos uploads/thumbnails

echo ""
echo "Setup complete! To run the server:"
echo "  1. Activate the venv: source venv/bin/activate"
echo "  2. Start the app:     uvicorn app.main:app --host 0.0.0.0 --port 8000"
echo ""
echo "Or install as a systemd service:"
echo "  sudo cp video-bank.service /etc/systemd/system/"
echo "  sudo systemctl enable --now video-bank"
