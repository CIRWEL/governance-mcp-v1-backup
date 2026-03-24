-- Migration 009: Add quorum voting support to dialectic sessions
-- Enables multi-reviewer voting when dialectic synthesis exceeds max rounds.

-- Add quorum columns
ALTER TABLE core.dialectic_sessions
    ADD COLUMN IF NOT EXISTS quorum_reviewer_ids JSONB,
    ADD COLUMN IF NOT EXISTS quorum_deadline TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS quorum_result JSONB;

-- Extend phase CHECK to include 'quorum_voting'
ALTER TABLE core.dialectic_sessions DROP CONSTRAINT dialectic_sessions_phase_check;
ALTER TABLE core.dialectic_sessions ADD CONSTRAINT dialectic_sessions_phase_check
    CHECK (phase = ANY (ARRAY[
        'awaiting_thesis', 'thesis', 'antithesis', 'synthesis',
        'resolved', 'escalated', 'failed', 'quorum_voting'
    ]));

-- Extend status CHECK to include 'quorum_voting'
ALTER TABLE core.dialectic_sessions DROP CONSTRAINT dialectic_sessions_status_check;
ALTER TABLE core.dialectic_sessions ADD CONSTRAINT dialectic_sessions_status_check
    CHECK (status = ANY (ARRAY[
        'active', 'resolved', 'escalated', 'failed', 'quorum_voting'
    ]));

-- Migration metadata
INSERT INTO core.schema_migrations (version, name, applied_at)
VALUES (9, 'quorum_support', NOW())
ON CONFLICT (version) DO NOTHING;
