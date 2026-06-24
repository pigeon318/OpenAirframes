import json
import os
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

import psycopg
from dotenv import load_dotenv

script_dir = Path(__file__).parent
data_dir = script_dir.parent / "data"
SOURCE = "Mictronics"
TRUST_ORDER = ["FAA", "UK_CAA", "Mictronics", "OpenSky", "user"]

AIRCRAFTS_URL = "https://raw.githubusercontent.com/Mictronics/readsb-protobuf/dev/webapp/src/db/aircrafts.json"
TYPES_URL = "https://raw.githubusercontent.com/Mictronics/readsb-protobuf/dev/webapp/src/db/types.json"

WTC_MAP = {
    "L": "Light",
    "M": "Medium",
    "H": "Heavy",
    "J": "Super Heavy",
}


def download(url, dest):
    print(f"Downloading {dest.name} ...", flush=True)
    urllib.request.urlretrieve(url, dest)


def ensure_files(aircrafts_path, types_path):
    if not aircrafts_path.exists():
        download(AIRCRAFTS_URL, aircrafts_path)
    if not types_path.exists():
        download(TYPES_URL, types_path)


def load_types(types_path):
    with open(types_path, encoding="utf-8") as f:
        raw = json.load(f)
    result = {}
    for code, entry in raw.items():
        if not isinstance(entry, list):
            continue
        result[code] = {
            "description": entry[0] if len(entry) > 0 else None,
            "wtc": entry[1] if len(entry) > 1 else None,
        }
    return result


def load_aircrafts(aircrafts_path, types):
    with open(aircrafts_path, encoding="utf-8") as f:
        raw = json.load(f)

    for icao_hex, entry in raw.items():
        icao_hex = icao_hex.strip().lower()
        if len(icao_hex) != 6 or not all(c in "0123456789abcdef" for c in icao_hex):
            continue

        if not isinstance(entry, list) or len(entry) < 1:
            continue

        registration = entry[0] if entry[0] else None
        type_code = entry[1] if len(entry) > 1 and entry[1] else None
        flags = entry[2] if len(entry) > 2 else None

        type_info = types.get(type_code, {}) if type_code else {}
        description = type_info.get("description")
        wtc = type_info.get("wtc")

        yield {
            "icao_hex": icao_hex,
            "registration": registration,
            "serial_number": None,
            "source_record_id": None,
            "manufacturer": None,
            "model": description,
            "type_aircraft": None,
            "type_aircraft_raw": type_code,
            "type_engine": None,
            "type_engine_raw": None,
            "engine_count": None,
            "seats": None,
            "year_manufactured": None,
            "owner_name": None,
            "owner_type": None,
            "owner_type_raw": None,
            "owner_city": None,
            "owner_state": None,
            "owner_country": None,
            "status": None,
            "status_raw": None,
            "certification": None,
            "last_action_date": None,
            "cert_issue_date": None,
            "airworthiness_date": None,
            "expiration_date": None,
            "aircraft_category": None,
            "aircraft_category_raw": None,
            "builder_certification": None,
            "builder_certification_raw": None,
            "weight_class": WTC_MAP.get(wtc) if wtc else None,
            "weight_class_raw": wtc,
            "source": SOURCE,
        }


COLUMNS = [
    "icao_hex",
    "registration",
    "serial_number",
    "source_record_id",
    "manufacturer",
    "model",
    "type_aircraft",
    "type_aircraft_raw",
    "type_engine",
    "type_engine_raw",
    "engine_count",
    "seats",
    "year_manufactured",
    "owner_name",
    "owner_type",
    "owner_type_raw",
    "owner_city",
    "owner_state",
    "owner_country",
    "status",
    "status_raw",
    "certification",
    "last_action_date",
    "cert_issue_date",
    "airworthiness_date",
    "expiration_date",
    "aircraft_category",
    "aircraft_category_raw",
    "builder_certification",
    "builder_certification_raw",
    "weight_class",
    "weight_class_raw",
    "source",
]


def ingest(conn, aircrafts_path, types_path):
    types = load_types(types_path)
    inserted = 0
    skipped_dup = 0
    seen = set()

    trust_case = " ".join(
        f"WHEN '{src}' THEN {len(TRUST_ORDER) - i}"
        for i, src in enumerate(TRUST_ORDER)
    )

    with conn.cursor() as cur:
        cur.execute("""
            CREATE TEMP TABLE aircraft_staging (
                LIKE aircraft INCLUDING DEFAULTS
            ) ON COMMIT DROP
        """)

        copy_sql = f"COPY aircraft_staging ({', '.join(COLUMNS)}) FROM STDIN"
        with cur.copy(copy_sql) as copy:
            for record in load_aircrafts(aircrafts_path, types):
                if record["icao_hex"] in seen:
                    skipped_dup += 1
                    continue
                seen.add(record["icao_hex"])
                copy.write_row([record[c] for c in COLUMNS])
                inserted += 1

        upsert_sql = f"""
            INSERT INTO aircraft ({', '.join(COLUMNS)})
            SELECT {', '.join(COLUMNS)} FROM aircraft_staging
            ON CONFLICT (icao_hex) DO UPDATE SET
                registration = COALESCE(aircraft.registration, EXCLUDED.registration),
                model = COALESCE(aircraft.model, EXCLUDED.model),
                type_aircraft_raw = COALESCE(aircraft.type_aircraft_raw, EXCLUDED.type_aircraft_raw),
                weight_class = COALESCE(aircraft.weight_class, EXCLUDED.weight_class),
                weight_class_raw = COALESCE(aircraft.weight_class_raw, EXCLUDED.weight_class_raw),
                source = CASE
                    WHEN aircraft.source = 'Mictronics' THEN EXCLUDED.source
                    ELSE aircraft.source
                END,
                updated_at = NOW()
            WHERE (CASE aircraft.source {trust_case} END)
                  <= (CASE EXCLUDED.source {trust_case} END)
        """
        cur.execute(upsert_sql)
        affected = cur.rowcount

    conn.commit()
    return inserted, skipped_dup, affected


def main():
    load_dotenv(script_dir.parent / ".env")

    aircrafts_path = data_dir / "mictronics_aircrafts.json"
    types_path = data_dir / "mictronics_types.json"

    args = sys.argv[1:]
    if "--refresh" in args:
        aircrafts_path.unlink(missing_ok=True)
        types_path.unlink(missing_ok=True)
        args = [a for a in args if a != "--refresh"]
    if args:
        aircrafts_path = Path(args[0])
        if len(args) > 1:
            types_path = Path(args[1])

    data_dir.mkdir(parents=True, exist_ok=True)
    ensure_files(aircrafts_path, types_path)

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    started = datetime.now()
    with psycopg.connect(database_url) as conn:
        inserted, skipped, affected = ingest(conn, aircrafts_path, types_path)

    elapsed = (datetime.now() - started).total_seconds()
    print(f"Mictronics ingest complete in {elapsed:.1f}s")
    print(f"  type definitions: loaded from types.json")
    print(f"  staged: {inserted}")
    if skipped:
        print(f"  duplicate icao_hex skipped: {skipped}")
    print(f"  inserted or updated: {affected}")


if __name__ == "__main__":
    main()
