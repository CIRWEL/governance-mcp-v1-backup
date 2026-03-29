-- Add trigger_source to dialectic_sessions for provenance tracking
-- Values: "manual", "circuit_breaker", "loop_detection", "drift_detection"
ALTER TABLE core.dialectic_sessions ADD COLUMN IF NOT EXISTS trigger_source TEXT;
