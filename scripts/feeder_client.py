import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

DEFAULT_DUMP1090 = "/run/dump1090-mutability/aircraft.json"
DEFAULT_SERVER   = "http://localhost:8000"
DEFAULT_INTERVAL = 2
CONFIG_FILE      = Path(__file__).parent.parent / "feeder.json"


def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)
    print(f"Config saved to {CONFIG_FILE}")


def fetch_aircraft(source):
    if source.startswith("http://") or source.startswith("https://"):
        with urllib.request.urlopen(source, timeout=5) as r:
            return json.loads(r.read())
    with open(source) as f:
        return json.load(f)


def post_feed(server_url, key, aircraft):
    body = json.dumps({"aircraft": aircraft, "key": key}).encode()
    req = urllib.request.Request(
        f"{server_url.rstrip('/')}/feed",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Feeder-Key": key,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def run(server_url, key, source_url, interval):
    print(f"OpenAirframes feeder client starting")
    print(f"  source:   {source_url}")
    print(f"  server:   {server_url}")
    print(f"  interval: {interval}s")
    print()

    total_sent = 0
    total_accepted = 0
    errors = 0
    started = time.time()

    while True:
        try:
            data = fetch_aircraft(source_url)
            aircraft = data.get("aircraft", [])

            result = post_feed(server_url, key, aircraft)
            accepted = result.get("accepted", 0)
            total_sent += len(aircraft)
            total_accepted += accepted
            errors = 0

            elapsed = int(time.time() - started)
            print(
                f"\r  uptime {elapsed}s  |  aircraft in view: {len(aircraft)}"
                f"  |  accepted: {accepted}"
                f"  |  total sent: {total_sent}",
                end="",
                flush=True,
            )

        except KeyboardInterrupt:
            print()
            print(f"Stopped. Total sent: {total_sent}, accepted: {total_accepted}")
            sys.exit(0)

        except Exception as e:
            errors += 1
            print(f"\n  error ({errors}): {e}", flush=True)
            if errors >= 10:
                print("Too many consecutive errors, exiting.")
                sys.exit(1)

        time.sleep(interval)


def main():
    cfg = load_config()

    parser = argparse.ArgumentParser(description="OpenAirframes feeder client")
    parser.add_argument("--server",   default=cfg.get("server",   DEFAULT_SERVER))
    parser.add_argument("--key",      default=cfg.get("key",      ""))
    parser.add_argument("--source",   default=cfg.get("source",   DEFAULT_DUMP1090))
    parser.add_argument("--interval", default=cfg.get("interval", DEFAULT_INTERVAL), type=float)
    parser.add_argument("--save",     action="store_true", help="Save these settings for next time")
    args = parser.parse_args()

    if not args.key:
        print("Error: --key is required. Get your feeder key from the server admin.")
        sys.exit(1)

    if args.save:
        save_config({
            "server":   args.server,
            "key":      args.key,
            "source":   args.source,
            "interval": args.interval,
        })

    run(args.server, args.key, args.source, args.interval)


if __name__ == "__main__":
    main()
