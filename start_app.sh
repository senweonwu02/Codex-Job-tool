#!/bin/bash
echo ""
echo " ========================================="
echo "   Codex - Starting up..."
echo " ========================================="
echo ""

# Install dependencies
pip install flask --quiet

echo " Starting server..."
echo " Open your browser at: http://localhost:5050"
echo ""

# Open browser (works on Mac and Linux)
if command -v open &>/dev/null; then
  sleep 1 && open "http://localhost:5050" &
elif command -v xdg-open &>/dev/null; then
  sleep 1 && xdg-open "http://localhost:5050" &
fi

python3 app.py
