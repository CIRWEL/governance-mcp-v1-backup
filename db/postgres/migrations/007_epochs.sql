-- Migration 007: Epoch-Based Data Lifecycle
--
-- Epochs cleanly separate data across breaking model changes.
-- When EISV coupling constants, coherence formulas, or calibration logic change,
-- bump the epoch. Old data stays queryable for history but is excluded from
-- active calculations.
--
-- Most changes (bug fixes, new tools, docs) do NOT bump the epoch.
-- Only changes that make existing stored data wrong require a bump.

-- Add epoch column to tables whose data is invalidated by model changes
ALTER TABLE core.agent_state
    ADD COLUMN IF NOT EXISTS epoch INTEGER NOT NULL DEFAULT 1;

ALTER TABLE core.agent_baselines
    ADD COLUMN IF NOT EXISTS epoch INTEGER NOT NULL DEFAULT 1;

ALTER TABLE knowledge.discoveries
    ADD COLUMN IF NOT EXISTS epoch INTEGER NOT NULL DEFAULT 1;

ALTER TABLE audit.outcome_events
    ADD COLUMN IF NOT EXISTS epoch INTEGER NOT NULL DEFAULT 1;

-- Indexes for epoch filtering
CREATE INDEX IF NOT EXISTS idx_agent_state_epoch
    ON core.agent_state(epoch);

CREATE INDEX IF NOT EXISTS idx_agent_baselines_epoch
    ON core.agent_baselines(epoch);

CREATE INDEX IF NOT EXISTS idx_discoveries_epoch
    ON knowledge.discoveries(epoch);

CREATE INDEX IF NOT EXISTS idx_outcome_events_epoch
    ON audit.outcome_events(epoch);

-- Epoch metadata table: tracks when and why each epoch started
CREATE TABLE IF NOT EXISTS core.epochs (
    epoch       INTEGER PRIMARY KEY,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    reason      TEXT NOT NULL,
    started_by  TEXT  -- agent_id or 'manual'
);

-- Seed epoch 1 as the implicit starting epoch
INSERT INTO core.epochs (epoch, reason, started_by)
VALUES (1, 'initial epoch — all pre-epoch data', 'system')
ON CONFLICT (epoch) DO NOTHING;

INSERT INTO core.schema_migrations (version, name)
VALUES (7, 'epoch_based_data_lifecycle')
ON CONFLICT (version) DO NOTHING;
