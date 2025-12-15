#!/bin/bash
# Quick test script for OpenAI-compatible endpoints
# Usage: ./tests/test_openai_endpoints.sh [BASE_URL]

BASE_URL="${1:-http://127.0.0.1:8765}"

echo "============================================================"
echo "OpenAI-Compatible Endpoints Quick Test"
echo "============================================================"
echo "Testing server at: $BASE_URL"
echo ""

# Test health endpoint
echo "1. Testing /health endpoint..."
if curl -s -f "$BASE_URL/health" > /dev/null 2>&1; then
    echo "   ✅ Health check passed"
else
    echo "   ❌ Health check failed"
    exit 1
fi

# Test list tools
echo ""
echo "2. Testing GET /v1/tools endpoint..."
TOOL_COUNT=$(curl -s "$BASE_URL/v1/tools" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('count', 0))" 2>/dev/null)
if [ -n "$TOOL_COUNT" ] && [ "$TOOL_COUNT" -gt 0 ]; then
    echo "   ✅ Found $TOOL_COUNT tools"
else
    echo "   ❌ Failed to get tools or count is 0"
    exit 1
fi

# Test call tool
echo ""
echo "3. Testing POST /v1/tools/call endpoint..."
SUCCESS=$(curl -s -X POST "$BASE_URL/v1/tools/call" \
    -H "Content-Type: application/json" \
    -d '{"name": "health_check", "arguments": {}}' \
    | python3 -c "import sys, json; d=json.load(sys.stdin); print('true' if d.get('success') else 'false')" 2>/dev/null)

if [ "$SUCCESS" = "true" ]; then
    echo "   ✅ Tool call succeeded"
else
    echo "   ❌ Tool call failed"
    exit 1
fi

echo ""
echo "============================================================"
echo "✅ All quick tests passed!"
echo "============================================================"
echo ""
echo "For more detailed tests, run:"
echo "  python3 tests/test_openai_endpoints.py --base-url $BASE_URL"

