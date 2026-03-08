-------------------------------------------------------------------------------
-- Threat Intelligence Correlation Platform — PostgreSQL Schema
-- Initialised automatically on first container start.
-------------------------------------------------------------------------------

-- Enable useful extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";     -- fuzzy text search

-------------------------------------------------------------------------------
-- 1. Core report table
-------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS threat_reports (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    opencti_id      TEXT UNIQUE,                       -- STIX ID from OpenCTI
    title           TEXT NOT NULL,
    description     TEXT,                              -- raw description / body
    summary         TEXT,                              -- AI-generated summary
    report_type     TEXT,                              -- e.g. threat-report, malware-analysis
    source          TEXT,                              -- e.g. MalwareBazaar, Telegram, RSS
    source_url      TEXT,
    confidence      INTEGER DEFAULT 0,                 -- 0-100
    severity        TEXT,                              -- critical / high / medium / low / info
    tlp             TEXT DEFAULT 'TLP:CLEAR',          -- Traffic Light Protocol
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    published_at    TIMESTAMPTZ,
    ingested_at     TIMESTAMPTZ DEFAULT NOW(),
    raw_json        JSONB                              -- full OpenCTI object for reference
);

CREATE INDEX idx_reports_source      ON threat_reports (source);
CREATE INDEX idx_reports_published   ON threat_reports (published_at DESC);
CREATE INDEX idx_reports_severity    ON threat_reports (severity);
CREATE INDEX idx_reports_title_trgm  ON threat_reports USING gin (title gin_trgm_ops);

-------------------------------------------------------------------------------
-- 2. Extracted entities (IOCs, TTPs, threat actors, malware families, etc.)
-------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS entities (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_type     TEXT NOT NULL,            -- threat-actor, malware, vulnerability, indicator, attack-pattern, tool, campaign
    name            TEXT NOT NULL,
    stix_id         TEXT,
    description     TEXT,
    first_seen      TIMESTAMPTZ,
    last_seen       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_entities_type_name ON entities (entity_type, name);
CREATE INDEX idx_entities_stix ON entities (stix_id);

-------------------------------------------------------------------------------
-- 3. Many-to-many: which entities appear in which reports
-------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS report_entities (
    report_id       UUID REFERENCES threat_reports(id) ON DELETE CASCADE,
    entity_id       UUID REFERENCES entities(id) ON DELETE CASCADE,
    relationship    TEXT DEFAULT 'mentions',   -- mentions, targets, uses, attributed-to
    confidence      INTEGER DEFAULT 50,
    extracted_by    TEXT DEFAULT 'ai',         -- ai | opencti | manual
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (report_id, entity_id, relationship)
);

-------------------------------------------------------------------------------
-- 4. AI-extracted tags / topics for trend analysis
-------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS report_tags (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    report_id       UUID REFERENCES threat_reports(id) ON DELETE CASCADE,
    tag             TEXT NOT NULL,
    category        TEXT,                      -- tactic, technique, sector, region, campaign
    weight          REAL DEFAULT 1.0,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_tags_tag       ON report_tags (tag);
CREATE INDEX idx_tags_category  ON report_tags (category);

-------------------------------------------------------------------------------
-- 5. Correlation scores between reports (populated by analysis pipeline)
-------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS report_correlations (
    report_a        UUID REFERENCES threat_reports(id) ON DELETE CASCADE,
    report_b        UUID REFERENCES threat_reports(id) ON DELETE CASCADE,
    score           REAL NOT NULL,             -- 0.0-1.0 similarity / correlation
    method          TEXT,                      -- cosine, entity-overlap, ai-judgement
    details         JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (report_a, report_b)
);

-------------------------------------------------------------------------------
-- 6. Trend snapshots (periodic aggregation for dashboards)
-------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS trend_snapshots (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    snapshot_date   DATE NOT NULL,
    window_days     INTEGER NOT NULL DEFAULT 7,   -- 1=daily, 7=weekly, 30=monthly
    trend_type      TEXT NOT NULL,                 -- entity, tag, severity, source
    trend_key       TEXT NOT NULL,                 -- e.g. "ransomware", "CVE-2025-xxxx"
    count           INTEGER DEFAULT 0,
    pct_change      REAL,                          -- vs previous window
    details         JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_trends_date ON trend_snapshots (snapshot_date DESC);
CREATE INDEX idx_trends_key  ON trend_snapshots (trend_key);

-------------------------------------------------------------------------------
-- 7. Telegram channel tracking
-------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS telegram_channels (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    channel_name    TEXT NOT NULL UNIQUE,
    channel_id      BIGINT,
    category        TEXT,                      -- threat-actor, marketplace, leak, news
    language        TEXT DEFAULT 'en',
    active          BOOLEAN DEFAULT TRUE,
    last_fetched    TIMESTAMPTZ,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-------------------------------------------------------------------------------
-- Useful views
-------------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_report_entity_summary AS
SELECT
    tr.id AS report_id,
    tr.title,
    tr.source,
    tr.severity,
    tr.published_at,
    e.entity_type,
    e.name AS entity_name,
    re.relationship
FROM threat_reports tr
JOIN report_entities re ON tr.id = re.report_id
JOIN entities e ON re.entity_id = e.id
ORDER BY tr.published_at DESC;

CREATE OR REPLACE VIEW v_trending_entities AS
SELECT
    e.entity_type,
    e.name,
    COUNT(DISTINCT re.report_id) AS report_count,
    MAX(tr.published_at) AS last_seen,
    MIN(tr.published_at) AS first_seen
FROM entities e
JOIN report_entities re ON e.id = re.entity_id
JOIN threat_reports tr ON re.report_id = tr.id
WHERE tr.published_at >= NOW() - INTERVAL '30 days'
GROUP BY e.entity_type, e.name
ORDER BY report_count DESC;