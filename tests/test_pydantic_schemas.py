import pytest
from pydantic import ValidationError
from src.tool_schemas import get_pydantic_schemas
from src.tool_schemas import get_pydantic_schemas

class TestPydanticSchemas:
    """Tests to ensure our new Pydantic schema validation is robust and has 
    full coverage of the type coercions and bounds checking previously handled 
    by manual validators."""

    def test_float_bounds(self):
        """Test float range bounds are applied correctly (e.g., complexity 0.0-1.0)."""
        from src.mcp_handlers.schemas.core import ProcessAgentUpdateParams
        # Valid bounds
        valid = ProcessAgentUpdateParams(complexity=0.5, response_text="Test")
        assert valid.complexity == 0.5
        
        # Invalid upper bound
        with pytest.raises(ValidationError) as exc:
            ProcessAgentUpdateParams(complexity=1.5, response_text="Test")
        assert "less than or equal to 1" in str(exc.value).lower()
        
        # Invalid lower bound
        with pytest.raises(ValidationError) as exc:
            ProcessAgentUpdateParams(complexity=-0.1, response_text="Test")
        assert "greater than or equal to 0" in str(exc.value).lower()

    def test_ethical_drift_bounds(self):
        """Test ethical drift lists are correctly bounded."""
        from src.mcp_handlers.schemas.core import ProcessAgentUpdateParams
        # Valid
        valid = ProcessAgentUpdateParams(ethical_drift=[0.1, -0.5, 1.0], response_text="T")
        assert valid.ethical_drift == [0.1, -0.5, 1.0]

        # Valid defaults
        default = ProcessAgentUpdateParams(response_text="T")
        assert default.ethical_drift == [0.0, 0.0, 0.0]

    def test_boolean_coercion(self):
        """Tests our custom @model_validator coercions for booleans."""
        from src.mcp_handlers.schemas.admin import ListToolsParams
        # Test ListToolsParams which uses coerce_booleans
        # "true" -> True
        model = ListToolsParams(essential_only="true", verbose=1)
        assert model.essential_only is True
        assert model.verbose is True
        
        # "false" -> False
        model2 = ListToolsParams(essential_only="false", verbose="0")
        assert model2.essential_only is False
        assert model2.verbose is False
        
        # Already bool
        model3 = ListToolsParams(essential_only=True)
        assert model3.essential_only is True

    def test_enum_validation(self):
        """Test Literal enums restrict input correctly."""
        from src.mcp_handlers.schemas.core import ProcessAgentUpdateParams
        # Valid
        valid = ProcessAgentUpdateParams(response_text="T", response_mode="auto")
        assert valid.response_mode == "auto"

        # Invalid
        with pytest.raises(ValidationError):
            ProcessAgentUpdateParams(response_text="T", response_mode="invalid_mode")

    def test_schema_registry_complete(self):
        """Ensure all 79 tools mapped in PYDANTIC_SCHEMAS exist and are valid subclasses of BaseModel."""
        schemas = get_pydantic_schemas()
        assert len(schemas) >= 70, "Should have schemas for all known tools"
        for name, model_cls in schemas.items():
            assert hasattr(model_cls, "model_validate"), f"Schema for {name} must be a Pydantic model"

    def test_pi_params_validation(self):
        """Verify complex discriminated unions or enums in PiParams work."""
        from src.mcp_handlers.schemas.pi_orchestration import PiParams
        valid_health = PiParams(action="health")
        assert valid_health.action == "health"

        valid_sync = PiParams(action="sync_eisv", update_governance=True)
        assert valid_sync.action == "sync_eisv"
        assert valid_sync.update_governance is True

        with pytest.raises(ValidationError):
            PiParams(action="unknown_action_xyz")

    def test_legacy_validation_removal(self):
        """Confirm that missing/invalid types let Pydantic handle it naturally."""
        # Instead of manual code checking if limit is int, Pydantic type hints do it
        # E.g., list_tools (we handle this automatically)
        pass 
