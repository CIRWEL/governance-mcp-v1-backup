"""
Knowledge layer tool handlers.

⚠️  DEPRECATED - ARCHIVED NOVEMBER 28, 2025 ⚠️

These MCP tools are deprecated. See docs/archive/KNOWLEDGE_LAYER_EXPERIMENT.md

DO NOT USE. Preserved for reference only.
"""

from typing import Dict, Any, Sequence
from mcp.types import TextContent
from .utils import success_response, error_response, require_argument, require_agent_id


async def handle_store_knowledge(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Handle store_knowledge tool"""
    from src.knowledge_layer import log_discovery, log_pattern, add_lesson, add_question, find_similar_discoveries
    
    agent_id, error = require_agent_id(arguments)
    if error:
        return [error]
    
    knowledge_type, error = require_argument(arguments, "knowledge_type", 
                                            "knowledge_type is required (discovery, pattern, lesson, or question)")
    if error:
        return [error]
    
    try:
        if knowledge_type == "discovery":
            discovery_type, error = require_argument(arguments, "discovery_type",
                                                    "discovery_type is required for knowledge_type='discovery'")
            if error:
                return [error]
            
            summary = arguments.get("summary", "")

            # Check for similar existing discoveries before storing (opt-in for performance)
            check_duplicates = arguments.get("check_duplicates", False)
            # Limit to 200 discoveries to prevent context compression
            similar = find_similar_discoveries(summary, threshold=0.6, limit=200) if (summary and check_duplicates) else []
            similar_warning = None
            if similar:
                # Filter to open/resolved (not archived) and limit to top 3
                relevant_similar = [
                    (d, score) for d, score in similar 
                    if d.status != "archived"
                ][:3]
                if relevant_similar:
                    similar_warning = {
                        "message": f"Found {len(relevant_similar)} similar discovery(ies). Consider searching first with search_knowledge().",
                        "similar": [
                            {
                                "summary": d.summary,
                                "agent": d.timestamp.split("T")[0],  # Just date for brevity
                                "status": d.status,
                                "similarity": f"{score:.0%}"
                            }
                            for d, score in relevant_similar
                        ]
                    }
            
            discovery = log_discovery(
                agent_id=agent_id,
                discovery_type=discovery_type,
                summary=summary,
                details=arguments.get("details", ""),
                severity=arguments.get("severity"),
                tags=arguments.get("tags", []),
                related_files=arguments.get("related_files", []),
                auto_link_related=arguments.get("auto_link_related", False)
            )
            
            response = {
                "message": f"Discovery logged for agent '{agent_id}'",
                "discovery": discovery.to_dict()
            }
            if similar_warning:
                response["warning"] = similar_warning
            
            return success_response(response)
        
        elif knowledge_type == "pattern":
            pattern_id, error = require_argument(arguments, "pattern_id",
                                                 "pattern_id is required for knowledge_type='pattern'")
            if error:
                return [error]
            
            description, error = require_argument(arguments, "description",
                                                 "description is required for knowledge_type='pattern'")
            if error:
                return [error]
            
            pattern = log_pattern(
                agent_id=agent_id,
                pattern_id=pattern_id,
                description=description,
                severity=arguments.get("severity", "medium"),
                tags=arguments.get("tags", []),
                examples=arguments.get("examples", [])
            )
            
            return success_response({
                "message": f"Pattern logged for agent '{agent_id}'",
                "pattern": pattern.to_dict()
            })
        
        elif knowledge_type == "lesson":
            lesson, error = require_argument(arguments, "lesson",
                                            "lesson is required for knowledge_type='lesson'")
            if error:
                return [error]
            
            add_lesson(agent_id, lesson)
            
            return success_response({
                "message": f"Lesson added for agent '{agent_id}'",
                "lesson": lesson
            })
        
        elif knowledge_type == "question":
            question, error = require_argument(arguments, "question",
                                             "question is required for knowledge_type='question'")
            if error:
                return [error]
            
            add_question(agent_id, question)
            
            return success_response({
                "message": f"Question added for agent '{agent_id}'",
                "question": question
            })
        
        else:
            return [error_response(
                f"Unknown knowledge_type: {knowledge_type}. Must be: discovery, pattern, lesson, or question"
            )]
    
    except Exception as e:
        return [error_response(f"Failed to store knowledge: {str(e)}")]


async def handle_retrieve_knowledge(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Handle retrieve_knowledge tool"""
    from src.knowledge_layer import get_knowledge
    
    agent_id, error = require_agent_id(arguments)
    if error:
        return [error]
    
    knowledge = get_knowledge(agent_id)
    
    if knowledge is None:
        return success_response({
            "message": f"No knowledge found for agent '{agent_id}'",
            "knowledge": None
        })
    
    return success_response({
        "knowledge": knowledge.to_dict()
    })


async def handle_search_knowledge(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Handle search_knowledge tool"""
    from src.knowledge_layer import query_discoveries
    
    agent_id = arguments.get("agent_id")
    discovery_type = arguments.get("discovery_type")
    tags = arguments.get("tags", [])
    severity = arguments.get("severity")
    status = arguments.get("status")
    search_text = arguments.get("search_text")
    sort_by = arguments.get("sort_by", "timestamp")
    sort_order = arguments.get("sort_order", "desc")
    limit = arguments.get("limit", 100)  # Default limit to prevent context compression
    
    discoveries = query_discoveries(
        agent_id=agent_id,
        discovery_type=discovery_type,
        tags=tags if tags else None,
        severity=severity,
        status=status,
        search_text=search_text,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit
    )
    
    return success_response({
        "count": len(discoveries),
        "discoveries": [d.to_dict() for d in discoveries],
        "filters": {
            "agent_id": agent_id,
            "discovery_type": discovery_type,
            "tags": tags,
            "severity": severity,
            "status": status,
            "search_text": search_text,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "limit": limit
        },
        "note": f"Results limited to {limit} discoveries. Use more specific filters or increase limit if needed."
    })


async def handle_update_discovery_status(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Handle update_discovery_status tool"""
    from src.knowledge_layer import update_discovery_status
    
    agent_id, error = require_agent_id(arguments)
    if error:
        return [error]
    
    discovery_timestamp, error = require_argument(arguments, "discovery_timestamp", 
                                                 "discovery_timestamp is required")
    if error:
        return [error]
    
    new_status, error = require_argument(arguments, "new_status",
                                        "new_status is required (open, resolved, archived)")
    if error:
        return [error]
    
    if new_status not in ["open", "resolved", "archived"]:
        return [error_response(f"Invalid status: {new_status}. Must be: open, resolved, archived")]
    
    resolved_reason = arguments.get("resolved_reason")
    
    discovery = update_discovery_status(agent_id, discovery_timestamp, new_status, resolved_reason)
    
    if discovery is None:
        return [error_response(f"Discovery not found for agent '{agent_id}' with timestamp '{discovery_timestamp}'")]
    
    return success_response({
        "message": f"Discovery status updated to '{new_status}'",
        "discovery": discovery.to_dict()
    })


async def handle_update_discovery(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Handle update_discovery tool"""
    from src.knowledge_layer import update_discovery
    
    agent_id, error = require_agent_id(arguments)
    if error:
        return [error]
    
    discovery_timestamp, error = require_argument(arguments, "discovery_timestamp",
                                                 "discovery_timestamp is required")
    if error:
        return [error]
    
    # Extract update fields
    update_fields = {}
    if "summary" in arguments:
        update_fields["summary"] = arguments["summary"]
    if "details" in arguments:
        update_fields["details"] = arguments["details"]
    if "severity" in arguments:
        update_fields["severity"] = arguments["severity"]
    if "tags" in arguments:
        update_fields["tags"] = arguments["tags"]
    if "status" in arguments:
        update_fields["status"] = arguments["status"]
    if "related_files" in arguments:
        update_fields["related_files"] = arguments["related_files"]
    if "append_details" in arguments:
        update_fields["append_details"] = arguments["append_details"]
    
    if not update_fields:
        return [error_response("No update fields provided. Specify at least one: summary, details, severity, tags, status, related_files")]
    
    discovery = update_discovery(agent_id, discovery_timestamp, **update_fields)
    
    if discovery is None:
        return [error_response(f"Discovery not found for agent '{agent_id}' with timestamp '{discovery_timestamp}'")]
    
    return success_response({
        "message": "Discovery updated successfully",
        "discovery": discovery.to_dict(),
        "updated_fields": list(update_fields.keys())
    })


async def handle_find_similar_discoveries(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Handle find_similar_discoveries tool"""
    from src.knowledge_layer import find_similar_discoveries
    
    summary, error = require_argument(arguments, "summary", "summary is required")
    if error:
        return [error]
    
    threshold = arguments.get("threshold", 0.7)
    agent_id = arguments.get("agent_id")
    
    if not (0.0 <= threshold <= 1.0):
        return [error_response("threshold must be between 0.0 and 1.0")]
    
    similar = find_similar_discoveries(summary, threshold, agent_id)
    
    return success_response({
        "count": len(similar),
        "similar_discoveries": [
            {
                "discovery": discovery.to_dict(),
                "similarity_score": score
            }
            for discovery, score in similar
        ],
        "threshold": threshold
    })


async def handle_list_knowledge(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Handle list_knowledge tool"""
    from src.knowledge_layer import get_knowledge_manager
    
    manager = get_knowledge_manager()
    stats = manager.get_stats()
    
    return success_response({
        "stats": stats,
        "note": "Use retrieve_knowledge(agent_id) to get full knowledge for a specific agent, or search_knowledge() to query discoveries."
    })
