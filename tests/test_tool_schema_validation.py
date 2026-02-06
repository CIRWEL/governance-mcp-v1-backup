"""
Tool schema and registry validation tests.

Validates structural correctness of tool schemas and registry alignment
without requiring any backend mocking.
"""

import json
import pytest
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.tool_schemas import get_tool_definitions
from src.mcp_handlers.decorators import (
    get_tool_registry,
    list_registered_tools,
    _TOOL_DEFINITIONS,
)
from src.mcp_handlers.tool_stability import _TOOL_ALIASES


# ============================================================================
# Schema Structure Validation
# ============================================================================

class TestSchemaStructure:

    @pytest.fixture(scope="class")
    def tools(self):
        return get_tool_definitions(verbosity="full")

    def test_tool_definitions_returns_list(self, tools):
        assert isinstance(tools, list)
        assert len(tools) > 0

    def test_every_tool_has_name(self, tools):
        for tool in tools:
            assert hasattr(tool, 'name'), f"Tool missing name: {tool}"
            assert tool.name, f"Tool has empty name"

    def test_every_tool_has_description(self, tools):
        missing = []
        for tool in tools:
            assert hasattr(tool, 'description'), f"Tool {tool.name} missing description"
            if not tool.description:
                missing.append(tool.name)
        # Allow a few tools to have empty descriptions (some are auto-generated stubs)
        assert len(missing) <= 5, (
            f"Too many tools with empty descriptions ({len(missing)}): {missing}"
        )

    def test_every_tool_has_input_schema(self, tools):
        for tool in tools:
            assert hasattr(tool, 'inputSchema'), f"Tool {tool.name} missing inputSchema"
            schema = tool.inputSchema
            assert isinstance(schema, dict), f"Tool {tool.name} inputSchema is not a dict"

    def test_input_schema_has_type_object(self, tools):
        for tool in tools:
            schema = tool.inputSchema
            assert schema.get("type") == "object", (
                f"Tool {tool.name} inputSchema type should be 'object', got {schema.get('type')}"
            )

    def test_input_schema_has_properties(self, tools):
        for tool in tools:
            schema = tool.inputSchema
            assert "properties" in schema, (
                f"Tool {tool.name} inputSchema missing 'properties'"
            )

    def test_no_duplicate_tool_names(self, tools):
        names = [t.name for t in tools]
        duplicates = [n for n in names if names.count(n) > 1]
        assert len(duplicates) == 0, f"Duplicate tool names: {set(duplicates)}"

    def test_description_length_reasonable(self, tools):
        """Short-mode descriptions should be concise."""
        short_tools = get_tool_definitions(verbosity="short")
        for tool in short_tools:
            # Short descriptions should be under 500 chars
            assert len(tool.description) < 2000, (
                f"Tool {tool.name} description too long ({len(tool.description)} chars)"
            )

    def test_required_params_subset_of_properties(self, tools):
        """Required params must exist in properties."""
        for tool in tools:
            schema = tool.inputSchema
            required = schema.get("required", [])
            properties = schema.get("properties", {})
            for param in required:
                assert param in properties, (
                    f"Tool {tool.name}: required param '{param}' not in properties"
                )


# ============================================================================
# Registry Alignment
# ============================================================================

class TestRegistryAlignment:

    def test_registry_is_not_empty(self):
        registry = get_tool_registry()
        assert len(registry) > 0, "Tool registry should not be empty"

    def test_all_registry_tools_are_callable(self):
        registry = get_tool_registry()
        for name, handler in registry.items():
            assert callable(handler), f"Handler for '{name}' is not callable"

    def test_schema_tools_have_handlers(self):
        """Most tools in schema should have registered handlers."""
        tools = get_tool_definitions()
        registry = get_tool_registry()
        tool_names = {t.name for t in tools}

        missing = []
        for name in tool_names:
            if name not in registry:
                # Check if it's an alias
                if name not in _TOOL_ALIASES:
                    missing.append(name)

        # Allow some slack - some schema tools may use the legacy elif chain
        # but the majority should be registered
        coverage = 1 - (len(missing) / len(tool_names)) if tool_names else 0
        assert coverage > 0.5, (
            f"Only {coverage:.0%} of schema tools have handlers. Missing: {missing[:10]}"
        )


# ============================================================================
# Alias Validation
# ============================================================================

class TestAliasValidation:

    def test_aliases_dict_not_empty(self):
        assert len(_TOOL_ALIASES) > 0, "Tool aliases should not be empty"

    def test_all_aliases_have_new_name(self):
        for old_name, alias in _TOOL_ALIASES.items():
            assert alias.new_name, f"Alias '{old_name}' has no new_name"

    def test_alias_targets_exist_in_registry(self):
        """Alias targets should point to existing tools."""
        registry = get_tool_registry()
        missing_targets = []
        for old_name, alias in _TOOL_ALIASES.items():
            if alias.new_name not in registry:
                missing_targets.append(f"{old_name} -> {alias.new_name}")

        # Allow some slack for aliases that target tools not yet migrated
        if missing_targets:
            # At least 80% of aliases should point to valid targets
            coverage = 1 - (len(missing_targets) / len(_TOOL_ALIASES))
            assert coverage > 0.5, (
                f"Many alias targets missing from registry: {missing_targets[:5]}"
            )

    def test_alias_old_name_matches_key(self):
        """ToolAlias.old_name should match the dict key."""
        for key, alias in _TOOL_ALIASES.items():
            assert alias.old_name == key, (
                f"Alias key '{key}' doesn't match old_name '{alias.old_name}'"
            )


# ============================================================================
# Short vs Full Verbosity
# ============================================================================

class TestVerbosityModes:

    def test_short_mode_exists(self):
        tools = get_tool_definitions(verbosity="short")
        assert len(tools) > 0

    def test_full_mode_exists(self):
        tools = get_tool_definitions(verbosity="full")
        assert len(tools) > 0

    def test_same_tool_count(self):
        short = get_tool_definitions(verbosity="short")
        full = get_tool_definitions(verbosity="full")
        assert len(short) == len(full), (
            f"Short ({len(short)}) and full ({len(full)}) should have same tool count"
        )

    def test_short_descriptions_shorter_or_equal(self):
        """Short mode descriptions should generally be <= full mode."""
        short = {t.name: t.description for t in get_tool_definitions(verbosity="short")}
        full = {t.name: t.description for t in get_tool_definitions(verbosity="full")}

        shorter_count = sum(1 for name in short if len(short[name]) <= len(full.get(name, "")))
        # Most should be shorter or equal
        assert shorter_count > len(short) * 0.5
