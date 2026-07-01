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
echo "Which ADS-B software are you running?"
echo "  1) dump1090-mutability (default)"
echo "  2) ADSB.im / readsb"
echo "  3) Other (enter path manually)"
read -p "Choice [1]: " SOURCE_CHOICE

case "$SOURCE_CHOICE" in
  2) SOURCE="/run/readsb/aircraft.json" ;;
  3)
    read -p "Path to aircraft.json: " SOURCE
    if [ -z "$SOURCE" ]; then
      echo "Error: Path is required"
      exit 1
    fi
    ;;
  *) SOURCE="/run/dump1090-mutability/aircraft.json" ;;
esac

echo "Source: $SOURCE"
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
python3 scripts/feeder_client.py --server="$SERVER_URL" --key="$KEY" --source="$SOURCE" --save

echo "✓ Config saved to feeder.json"
echo
echo "Setup complete! To start the feeder, run:"
echo
echo "  cd ~/openairframes"
echo "  source venv/bin/activate"
echo "  python3 scripts/feeder_client.py"
echo
echo "The feeder will read from: $SOURCE"
echo "Your config is saved in feeder.json, so next time you can just run the command above."
echo
echo "To keep it running in the background, you can use tmux or screen:"
echo "  tmux new-session -d -s openairframes 'cd ~/openairframes && source venv/bin/activate && python3 scripts/feeder_client.py'"
