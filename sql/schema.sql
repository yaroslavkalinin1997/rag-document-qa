CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    file_type VARCHAR(10) NOT NULL
        CHECK (file_type IN ('txt', 'docx')),
    full_text TEXT NOT NULL,
    content_sha256 CHAR(64) NOT NULL UNIQUE,
    size_bytes INTEGER NOT NULL
        CHECK (size_bytes > 0),
    status VARCHAR(20) NOT NULL DEFAULT 'ready'
        CHECK (status IN ('processing', 'ready', 'failed')),
    chunk_count INTEGER NOT NULL DEFAULT 0
        CHECK (chunk_count >= 0),
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY,
    document_id UUID NOT NULL
        REFERENCES documents(id)
        ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL
        CHECK (chunk_index >= 0),
    content TEXT NOT NULL
        CHECK (length(btrim(content)) > 0),
    embedding VECTOR(768) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (document_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS rate_limit_counters (
    action VARCHAR(20) NOT NULL
        CHECK (action IN ('ask', 'upload')),
    scope VARCHAR(20) NOT NULL
        CHECK (scope IN ('site_day', 'ip_day', 'ip_minute')),
    client_key VARCHAR(64) NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    request_count INTEGER NOT NULL
        CHECK (request_count > 0),

    PRIMARY KEY (action, scope, client_key, window_start)
);

CREATE INDEX IF NOT EXISTS rate_limit_counters_window_start_idx
    ON rate_limit_counters (window_start);
