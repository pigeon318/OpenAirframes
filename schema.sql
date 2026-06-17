CREATE TABLE aircraft (
    icao_hex          TEXT PRIMARY KEY
                      CHECK (icao_hex ~ '^[0-9a-f]{6}$'),
    registration      TEXT,
    serial_number     TEXT,
    source_record_id  TEXT,

    manufacturer            TEXT,
    model                   TEXT,
    type_aircraft           TEXT,
    type_aircraft_raw       TEXT,
    type_engine             TEXT,
    type_engine_raw         TEXT,
    engine_count            INTEGER,
    seats                   INTEGER,
    year_manufactured       INTEGER,

    owner_name      TEXT,
    owner_type      TEXT,
    owner_type_raw  TEXT,
    owner_city      TEXT,
    owner_state     TEXT,
    owner_country   TEXT,

    status                 TEXT,
    status_raw             TEXT,
    certification          TEXT,
    last_action_date       DATE,
    cert_issue_date        DATE,
    airworthiness_date     DATE,
    expiration_date        DATE,

    source        TEXT NOT NULL
                  CHECK (source IN ('FAA', 'UK_CAA', 'Mictronics', 'OpenSky', 'user')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_aircraft_registration  ON aircraft (registration);
CREATE INDEX idx_aircraft_manufacturer  ON aircraft (manufacturer);
CREATE INDEX idx_aircraft_model         ON aircraft (model);
CREATE INDEX idx_aircraft_owner_name    ON aircraft (owner_name);
