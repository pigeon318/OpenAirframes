CREATE TABLE positions (
    id          BIGSERIAL PRIMARY KEY,
    hex         CHAR(6) NOT NULL,
    ts          TIMESTAMPTZ NOT NULL DEFAULT now(),
    lat         DOUBLE PRECISION NOT NULL,
    lon         DOUBLE PRECISION NOT NULL,
    alt_baro    INTEGER,
    gs          REAL,
    track       REAL,
    vert_rate   INTEGER
);

CREATE INDEX positions_hex_ts ON positions (hex, ts DESC);
