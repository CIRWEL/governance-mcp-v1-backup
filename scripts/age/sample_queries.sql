-- Sample Apache AGE queries for the governance knowledge graph.
-- Assumes you've run scripts/age/bootstrap.sql and imported data into graph 'governance'.

LOAD 'age';
SET search_path = ag_catalog, "$user", public;

-- 1) Count nodes
SELECT * FROM cypher('governance', $$
  MATCH (d:Discovery)
  RETURN count(d) AS discoveries
$$) AS (discoveries agtype);

-- 1b) Count agents + dialectic sessions (if exported)
SELECT * FROM cypher('governance', $$
  MATCH (a:Agent)
  RETURN count(a) AS agents
$$) AS (agents agtype);

SELECT * FROM cypher('governance', $$
  MATCH (s:DialecticSession)
  RETURN count(s) AS dialectic_sessions
$$) AS (dialectic_sessions agtype);

-- 2) Multi-hop related traversal (1..3 hops)
-- Replace $DISCOVERY_ID with a real discovery id (ISO timestamp string).
-- Example: 2025-12-12T23:17:25.582919
SELECT * FROM cypher('governance', $$
  MATCH path = (d:Discovery {id: '$DISCOVERY_ID'})-[:RELATED_TO*1..3]->(r:Discovery)
  RETURN r.id, length(path) AS depth
  ORDER BY depth
  LIMIT 25
$$) AS (r_id agtype, depth agtype);

-- 3) Response thread expansion (variable depth)
SELECT * FROM cypher('governance', $$
  MATCH path = (root:Discovery {id: '$DISCOVERY_ID'})<-[:RESPONSE_TO*0..5]-(reply:Discovery)
  RETURN reply.id, length(path) AS depth
  ORDER BY depth
  LIMIT 50
$$) AS (reply_id agtype, depth agtype);

-- 4) Agent lineage: ancestry chain (variable depth)
-- Replace $AGENT_ID with a real agent id, e.g. cursor-opus-exploration-20251213
SELECT * FROM cypher('governance', $$
  MATCH path = (root:Agent)-[:SPAWNED*0..10]->(a:Agent {id: '$AGENT_ID'})
  RETURN length(path) AS depth
  ORDER BY depth DESC
  LIMIT 1
$$) AS (depth agtype);

-- 5) Dialectic sessions involving an agent (paused agent or reviewer)
SELECT * FROM cypher('governance', $$
  MATCH (a:Agent {id: '$AGENT_ID'})<-[:PAUSED_AGENT|:REVIEWER]-(s:DialecticSession)
  RETURN s.id, s.status, s.phase, s.created_at
  ORDER BY s.created_at DESC
  LIMIT 20
$$) AS (session_id agtype, status agtype, phase agtype, created_at agtype);

-- 6) Dialectic message thread for a session
-- Replace $SESSION_ID with a real dialectic session id.
SELECT * FROM cypher('governance', $$
  MATCH (s:DialecticSession {id: '$SESSION_ID'})-[:HAS_MESSAGE]->(m:DialecticMessage)
  RETURN m.seq, m.message_type, m.agent_id, m.timestamp
  ORDER BY m.seq ASC
$$) AS (seq agtype, message_type agtype, agent_id agtype, timestamp agtype);

