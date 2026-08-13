CREATE TABLE presets (
    id TEXT PRIMARY KEY,
    instrument TEXT NOT NULL CHECK (length(instrument) > 0),
    name TEXT NOT NULL CHECK (length(name) > 0),
    created_at_us INTEGER NOT NULL,
    preset_json TEXT NOT NULL,
    UNIQUE (instrument, name)
) STRICT;

CREATE INDEX presets_instrument_created
    ON presets(instrument, created_at_us DESC);
