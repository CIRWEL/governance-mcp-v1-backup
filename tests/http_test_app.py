"""
Minimal ASGI test app mirroring mcp_server.py endpoint contract.

Since mcp_server.py handlers are closures inside main(), we can't import them
directly. This creates a lightweight Starlette app that uses dispatch_tool()
to test the HTTP layer contract independently.
"""

import json
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import JSONResponse


def create_test_app(dispatch_fn, list_tools_fn=None):
    """
    Create a test ASGI app mirroring mcp_server.py endpoints.

    Args:
        dispatch_fn: async callable(name, arguments) -> result
        list_tools_fn: optional callable() -> list of tool dicts
    """
    async def call_tool(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                {"error": True, "message": "Invalid JSON body"},
                status_code=400
            )

        tool_name = body.get("tool_name") or body.get("name")
        if not tool_name:
            return JSONResponse(
                {"error": True, "message": "Missing tool_name or name parameter"},
                status_code=400
            )

        arguments = body.get("arguments", {})

        # Propagate session header into arguments (mirrors mcp_server.py behavior)
        session_id = request.headers.get("x-session-id")
        if session_id and "client_session_id" not in arguments:
            arguments["client_session_id"] = session_id

        result = await dispatch_fn(tool_name, arguments)

        # Convert TextContent objects to serializable format
        if result and hasattr(result[0], 'text'):
            return JSONResponse({"result": json.loads(result[0].text)})
        return JSONResponse({"result": result})

    async def list_tools(request: Request) -> JSONResponse:
        if list_tools_fn:
            tools = list_tools_fn()
            return JSONResponse({"tools": tools})
        return JSONResponse({"tools": []})

    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    return Starlette(
        routes=[
            Route("/v1/tools/call", call_tool, methods=["POST"]),
            Route("/v1/tools/list", list_tools, methods=["GET"]),
            Route("/health", health, methods=["GET"]),
        ],
        debug=True,
    )
