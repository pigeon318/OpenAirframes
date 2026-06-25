#!/bin/bash
set -e

echo "OpenAirframes Feeder Setup"
echo "=========================="
echo

SERVER_URL="https://api.pigeite.com"
echo "Server: $SERVER_URL"
echo

read -p "Feeder name (e.g., London Station): " FEEDER_NAME
if [ -z "$FEEDER_NAME" ]; then
  echo "Error: Feeder name is required"
  exit 1
fi

read -p "Location (optional, e.g., London, UK): " LOCATION

echo
echo "Setting up environment..."

if [ ! -d "venv" ]; then
  python3 -m venv venv
fi

source venv/bin/activate
pip install -q -r requirements.txt

echo "Registering feeder with server..."

RESPONSE=$(curl -s -X POST "$SERVER_URL/feeders/register" \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"$FEEDER_NAME\", \"location\": $([ -z "$LOCATION" ] && echo 'null' || echo "\"$LOCATION\"")}")

if [ -z "$RESPONSE" ]; then
  echo "Error: No response from server at $SERVER_URL"
  echo "Please check the server URL and try again."
  exit 1
fi

KEY=$(echo "$RESPONSE" | python3 -c "import sys, json; data = json.load(sys.stdin); print(data.get('key', ''))" 2>/dev/null || echo "")

if [ -z "$KEY" ]; then
  echo "Error: Server returned invalid response"
  echo "Response: $RESPONSE"
  exit 1
fi

echo "✓ Registered successfully!"
echo "  Feeder key: $KEY"
echo

echo "Saving config..."
python3 scripts/feeder_client.py --server "$SERVER_URL" --key "$KEY" --save

echo "✓ Config saved to feeder.json"
echo

echo "Starting feeder client..."
python3 scripts/feeder_client.py
