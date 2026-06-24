import csv
import os
import sys
from datetime import datetime
from pathlib import Path

import psycopg
from dotenv import load_dotenv

script_dir = Path(__file__).parent
data_dir = script_dir.parent / "data"
SOURCE = "UK_CAA"
TRUST_ORDER = ["FAA", "UK_CAA", "Mictronics", "OpenSky", "user"]


def parse_date(s):
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_int(s):
    s = (s or "").strip()
    try:
        return int(s)
    except (ValueError, TypeError):
        return None


def clean(d, key):
    return d.get(key, "").strip() or None


def load_register(path):
    with open(path, encoding="latin-1") as f:
        reader = csv.DictReader(f)
        headers = {h.strip(): h for h in (reader.fieldnames or [])}

        def get(row, name):
            real_key = headers.get(name)
            if real_key is None:
                return None
            return row.get(real_key, "").strip() or None

        for row in reader:
            icao_raw = get(row, "ICAO 24 bit address")
            if not icao_raw:
                continue
            icao_hex = icao_raw.strip().lower()
            if len(icao_hex) != 6 or not all(c in "0123456789abcdef" for c in icao_hex):
                continue

            mark = get(row, "Mark")
            registration = mark if mark else None

            addr_parts = [
                get(row, "Registered Address (1)"),
                get(row, "Registered Address (2)"),
                get(row, "Registered Address (3)"),
                get(row, "Registered Address (4)"),
                get(row, "Registered Address (5)"),
            ]
            addr_parts = [p for p in addr_parts if p]

            owner_city = addr_parts[-3] if len(addr_parts) >= 3 else (addr_parts[0] if addr_parts else None)
            owner_country = addr_parts[-1] if len(addr_parts) >= 2 else None

            cofa_permit = get(row, "CofA/Permit")
            if cofa_permit:
                cofa_permit = cofa_permit.replace("C of A", "Certificate of Airworthiness")

            yield {
                "icao_hex": icao_hex,
                "registration": registration,
                "serial_number": get(row, "Serial Number"),
                "source_record_id": get(row, "Certificate Number"),
                "manufacturer": get(row, "Manufacturer Name"),
                "model": get(row, "Manufacturer Designation"),
                "type_aircraft": None,
                "type_aircraft_raw": get(row, "Type Code"),
                "type_engine": None,
                "type_engine_raw": None,
                "engine_count": None,
                "seats": None,
                "year_manufactured": None,
                "owner_name": get(row, "Registered Owner"),
                "owner_type": None,
                "owner_type_raw": None,
                "owner_city": owner_city,
                "owner_state": None,
                "owner_country": owner_country,
                "status": "Valid",
                "status_raw": None,
                "certification": cofa_permit,
                "last_action_date": None,
                "cert_issue_date": parse_date(get(row, "Date of CofA/Permit Issue")),
                "airworthiness_date": parse_date(get(row, "Date of CofA/Permit Issue")),
                "expiration_date": parse_date(get(row, "Date of CofA/Permit Expiry")),
                "aircraft_category": None,
                "aircraft_category_raw": None,
                "builder_certification": None,
                "builder_certification_raw": None,
                "weight_class": None,
                "weight_class_raw": None,
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


def ingest(conn, path):
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
            for record in load_register(path):
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
                registration = EXCLUDED.registration,
                serial_number = EXCLUDED.serial_number,
                source_record_id = EXCLUDED.source_record_id,
                manufacturer = EXCLUDED.manufacturer,
                model = EXCLUDED.model,
                type_aircraft = COALESCE(EXCLUDED.type_aircraft, aircraft.type_aircraft),
                type_aircraft_raw = EXCLUDED.type_aircraft_raw,
                type_engine = COALESCE(EXCLUDED.type_engine, aircraft.type_engine),
                type_engine_raw = EXCLUDED.type_engine_raw,
                engine_count = COALESCE(EXCLUDED.engine_count, aircraft.engine_count),
                seats = COALESCE(EXCLUDED.seats, aircraft.seats),
                year_manufactured = COALESCE(EXCLUDED.year_manufactured, aircraft.year_manufactured),
                owner_name = EXCLUDED.owner_name,
                owner_type = EXCLUDED.owner_type,
                owner_type_raw = EXCLUDED.owner_type_raw,
                owner_city = EXCLUDED.owner_city,
                owner_state = EXCLUDED.owner_state,
                owner_country = EXCLUDED.owner_country,
                status = EXCLUDED.status,
                status_raw = EXCLUDED.status_raw,
                certification = EXCLUDED.certification,
                last_action_date = EXCLUDED.last_action_date,
                cert_issue_date = EXCLUDED.cert_issue_date,
                airworthiness_date = EXCLUDED.airworthiness_date,
                expiration_date = EXCLUDED.expiration_date,
                aircraft_category = COALESCE(EXCLUDED.aircraft_category, aircraft.aircraft_category),
                aircraft_category_raw = EXCLUDED.aircraft_category_raw,
                builder_certification = COALESCE(EXCLUDED.builder_certification, aircraft.builder_certification),
                builder_certification_raw = EXCLUDED.builder_certification_raw,
                weight_class = COALESCE(EXCLUDED.weight_class, aircraft.weight_class),
                weight_class_raw = EXCLUDED.weight_class_raw,
                source = EXCLUDED.source,
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
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    csv_path = data_dir / "CAA_REGISTER.csv"
    if len(sys.argv) > 1:
        csv_path = Path(sys.argv[1])

    if not csv_path.exists():
        print(f"Register file not found: {csv_path}", file=sys.stderr)
        print("Download from: https://www.caa.co.uk/data-and-analysis/aircraft/aircraft-register/", file=sys.stderr)
        sys.exit(1)

    started = datetime.now()
    with psycopg.connect(database_url) as conn:
        inserted, skipped, affected = ingest(conn, csv_path)

    elapsed = (datetime.now() - started).total_seconds()
    print(f"UK CAA ingest complete in {elapsed:.1f}s")
    print(f"  staged: {inserted}")
    if skipped:
        print(f"  duplicate icao_hex skipped: {skipped}")
    print(f"  inserted or updated: {affected}")


if __name__ == "__main__":
    main()
