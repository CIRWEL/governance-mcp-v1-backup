"""
Knowledge Graph MCP Handlers

Fast, indexed, non-blocking knowledge operations using knowledge graph.
Replaces deprecated file-based knowledge layer.

Performance:
- store_knowledge: ~0.01ms (vs 350ms file-based) - 35,000x faster
- search_knowledge: O(indexes) not O(n) - scales logarithmically
- find_similar: Tag-based overlap - no brute force scanning

Claude Desktop compatible: All operations are async and non-blocking.
"""

from typing import Dict, Any, Sequence, Optional
from mcp.types import TextContent
from datetime import datetime
import time
from .utils import success_response, error_response, require_argument, require_agent_id, require_registered_agent
from .decorators import mcp_tool
from .validators import validate_discovery_type, validate_severity, validate_discovery_status, validate_response_type, validate_discovery_id
from src.knowledge_graph import get_knowledge_graph, DiscoveryNode, ResponseTo
from config.governance_config import config
from src.logging_utils import get_logger
from src.perf_monitor import record_ms

logger = get_logger(__name__)


@mcp_tool("store_knowledge_graph", timeout=20.0)
async def handle_store_knowledge_graph(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Store knowledge discovery/discoveries in graph - fast, non-blocking, transparent
    
    Accepts either:
    - Single discovery: discovery_type, summary, details, tags, etc.
    - Batch discoveries: discoveries array (max 10 per batch)
    """
    # SECURITY FIX: Verify agent_id is registered (prevents phantom agent_ids)
    agent_id, error = require_registered_agent(arguments)
    if error:
        return [error]
    
    # Check if batch mode (discoveries array provided)
    if "discoveries" in arguments and arguments["discoveries"] is not None:
        # Batch mode - delegate to batch handler logic
        return await _handle_store_knowledge_graph_batch(arguments, agent_id)
    
    # Single discovery mode (original behavior)
    # LITE-FIRST: discovery_type defaults to "note" (simplest form)
    discovery_type = arguments.get("discovery_type", "note")
    
    # Validate discovery_type enum
    discovery_type, error = validate_discovery_type(discovery_type)
    if error:
        return [error]
    
    summary, error = require_argument(arguments, "summary",
                                    "summary is required - what did you discover/learn?")
    if error:
        return [error]
    
    try:
        # SECURITY: Rate limiting is handled by the knowledge graph backend
        # JSON backend uses efficient timestamp tracking (O(1) per store)
        # SQLite backend uses dedicated rate_limits table (O(1) per store)
        # No need for inefficient O(n) query here - let graph handle it
        graph = await get_knowledge_graph()
        
        # Truncate fields to prevent context overflow
        MAX_SUMMARY_LEN = 300
        MAX_DETAILS_LEN = 500
        
        raw_summary = summary
        raw_details = arguments.get("details", "")
        
        if len(raw_summary) > MAX_SUMMARY_LEN:
            summary = raw_summary[:MAX_SUMMARY_LEN] + "..."
        
        if len(raw_details) > MAX_DETAILS_LEN:
            raw_details = raw_details[:MAX_DETAILS_LEN] + "... [truncated]"
        
        # Create discovery node
        discovery_id = datetime.now().isoformat()
        
        # Parse response_to if provided (typed response to parent discovery)
        response_to = None
        if "response_to" in arguments and arguments["response_to"]:
            resp_data = arguments["response_to"]
            if isinstance(resp_data, dict) and "discovery_id" in resp_data and "response_type" in resp_data:
                # Validate discovery_id format
                parent_id, error = validate_discovery_id(resp_data["discovery_id"])
                if error:
                    return [error]
                
                # Validate response_type enum
                response_type, error = validate_response_type(resp_data["response_type"])
                if error:
                    return [error]
                
                from src.knowledge_graph import ResponseTo
                response_to = ResponseTo(
                    discovery_id=parent_id,
                    response_type=response_type
                )
        
        # Validate severity if provided
        severity = arguments.get("severity")
        if severity is not None:
            severity, error = validate_severity(severity)
            if error:
                return [error]
        
        # ENHANCED PROVENANCE: Capture agent state at creation time
        # Answers: "What was the agent's context when they made this discovery?"
        provenance = None
        provenance_chain = None
        try:
            from .shared import get_mcp_server
            from .identity import _get_lineage  # Import lineage function

            mcp_server = get_mcp_server()
            if agent_id in mcp_server.agent_metadata:
                meta = mcp_server.agent_metadata[agent_id]

                # Get monitor state if available
                monitor_state = {}
                if agent_id in mcp_server.monitors:
                    monitor = mcp_server.monitors[agent_id]
                    state = monitor.state
                    monitor_state = {
                        "regime": state.regime,
                        "coherence": round(state.coherence, 3),
                        "energy": round(state.E, 3),  # E, I, S, V are uppercase
                        "entropy": round(state.S, 3),
                        "void_active": state.void_active,
                    }

                # CAPTURE BASIC PROVENANCE
                provenance = {
                    "agent_state": {
                        "status": meta.status,
                        "health": meta.health_status,
                        "total_updates": meta.total_updates,
                        **monitor_state
                    },
                    "captured_at": datetime.now().isoformat(),
                }

                # CAPTURE PROVENANCE CHAIN: Full lineage context
                try:
                    lineage = _get_lineage(agent_id)  # [oldest_ancestor, ..., parent, self]
                    if len(lineage) > 1:  # Has ancestors
                        provenance_chain = []
                        for ancestor_id in lineage[:-1]:  # Exclude self
                            ancestor_meta = mcp_server.agent_metadata.get(ancestor_id)
                            if ancestor_meta:
                                chain_entry = {
                                    "agent_id": ancestor_id,
                                    "relationship": "ancestor",
                                    "spawn_reason": ancestor_meta.spawn_reason,
                                    "created_at": ancestor_meta.created_at,
                                    "lineage_depth": len(provenance_chain)  # Distance from root
                                }
                                provenance_chain.append(chain_entry)

                        # Add immediate parent context
                        if meta.parent_agent_id:
                            parent_meta = mcp_server.agent_metadata.get(meta.parent_agent_id)
                            if parent_meta:
                                parent_entry = {
                                    "agent_id": meta.parent_agent_id,
                                    "relationship": "direct_parent",
                                    "spawn_reason": meta.spawn_reason,
                                    "created_at": parent_meta.created_at,
                                    "lineage_depth": len(provenance_chain)
                                }
                                provenance_chain.append(parent_entry)
                except Exception as lineage_error:
                    logger.debug(f"Could not capture provenance chain: {lineage_error}")
                    # Non-critical - continue without chain
        except Exception as e:
            logger.debug(f"Could not capture provenance: {e}")  # Non-critical
        
        discovery = DiscoveryNode(
            id=discovery_id,
            agent_id=agent_id,
            type=discovery_type,
            summary=summary,
            details=raw_details,
            tags=arguments.get("tags", []),
            severity=severity,
            response_to=response_to,
            references_files=arguments.get("related_files", []),
            provenance=provenance
        )
        
        # Find similar discoveries (fast with tag index) - DEFAULT: true for better linking
        similar_discoveries = []
        if arguments.get("auto_link_related", True):  # Default to true - new graph uses indexes (fast)
            similar = await graph.find_similar(discovery, limit=5)
            discovery.related_to = [s.id for s in similar]
            similar_discoveries = [s.to_dict(include_details=False) for s in similar]
        
        # SECURITY: Require API key authentication for high-severity discoveries
        # This prevents unauthorized agents from storing critical security issues
        if discovery.severity in ["high", "critical"]:
            # Use centralized fallback chain (explicit → session → metadata → SQLite)
            from .utils import get_api_key_with_fallback
            api_key = get_api_key_with_fallback(agent_id, arguments)
            
            if not api_key:
                return [error_response(
                    "API key required for high-severity discoveries. "
                    "High-severity discoveries require authentication to prevent knowledge graph poisoning.",
                    recovery={
                        "action": "Provide api_key parameter or bind your identity",
                        "related_tools": ["get_agent_api_key", "bind_identity"],
                        "workflow": [
                            "Option 1: Get API key via get_agent_api_key and include in store_knowledge_graph call",
                            "Option 2: Call bind_identity(agent_id, api_key) once, then API key auto-retrieved from session",
                            "Tip: After bind_identity, you won't need to pass api_key explicitly"
                        ]
                    }
                )]
            
            # Verify API key matches agent_id
            import src.mcp_server_std as mcp_server
            agent_meta = mcp_server.agent_metadata.get(agent_id)
            if not agent_meta or agent_meta.api_key != api_key:
                return [error_response(
                    "Invalid API key for high-severity discovery. "
                    "API key must match the agent_id.",
                    recovery={
                        "action": "Verify your API key matches your agent_id",
                        "related_tools": ["get_agent_api_key"],
                        "workflow": "1. Get correct API key for your agent_id 2. Retry with correct key"
                    }
                )]
        
        # HUMAN REVIEW FLAGGING: Flag high-severity discoveries for review
        requires_review = discovery.severity in ["high", "critical"]
        
        # Add to graph (fast, non-blocking)
        await graph.add_discovery(discovery)
        
        response = {
            "message": f"Discovery stored for agent '{agent_id}'",
            "discovery_id": discovery_id,
            "discovery": discovery.to_dict(include_details=False)  # Summary only in response
        }
        
        # Add human review flag if needed
        if requires_review:
            response["human_review_required"] = True
            response["review_message"] = f"High-severity discovery ({discovery.severity}) - please review for accuracy and safety"
        
        if similar_discoveries:
            response["related_discoveries"] = similar_discoveries
        
        return success_response(response)
        
    except ValueError as e:
        # Handle rate limiting errors from graph backend (efficient O(1) check)
        error_msg = str(e)
        if "rate limit" in error_msg.lower() or "Rate limit" in error_msg:
            return [error_response(
                error_msg,
                recovery={
                    "action": "Wait before storing more discoveries, or reduce batch size",
                    "related_tools": ["search_knowledge_graph"]
                }
            )]
        # Other ValueError (validation errors, etc.)
        return [error_response(error_msg)]
    except Exception as e:
        return [error_response(f"Failed to store knowledge: {str(e)}")]


@mcp_tool("search_knowledge_graph", timeout=15.0, rate_limit_exempt=True)
async def handle_search_knowledge_graph(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Search knowledge graph (indexed filters; optional FTS query when SQLite backend is active).
    
    Use include_provenance=True to get provenance and lineage chain for each discovery.
    """
    try:
        graph = await get_knowledge_graph()

        limit = arguments.get("limit", config.KNOWLEDGE_QUERY_DEFAULT_LIMIT)
        include_details = arguments.get("include_details", False)
        include_provenance = arguments.get("include_provenance", False)  # Merged from query_provenance

        # Optional full-text query (SQLite FTS5 if available; bounded substring scan fallback for JSON backend)
        query_text = arguments.get("query")
        agent_id = arguments.get("agent_id")
        tags = arguments.get("tags")
        dtype = arguments.get("discovery_type")
        severity = arguments.get("severity")
        status = arguments.get("status")

        # Track semantic scores if semantic search is used
        semantic_scores_dict = {}
        
        t0 = time.perf_counter()
        if query_text:
            # Check if semantic search is requested and available
            use_semantic = arguments.get("semantic", False) and hasattr(graph, "semantic_search")
            
            if use_semantic:
                # Semantic search using vector embeddings
                min_similarity = arguments.get("min_similarity", 0.3)
                semantic_results = await graph.semantic_search(
                    str(query_text),
                    limit=limit * 2,  # Get extra for filtering
                    min_similarity=min_similarity
                )
                candidates = [d for d, _ in semantic_results]
                semantic_scores_dict = {d.id: score for d, score in semantic_results}
                search_mode = "semantic"
            elif hasattr(graph, "full_text_search"):
                # Prefer DB-native FTS when available
                candidate_limit = int(min(max(limit * 5, limit), 500))
                candidates = await graph.full_text_search(str(query_text), limit=candidate_limit)
                search_mode = "fts"
            else:
                # JSON backend fallback: bounded scan of most recent entries (kept small to prevent context bloat).
                # Reduced from 500 to 50 to prevent context bloat
                candidates = await graph.query(limit=50)
                search_mode = "substring_scan"

            q = str(query_text).lower()
            filtered = []
            for d in candidates:
                hay = ((d.summary or "") + "\n" + (d.details or "")).lower()
                if q not in hay:
                    continue
                if agent_id and d.agent_id != agent_id:
                    continue
                if dtype and d.type != dtype:
                    continue
                if severity and d.severity != severity:
                    continue
                if status and d.status != status:
                    continue
                if tags:
                    d_tags = set(d.tags or [])
                    if not all(t in d_tags for t in tags):
                        continue
                filtered.append(d)
                if len(filtered) >= limit:
                    break

            results = filtered
            # search_mode already set above
        else:
            # Indexed filter query (fast)
            results = await graph.query(
                agent_id=agent_id,
                tags=tags,
                type=dtype,
                severity=severity,
                status=status,
                limit=limit
            )
            search_mode = "indexed_filters"
        dt_ms = (time.perf_counter() - t0) * 1000.0
        record_ms(f"knowledge.search.{search_mode}", dt_ms)
        
        # Build discovery list with optional provenance
        discovery_list = []
        for d in results:
            d_dict = d.to_dict(include_details=include_details)
            if include_provenance:
                d_dict["provenance"] = d.provenance
                if d.provenance_chain:
                    d_dict["provenance_chain"] = d.provenance_chain
            discovery_list.append(d_dict)
        
        # Include similarity scores for semantic search
        response_data = {
            "search_mode": search_mode,
            "query": query_text,
            "discoveries": discovery_list,
            "count": len(results),
            "message": f"Found {len(results)} discovery(ies)" + ("" if include_details else " (use get_discovery_details for full content)")
        }
        
        # Add similarity scores if semantic search was used
        if search_mode == "semantic" and query_text and use_semantic:
            similarity_scores = {
                d.id: round(semantic_scores_dict[d.id], 3)
                for d in results
                if d.id in semantic_scores_dict
            }
            if similarity_scores:
                response_data["similarity_scores"] = similarity_scores
        
        return success_response(response_data)
        
    except Exception as e:
        return [error_response(f"Failed to search knowledge: {str(e)}")]


@mcp_tool("get_knowledge_graph", timeout=15.0, rate_limit_exempt=True)
async def handle_get_knowledge_graph(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Get all knowledge for an agent - summaries only (use get_discovery_details for full content)"""
    # SECURITY FIX: Verify agent_id is registered (prevents phantom agent_ids)
    agent_id, error = require_registered_agent(arguments)
    if error:
        return [error]
    
    try:
        graph = await get_knowledge_graph()
        
        limit = arguments.get("limit")
        t0 = time.perf_counter()
        discoveries = await graph.get_agent_discoveries(agent_id, limit=limit)
        record_ms("knowledge.get_agent_discoveries", (time.perf_counter() - t0) * 1000.0)
        
        # Return summaries only by default
        include_details = arguments.get("include_details", False)
        
        return success_response({
            "agent_id": agent_id,
            "discoveries": [d.to_dict(include_details=include_details) for d in discoveries],
            "count": len(discoveries)
        })
        
    except Exception as e:
        return [error_response(f"Failed to retrieve knowledge: {str(e)}")]


@mcp_tool("list_knowledge_graph", timeout=10.0, rate_limit_exempt=True)
async def handle_list_knowledge_graph(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """List knowledge graph statistics - full transparency"""
    try:
        graph = await get_knowledge_graph()
        t0 = time.perf_counter()
        stats = await graph.get_stats()
        record_ms("knowledge.get_stats", (time.perf_counter() - t0) * 1000.0)
        
        return success_response({
            "stats": stats,
            "message": f"Knowledge graph contains {stats['total_discoveries']} discoveries from {stats['total_agents']} agents"
        })
        
    except Exception as e:
        return [error_response(f"Failed to list knowledge: {str(e)}")]


@mcp_tool("update_discovery_status_graph", timeout=10.0)
async def handle_update_discovery_status_graph(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Update discovery status - fast graph update
    
    SECURITY: Requires authentication for high-severity discoveries.
    Low/medium severity discoveries can be updated by any registered agent (collaborative).
    """
    # SECURITY FIX: Require registered agent_id (prevents phantom agent_ids)
    agent_id, error = require_registered_agent(arguments)
    if error:
        return [error]
    
    discovery_id, error = require_argument(arguments, "discovery_id",
                                         "discovery_id is required")
    if error:
        return [error]
    
    # Validate discovery_id format
    discovery_id, error = validate_discovery_id(discovery_id)
    if error:
        return [error]
    
    status, error = require_argument(arguments, "status",
                                   "status is required (open, resolved, archived, disputed)")
    if error:
        return [error]
    
    # Validate status enum
    status, error = validate_discovery_status(status)
    if error:
        return [error]
    
    try:
        graph = await get_knowledge_graph()
        
        # Get discovery to check severity and ownership
        discovery = await graph.get_discovery(discovery_id)
        if not discovery:
            return [error_response(f"Discovery '{discovery_id}' not found")]
        
        # SECURITY FIX: Require authentication for high-severity discoveries
        if discovery.severity in ["high", "critical"]:
            # Use centralized fallback chain (explicit → session → metadata → SQLite)
            from .utils import get_api_key_with_fallback
            api_key = get_api_key_with_fallback(agent_id, arguments)
            
            if not api_key:
                return [error_response(
                    "API key required for updating high-severity discoveries. "
                    "High-severity discoveries require authentication to prevent unauthorized modifications.",
                    recovery={
                        "action": "Provide api_key parameter or bind your identity",
                        "related_tools": ["get_agent_api_key", "bind_identity"],
                        "workflow": [
                            "Option 1: Get API key via get_agent_api_key and include in update_discovery_status_graph call",
                            "Option 2: Call bind_identity(agent_id, api_key) once, then API key auto-retrieved from session",
                            "Tip: After bind_identity, you won't need to pass api_key explicitly"
                        ]
                    }
                )]
            
            # Verify API key matches agent_id
            import src.mcp_server_std as mcp_server
            agent_meta = mcp_server.agent_metadata.get(agent_id)
            if not agent_meta or agent_meta.api_key != api_key:
                return [error_response(
                    "Invalid API key for updating high-severity discovery. "
                    "API key must match the agent_id.",
                    recovery={
                        "action": "Verify your API key matches your agent_id",
                        "related_tools": ["get_agent_api_key"],
                        "workflow": "1. Get correct API key for your agent_id 2. Retry with correct key"
                    }
                )]
            
            # SECURITY: Check ownership - only discovery owner can update high-severity discoveries
            if discovery.agent_id != agent_id:
                return [error_response(
                    f"Permission denied: Cannot update high-severity discovery '{discovery_id}'. "
                    f"Discovery belongs to agent '{discovery.agent_id}', not '{agent_id}'.",
                    recovery={
                        "action": "Only the discovery owner can update high-severity discoveries",
                        "related_tools": ["get_discovery_details", "search_knowledge_graph"],
                        "workflow": "High-severity discoveries can only be updated by their creator for security."
                    }
                )]
        
        updates = {"status": status}
        if status == "resolved":
            updates["resolved_at"] = datetime.now().isoformat()
        
        success = await graph.update_discovery(discovery_id, updates)
        
        if not success:
            return [error_response(f"Discovery '{discovery_id}' not found")]
        
        discovery = await graph.get_discovery(discovery_id)
        
        return success_response({
            "message": f"Discovery '{discovery_id}' status updated to '{status}'",
            "discovery": discovery.to_dict(include_details=False) if discovery else None
        })
        
    except Exception as e:
        return [error_response(f"Failed to update discovery: {str(e)}")]


@mcp_tool("find_similar_discoveries_graph", timeout=15.0, rate_limit_exempt=True)
async def handle_find_similar_discoveries_graph(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Find similar discoveries by tag overlap - fast tag-based search"""
    discovery_id, error = require_argument(arguments, "discovery_id",
                                         "discovery_id is required")
    if error:
        return [error]
    
    # Validate discovery_id format
    discovery_id, error = validate_discovery_id(discovery_id)
    if error:
        return [error]
    
    limit = arguments.get("limit", 10)
    
    try:
        graph = await get_knowledge_graph()
        
        discovery = await graph.get_discovery(discovery_id)
        if not discovery:
            return [error_response(f"Discovery '{discovery_id}' not found")]
        
        t0 = time.perf_counter()
        similar = await graph.find_similar(discovery, limit=limit)
        record_ms("knowledge.find_similar", (time.perf_counter() - t0) * 1000.0)
        
        return success_response({
            "discovery_id": discovery_id,
            "similar_discoveries": [d.to_dict(include_details=False) for d in similar],
            "count": len(similar),
            "message": f"Found {len(similar)} similar discovery(ies)"
        })
        
    except Exception as e:
        return [error_response(f"Failed to find similar discoveries: {str(e)}")]


@mcp_tool("get_discovery_details", timeout=10.0, rate_limit_exempt=True)
async def handle_get_discovery_details(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Get full details for a specific discovery - use after search to drill down"""
    discovery_id, error = require_argument(arguments, "discovery_id",
                                         "discovery_id is required")
    if error:
        return [error]
    
    # Validate discovery_id format
    discovery_id, error = validate_discovery_id(discovery_id)
    if error:
        return [error]
    
    try:
        graph = await get_knowledge_graph()
        
        discovery = await graph.get_discovery(discovery_id)
        if not discovery:
            return [error_response(f"Discovery '{discovery_id}' not found")]
        
        return success_response({
            "discovery": discovery.to_dict(include_details=True),
            "message": f"Full details for discovery '{discovery_id}'"
        })
        
    except Exception as e:
        return [error_response(f"Failed to get discovery details: {str(e)}")]


@mcp_tool("get_related_discoveries_graph", timeout=15.0, rate_limit_exempt=True)
async def handle_get_related_discoveries_graph(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Graph traversal: get discoveries related to a given discovery (edges if SQLite; best-effort fallback if JSON)."""
    discovery_id, error = require_argument(arguments, "discovery_id", "discovery_id is required")
    if error:
        return [error]

    edge_types = arguments.get("edge_types")  # optional list
    limit = int(arguments.get("limit", 20))
    include_details = bool(arguments.get("include_details", False))

    try:
        graph = await get_knowledge_graph()

        # SQLite backend: use true edge traversal
        if hasattr(graph, "get_related_discoveries"):
            t0 = time.perf_counter()
            rel = await graph.get_related_discoveries(discovery_id, edge_types=edge_types, limit=limit)
            record_ms("knowledge.get_related_discoveries", (time.perf_counter() - t0) * 1000.0)
            related = []
            for node, edge_type, direction in rel:
                related.append({
                    "edge_type": edge_type,
                    "direction": direction,
                    "discovery": node.to_dict(include_details=include_details)
                })
            return success_response({
                "discovery_id": discovery_id,
                "backend": type(graph).__name__,
                "related": related,
                "count": len(related)
            })

        # JSON backend fallback: use related_to + response_to/responses_from only
        t0 = time.perf_counter()
        d = await graph.get_discovery(discovery_id)
        if not d:
            return [error_response(f"Discovery '{discovery_id}' not found")]

        related_nodes = []
        # related_to outward
        for rid in (d.related_to or [])[:limit]:
            rd = await graph.get_discovery(rid)
            if rd:
                related_nodes.append({
                    "edge_type": "related_to",
                    "direction": "outgoing",
                    "discovery": rd.to_dict(include_details=include_details)
                })

        # response_to parent
        if d.response_to and len(related_nodes) < limit:
            parent = await graph.get_discovery(d.response_to.discovery_id)
            if parent:
                related_nodes.append({
                    "edge_type": "response_to",
                    "direction": "outgoing",
                    "discovery": parent.to_dict(include_details=include_details)
                })

        # responses_from children
        for cid in (d.responses_from or [])[: max(0, limit - len(related_nodes))]:
            child = await graph.get_discovery(cid)
            if child:
                related_nodes.append({
                    "edge_type": "responses_from",
                    "direction": "incoming",
                    "discovery": child.to_dict(include_details=include_details)
                })

        resp = success_response({
            "discovery_id": discovery_id,
            "backend": type(graph).__name__,
            "related": related_nodes,
            "count": len(related_nodes),
            "note": "JSON backend fallback (limited traversal). SQLite backend provides full edge traversal."
        })
        # (best-effort timing, includes small traversal work)
        record_ms("knowledge.get_related_discoveries.fallback", (time.perf_counter() - t0) * 1000.0)
        return resp

    except Exception as e:
        return [error_response(f"Failed to get related discoveries: {str(e)}")]


@mcp_tool("get_response_chain_graph", timeout=15.0, rate_limit_exempt=True)
async def handle_get_response_chain_graph(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Graph traversal: get response chain thread for a discovery (SQLite recursive CTE; best-effort fallback if JSON)."""
    discovery_id, error = require_argument(arguments, "discovery_id", "discovery_id is required")
    if error:
        return [error]

    max_depth = int(arguments.get("max_depth", 10))
    include_details = bool(arguments.get("include_details", False))

    try:
        graph = await get_knowledge_graph()

        # SQLite backend: true response chain traversal
        if hasattr(graph, "get_response_chain"):
            t0 = time.perf_counter()
            chain = await graph.get_response_chain(discovery_id, max_depth=max_depth)
            record_ms("knowledge.get_response_chain", (time.perf_counter() - t0) * 1000.0)
            return success_response({
                "discovery_id": discovery_id,
                "backend": type(graph).__name__,
                "max_depth": max_depth,
                "chain": [d.to_dict(include_details=include_details) for d in chain],
                "count": len(chain)
            })

        # JSON backend fallback: walk via responses_from (children) breadth-first up to max_depth.
        t0 = time.perf_counter()
        root = await graph.get_discovery(discovery_id)
        if not root:
            return [error_response(f"Discovery '{discovery_id}' not found")]

        chain = []
        frontier = [(root, 0)]
        seen = set()
        while frontier:
            node, depth = frontier.pop(0)
            if node.id in seen:
                continue
            seen.add(node.id)
            chain.append(node)
            if depth >= max_depth:
                continue
            for child_id in (node.responses_from or []):
                child = await graph.get_discovery(child_id)
                if child and child.id not in seen:
                    frontier.append((child, depth + 1))

        resp = success_response({
            "discovery_id": discovery_id,
            "backend": type(graph).__name__,
            "max_depth": max_depth,
            "chain": [d.to_dict(include_details=include_details) for d in chain],
            "count": len(chain),
            "note": "JSON backend fallback (responses_from traversal). SQLite backend provides full threaded traversal."
        })
        record_ms("knowledge.get_response_chain.fallback", (time.perf_counter() - t0) * 1000.0)
        return resp

    except Exception as e:
        return [error_response(f"Failed to get response chain: {str(e)}")]


@mcp_tool("reply_to_question", timeout=10.0)
async def handle_reply_to_question(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Reply to a question in the knowledge graph - creates an answer linked to the question"""
    # SECURITY FIX: Verify agent_id is registered (prevents phantom agent_ids)
    agent_id, error = require_registered_agent(arguments)
    if error:
        return [error]
    
    question_id, error = require_argument(arguments, "question_id",
                                        "question_id is required (ID of the question to answer)")
    if error:
        return [error]
    
    summary, error = require_argument(arguments, "summary",
                                    "summary is required (brief answer summary)")
    if error:
        return [error]
    
    try:
        graph = await get_knowledge_graph()
        
        # Verify question exists and is actually a question
        question = await graph.get_discovery(question_id)
        if not question:
            return [error_response(f"Question '{question_id}' not found")]
        
        if question.type != "question":
            return [error_response(f"Discovery '{question_id}' is not a question (type: {question.type})")]
        
        # Get answer details (optional)
        details = arguments.get("details", "")
        tags = arguments.get("tags", [])
        severity = arguments.get("severity")
        
        # Ensure question tags are included for discoverability
        if question.tags:
            # Merge tags, avoiding duplicates
            answer_tags = set(tags) | set(question.tags)
            tags = list(answer_tags)
        
        # Create answer discovery
        from src.knowledge_graph import DiscoveryNode
        answer = DiscoveryNode(
            id=datetime.now().isoformat(),
            agent_id=agent_id,
            type="answer",
            summary=summary,
            details=details,
            tags=tags,
            severity=severity,
            related_to=[question_id],  # Link to the question
            status="open"
        )
        
        # Store answer
        await graph.add_discovery(answer)
        
        # Optionally mark question as resolved
        mark_resolved = arguments.get("mark_question_resolved", False)
        if mark_resolved:
            # SECURITY: Check if question is high-severity (requires auth + ownership)
            if question.severity in ["high", "critical"]:
                api_key = arguments.get("api_key")
                
                # FRICTION FIX: Auto-fallback to session-bound identity if API key not provided
                if not api_key:
                    try:
                        from .identity import get_bound_agent_id, get_bound_api_key
                        bound_id = get_bound_agent_id(arguments=arguments)
                        if bound_id == agent_id:
                            bound_key = get_bound_api_key(arguments=arguments)
                            if bound_key:
                                api_key = bound_key
                                arguments["api_key"] = api_key
                                logger.debug(f"Auto-retrieved API key for resolving high-severity question")
                    except (ImportError, AttributeError, Exception):
                        pass  # Continue with auth check below
                
                if not api_key:
                    return [error_response(
                        "API key required to mark high-severity question as resolved. "
                        "High-severity questions require authentication.",
                        recovery={
                            "action": "Provide api_key parameter or bind your identity",
                            "related_tools": ["get_agent_api_key", "bind_identity"]
                        }
                    )]
                
                # Verify API key matches agent_id
                import src.mcp_server_std as mcp_server
                agent_meta = mcp_server.agent_metadata.get(agent_id)
                if not agent_meta or agent_meta.api_key != api_key:
                    return [error_response(
                        "Invalid API key. Cannot mark high-severity question as resolved.",
                        recovery={
                            "action": "Verify your API key matches your agent_id",
                            "related_tools": ["get_agent_api_key"]
                        }
                    )]
                
                # SECURITY: Only question owner can mark high-severity questions as resolved
                if question.agent_id != agent_id:
                    return [error_response(
                        f"Permission denied: Cannot mark high-severity question '{question_id}' as resolved. "
                        f"Question belongs to agent '{question.agent_id}', not '{agent_id}'.",
                        recovery={
                            "action": "Only the question owner can mark high-severity questions as resolved",
                            "related_tools": ["get_discovery_details"]
                        }
                    )]
            
            # Update question status (auth checks passed if high-severity)
            await graph.update_discovery(question_id, {
                "status": "resolved",
                "resolved_at": datetime.now().isoformat()
            })
            question_status = "resolved"
        else:
            question_status = question.status
        
        return success_response({
            "message": f"Answer stored for question '{question_id}'",
            "answer_id": answer.id,
            "answer": answer.to_dict(include_details=False),
            "question_id": question_id,
            "question_status": question_status,
            "note": "Use search_knowledge_graph with discovery_type='answer' and related_to to find answers to questions"
        })
        
    except Exception as e:
        return [error_response(f"Failed to reply to question: {str(e)}")]


async def _handle_store_knowledge_graph_batch(arguments: Dict[str, Any], agent_id: str) -> Sequence[TextContent]:
    """Internal batch handler - called by store_knowledge_graph when discoveries array is provided"""
    discoveries = arguments.get("discoveries")
    
    if not isinstance(discoveries, list):
        return [error_response("discoveries must be a list of discovery objects")]
    
    if len(discoveries) == 0:
        return [error_response("discoveries list cannot be empty")]
    
    if len(discoveries) > 10:
        return [error_response("Maximum 10 discoveries per batch (to prevent context overflow)")]
    
    # agent_id already validated by caller
    
    try:
        graph = await get_knowledge_graph()
        
        # SECURITY: Rate limiting is handled by the knowledge graph backend per-discovery
        # JSON backend uses efficient timestamp tracking (O(1) per store)
        # SQLite backend uses dedicated rate_limits table (O(1) per store)
        # No need for inefficient O(n) query here - let graph handle it per-discovery
        
        # Process each discovery with graceful error handling
        stored = []
        errors = []
        
        for idx, disc_data in enumerate(discoveries):
            try:
                # Validate required fields
                if not isinstance(disc_data, dict):
                    errors.append(f"Discovery {idx}: must be a dict")
                    continue
                
                discovery_type = disc_data.get("discovery_type")
                if not discovery_type:
                    errors.append(f"Discovery {idx}: discovery_type is required")
                    continue
                
                discovery_type, error = validate_discovery_type(discovery_type)
                if error:
                    errors.append(f"Discovery {idx}: {error.text if hasattr(error, 'text') else str(error)}")
                    continue
                
                summary = disc_data.get("summary", "")
                if not summary:
                    errors.append(f"Discovery {idx}: summary is required")
                    continue
                
                # Truncate fields
                MAX_SUMMARY_LEN = 300
                MAX_DETAILS_LEN = 500
                
                if len(summary) > MAX_SUMMARY_LEN:
                    summary = summary[:MAX_SUMMARY_LEN] + "..."
                
                details = disc_data.get("details", "")
                if len(details) > MAX_DETAILS_LEN:
                    details = details[:MAX_DETAILS_LEN] + "... [truncated]"
                
                # Create discovery node
                discovery_id = datetime.now().isoformat()
                
                # Parse response_to if provided
                response_to = None
                if "response_to" in disc_data and disc_data["response_to"]:
                    resp_data = disc_data["response_to"]
                    if isinstance(resp_data, dict) and "discovery_id" in resp_data and "response_type" in resp_data:
                        # Validate discovery_id format
                        parent_id, error = validate_discovery_id(resp_data["discovery_id"])
                        if error:
                            errors.append(f"Discovery {idx}: Invalid response_to.discovery_id - {error.text if hasattr(error, 'text') else str(error)}")
                            continue
                        
                        response_type, error = validate_response_type(resp_data["response_type"])
                        if not error:
                            response_to = ResponseTo(
                                discovery_id=parent_id,
                                response_type=response_type
                            )
                
                # Validate severity
                severity = disc_data.get("severity")
                if severity is not None:
                    severity, error = validate_severity(severity)
                    if error:
                        severity = None  # Use default if invalid
                
                discovery = DiscoveryNode(
                    id=discovery_id,
                    agent_id=agent_id,
                    type=discovery_type,
                    summary=summary,
                    details=details,
                    tags=disc_data.get("tags", []),
                    severity=severity,
                    response_to=response_to,
                    references_files=disc_data.get("related_files", [])
                )
                
                # Auto-link similar discoveries
                if disc_data.get("auto_link_related", True):
                    similar = await graph.find_similar(discovery, limit=3)
                    discovery.related_to = [s.id for s in similar]
                
                # Check high-severity auth requirement
                if discovery.severity in ["high", "critical"]:
                    api_key = arguments.get("api_key")
                    
                    # FRICTION FIX: Auto-fallback to session-bound identity if API key not provided
                    if not api_key:
                        try:
                            from .identity import get_bound_agent_id, get_bound_api_key
                            # Try arguments-based lookup first (for SSE mode with session_id injection)
                            bound_id = get_bound_agent_id(arguments=arguments)
                            if bound_id == agent_id:  # Only use if bound identity matches
                                bound_key = get_bound_api_key(arguments=arguments)
                                if bound_key:
                                    api_key = bound_key
                                    arguments["api_key"] = api_key  # Inject for verification below
                                    logger.debug(f"Auto-retrieved API key from session-bound identity for batch discovery {idx}")
                            else:
                                # Fallback: Try without arguments (for stdio mode with process-based session)
                                bound_id_fallback = get_bound_agent_id()
                                if bound_id_fallback == agent_id:
                                    bound_key_fallback = get_bound_api_key()
                                    if bound_key_fallback:
                                        api_key = bound_key_fallback
                                        arguments["api_key"] = api_key
                                        logger.debug(f"Auto-retrieved API key from session-bound identity (fallback) for batch discovery {idx}")
                        except (ImportError, AttributeError) as e:
                            logger.debug(f"Could not auto-retrieve API key from session identity: {e}")
                            pass  # Identity module not available, continue with normal flow
                        except Exception as e:
                            logger.debug(f"Error auto-retrieving API key from session identity: {e}")
                            pass  # Don't fail the request if auto-retrieval fails
                    
                    if not api_key:
                        errors.append(f"Discovery {idx}: API key required for high-severity discoveries. Use bind_identity() or provide api_key parameter")
                        continue
                    
                    agent_meta = mcp_server.agent_metadata.get(agent_id)
                    if not agent_meta or agent_meta.api_key != api_key:
                        errors.append(f"Discovery {idx}: Invalid API key for high-severity discovery")
                        continue
                
                # Add to graph (rate limiting handled internally)
                await graph.add_discovery(discovery)
                stored.append({
                    "discovery_id": discovery_id,
                    "summary": summary,
                    "type": discovery_type
                })
                
            except ValueError as e:
                # Handle rate limiting and validation errors gracefully
                error_msg = str(e)
                if "rate limit" in error_msg.lower() or "Rate limit" in error_msg:
                    errors.append(f"Discovery {idx}: Rate limit exceeded - {error_msg}")
                else:
                    errors.append(f"Discovery {idx}: Validation error - {error_msg}")
            except Exception as e:
                errors.append(f"Discovery {idx}: {str(e)}")
        
        # Return results
        response = {
            "message": f"Stored {len(stored)}/{len(discoveries)} discovery/discoveries",
            "stored": stored,
            "total": len(discoveries),
            "success_count": len(stored),
            "error_count": len(errors)
        }
        
        if errors:
            response["errors"] = errors
        
        return success_response(response)
        
    except Exception as e:
        return [error_response(f"Failed to store batch knowledge: {str(e)}")]


@mcp_tool("leave_note", timeout=10.0)
async def handle_leave_note(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Leave a quick note in the knowledge graph - minimal friction contribution.
    
    Just agent_id + text + optional tags. Auto-sets type='note', severity='low'.
    For when you want to jot something down without the full store_knowledge_graph ceremony.
    """
    # SECURITY FIX: Verify agent_id is registered (prevents phantom agent_ids)
    agent_id, error = require_registered_agent(arguments)
    if error:
        return [error]
    
    text, error = require_argument(arguments, "text",
                                  "text is required (the note content)")
    if error:
        return [error]
    
    try:
        graph = await get_knowledge_graph()
        
        # Truncate if too long
        MAX_NOTE_LEN = 500
        if len(text) > MAX_NOTE_LEN:
            text = text[:MAX_NOTE_LEN] + "..."
        
        # Parse response_to if provided (for threading)
        response_to = None
        if "response_to" in arguments and arguments["response_to"]:
            resp_data = arguments["response_to"]
            if isinstance(resp_data, dict) and "discovery_id" in resp_data and "response_type" in resp_data:
                # Validate discovery_id format
                parent_id, error = validate_discovery_id(resp_data["discovery_id"])
                if error:
                    return [error]
                
                # Validate response_type enum
                response_type, error = validate_response_type(resp_data["response_type"])
                if error:
                    return [error]
                
                response_to = ResponseTo(
                    discovery_id=parent_id,
                    response_type=response_type
                )
        
        # Create note with minimal ceremony
        note = DiscoveryNode(
            id=datetime.now().isoformat(),
            agent_id=agent_id,
            type="note",
            summary=text,
            details="",  # Notes are summary-only
            tags=arguments.get("tags", []),
            severity="low",
            status="open",
            response_to=response_to
        )
        
        # Auto-link if tags provided (fast with indexes)
        if note.tags:
            similar = await graph.find_similar(note, limit=3)
            note.related_to = [s.id for s in similar]
        
        await graph.add_discovery(note)
        
        return success_response({
            "message": f"Note saved",
            "note_id": note.id,
            "note": note.to_dict(include_details=False)
        })
        
    except Exception as e:
        return [error_response(f"Failed to leave note: {str(e)}")]


