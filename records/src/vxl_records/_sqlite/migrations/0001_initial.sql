CREATE TABLE acquisitions (
    id TEXT PRIMARY KEY,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    status TEXT NOT NULL,
    created_at_us INTEGER NOT NULL,
    archived_at_us INTEGER,
    manifest_json TEXT NOT NULL,
    log_start_seq INTEGER,
    log_end_seq INTEGER,
    CHECK (log_start_seq IS NULL OR log_start_seq >= 0),
    CHECK (log_end_seq IS NULL OR log_start_seq IS NOT NULL),
    CHECK (log_end_seq IS NULL OR log_end_seq >= log_start_seq)
) STRICT;

CREATE INDEX acquisitions_active_created
    ON acquisitions(created_at_us DESC)
    WHERE archived_at_us IS NULL;

CREATE INDEX acquisitions_status_created
    ON acquisitions(status, created_at_us DESC)
    WHERE archived_at_us IS NULL;

CREATE TABLE logs (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    emitted_at_us INTEGER NOT NULL,
    recorded_at_us INTEGER NOT NULL,
    level INTEGER NOT NULL CHECK (level >= 0),
    logger TEXT NOT NULL CHECK (length(logger) > 0),
    message TEXT NOT NULL,
    node_id TEXT,
    attributes_json TEXT NOT NULL DEFAULT '{}',
    exception_json TEXT
) STRICT;

CREATE INDEX logs_recorded_at
    ON logs(recorded_at_us);

CREATE INDEX logs_level_seq
    ON logs(level, seq);

CREATE INDEX logs_node_seq
    ON logs(node_id, seq)
    WHERE node_id IS NOT NULL;
