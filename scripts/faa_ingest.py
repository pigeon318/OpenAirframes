import csv
import os
import sys
from collections import Counter
from datetime import datetime
from itertools import islice
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from faa_mappings import (
    AIRCRAFT_CATEGORY,
    BUILDER_CERTIFICATION,
    STATUS,
    TYPE_AIRCRAFT,
    TYPE_ENGINE,
    TYPE_REGISTRANT,
    WEIGHT_CLASS,
    decode,
)

script_dir = Path(__file__).parent
data_dir = script_dir.parent / "data"
SOURCE = "FAA"
TRUST_ORDER = ["FAA", "UK_CAA", "Mictronics", "OpenSky", "user"]


def load_acftref():
    result = {}
    with open(data_dir / "ACFTREF.txt", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = row["CODE"].strip()
            result[code] = {
                "manufacturer": row["MFR"].strip(),
                "model": row["MODEL"].strip(),
                "type_aircraft": row["TYPE-ACFT"].strip(),
                "type_engine": row["TYPE-ENG"].strip(),
                "aircraft_category": row["AC-CAT"].strip(),
                "builder_certification": row["BUILD-CERT-IND"].strip(),
                "engine_count": row["NO-ENG"].strip(),
                "seats": row["NO-SEATS"].strip(),
                "weight_class": row["AC-WEIGHT"].strip(),
            }
    return result


def parse_int(s):
    s = (s or "").strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def parse_date(s):
    s = (s or "").strip()
    if not s or len(s) != 8:
        return None
    try:
        return datetime.strptime(s, "%Y%m%d").date()
    except ValueError:
        return None


def load_master(acftref, unknown):
    with open(data_dir / "MASTER.txt", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            icao_hex = row["MODE S CODE HEX"].strip().lower()
            if not icao_hex or len(icao_hex) != 6:
                continue

            n_number = row["N-NUMBER"].strip()
            registration = f"N{n_number}" if n_number else None

            mfr_code = row["MFR MDL CODE"].strip()
            ref = acftref.get(mfr_code, {})

            ta_raw = row["TYPE AIRCRAFT"].strip()
            te_raw = row["TYPE ENGINE"].strip()
            tr_raw = row["TYPE REGISTRANT"].strip()
            st_raw = row["STATUS CODE"].strip()
            ac_raw = ref.get("aircraft_category", "")
            bc_raw = ref.get("builder_certification", "")
            wc_raw = ref.get("weight_class", "")

            type_aircraft = decode(TYPE_AIRCRAFT, ta_raw)
            type_engine = decode(TYPE_ENGINE, te_raw)
            owner_type = decode(TYPE_REGISTRANT, tr_raw)
            status = decode(STATUS, st_raw)
            aircraft_category = decode(AIRCRAFT_CATEGORY, ac_raw)
            builder_certification = decode(BUILDER_CERTIFICATION, bc_raw)
            weight_class = decode(WEIGHT_CLASS, wc_raw)

            if ta_raw and type_aircraft is None:
                unknown["type_aircraft"][ta_raw] += 1
                type_aircraft = "unknown"
            if te_raw and type_engine is None:
                unknown["type_engine"][te_raw] += 1
                type_engine = "unknown"
            if tr_raw and owner_type is None:
                unknown["owner_type"][tr_raw] += 1
                owner_type = "unknown"
            if st_raw and status is None:
                unknown["status"][st_raw] += 1
                status = "unknown"
            if ac_raw and aircraft_category is None:
                unknown["aircraft_category"][ac_raw] += 1
                aircraft_category = "unknown"
            if bc_raw and builder_certification is None:
                unknown["builder_certification"][bc_raw] += 1
                builder_certification = "unknown"
            if wc_raw and weight_class is None:
                unknown["weight_class"][wc_raw] += 1
                weight_class = "unknown"

            yield {
                "icao_hex": icao_hex,
                "registration": registration,
                "serial_number": row["SERIAL NUMBER"].strip() or None,
                "source_record_id": row["UNIQUE ID"].strip() or None,
                "manufacturer": ref.get("manufacturer") or None,
                "model": ref.get("model") or None,
                "type_aircraft": type_aircraft,
                "type_aircraft_raw": ta_raw or None,
                "type_engine": type_engine,
                "type_engine_raw": te_raw or None,
                "engine_count": parse_int(ref.get("engine_count")),
                "seats": parse_int(ref.get("seats")),
                "year_manufactured": parse_int(row["YEAR MFR"]),
                "owner_name": row["NAME"].strip() or None,
                "owner_type": owner_type,
                "owner_type_raw": tr_raw or None,
                "owner_city": row["CITY"].strip() or None,
                "owner_state": row["STATE"].strip() or None,
                "owner_country": row["COUNTRY"].strip() or None,
                "status": status,
                "status_raw": st_raw or None,
                "certification": row["CERTIFICATION"].strip() or None,
                "last_action_date": parse_date(row["LAST ACTION DATE"]),
                "cert_issue_date": parse_date(row["CERT ISSUE DATE"]),
                "airworthiness_date": parse_date(row["AIR WORTH DATE"]),
                "expiration_date": parse_date(row["EXPIRATION DATE"]),
                "aircraft_category": aircraft_category,
                "aircraft_category_raw": ac_raw or None,
                "builder_certification": builder_certification,
                "builder_certification_raw": bc_raw or None,
                "weight_class": weight_class,
                "weight_class_raw": wc_raw or None,
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


def ingest(conn, acftref, unknown):
    inserted = 0
    skipped_dup_in_batch = 0
    seen = set()

    with conn.cursor() as cur:
        cur.execute("""
            CREATE TEMP TABLE aircraft_staging (
                LIKE aircraft INCLUDING DEFAULTS
            ) ON COMMIT DROP
        """)

        copy_sql = f"COPY aircraft_staging ({', '.join(COLUMNS)}) FROM STDIN"
        with cur.copy(copy_sql) as copy:
            for record in load_master(acftref, unknown):
                if record["icao_hex"] in seen:
                    skipped_dup_in_batch += 1
                    continue
                seen.add(record["icao_hex"])
                copy.write_row([record[c] for c in COLUMNS])
                inserted += 1

        trust_case = " ".join(
            f"WHEN '{src}' THEN {len(TRUST_ORDER) - i}"
            for i, src in enumerate(TRUST_ORDER)
        )

        upsert_sql = f"""
            INSERT INTO aircraft ({', '.join(COLUMNS)})
            SELECT {', '.join(COLUMNS)} FROM aircraft_staging
            ON CONFLICT (icao_hex) DO UPDATE SET
                registration = EXCLUDED.registration,
                serial_number = EXCLUDED.serial_number,
                source_record_id = EXCLUDED.source_record_id,
                manufacturer = EXCLUDED.manufacturer,
                model = EXCLUDED.model,
                type_aircraft = EXCLUDED.type_aircraft,
                type_aircraft_raw = EXCLUDED.type_aircraft_raw,
                type_engine = EXCLUDED.type_engine,
                type_engine_raw = EXCLUDED.type_engine_raw,
                engine_count = EXCLUDED.engine_count,
                seats = EXCLUDED.seats,
                year_manufactured = EXCLUDED.year_manufactured,
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
                aircraft_category = EXCLUDED.aircraft_category,
                aircraft_category_raw = EXCLUDED.aircraft_category_raw,
                builder_certification = EXCLUDED.builder_certification,
                builder_certification_raw = EXCLUDED.builder_certification_raw,
                weight_class = EXCLUDED.weight_class,
                weight_class_raw = EXCLUDED.weight_class_raw,
                source = EXCLUDED.source,
                updated_at = NOW()
            WHERE (CASE aircraft.source {trust_case} END)
                  <= (CASE EXCLUDED.source {trust_case} END)
        """
        cur.execute(upsert_sql)
        affected = cur.rowcount

    conn.commit()
    return inserted, skipped_dup_in_batch, affected


def main():
    load_dotenv(script_dir.parent / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    started = datetime.now()
    acftref = load_acftref()

    unknown = {
        "type_aircraft": Counter(),
        "type_engine": Counter(),
        "owner_type": Counter(),
        "status": Counter(),
        "aircraft_category": Counter(),
        "builder_certification": Counter(),
        "weight_class": Counter(),
    }

    with psycopg.connect(database_url) as conn:
        inserted, skipped, affected = ingest(conn, acftref, unknown)

    elapsed = (datetime.now() - started).total_seconds()
    print(f"FAA ingest complete in {elapsed:.1f}s")
    print(f"  reference entries: {len(acftref)}")
    print(f"  staged: {inserted}")
    if skipped:
        print(f"  duplicate icao_hex skipped: {skipped}")
    print(f"  inserted or updated: {affected}")

    any_unknown = any(c for c in unknown.values())
    if any_unknown:
        print()
        print("Unknown enum values encountered:")
        for field, counter in unknown.items():
            if not counter:
                continue
            print(f"  {field}:")
            for value, count in counter.most_common():
                print(f"    {value!r}: {count}")


if __name__ == "__main__":
    main()
