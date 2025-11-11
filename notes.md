## Current PyRig Design Issues

1. **Type information loss**: `_parse_type_annotation` converts `TriggerMode` → `"triggermode"` string, losing the actual type reference
2. **Manual validation**: Each type needs explicit handling in `validate_value`
3. **Split coercion logic**: Enums handled differently for properties (`_coerce_property_value`) vs commands
4. **String-based type matching**: Using `str_type_map` is fragile and doesn't scale

## Better Design Options

### Option 1: Keep Type References (Recommended)
Store the actual Python type instead of just its name string:

```python
class ParamInfo(BaseModel):
    dtype: str  # For display/serialization
    dtype_ref: type | None = None  # Actual Python type for validation/coercion
    required: bool = True
    default: Any | None = None

    def coerce_value(self, value: Any) -> Any:
        """Coerce value to expected type."""
        if self.dtype_ref is None:
            return value

        # Handle Enum
        if isinstance(self.dtype_ref, type) and issubclass(self.dtype_ref, Enum):
            if isinstance(value, str):
                try:
                    return self.dtype_ref(value)  # By value for StrEnum
                except ValueError:
                    return self.dtype_ref[value]  # By name

        # Handle Pydantic models
        if isinstance(self.dtype_ref, type) and issubclass(self.dtype_ref, BaseModel):
            if isinstance(value, dict):
                return self.dtype_ref(**value)

        return value
```

### Option 2: Use Pydantic for Everything
Instead of manual validation, use Pydantic's validation:

```python
class Command[R]:
    def __init__(self, func: Callable[..., R]):
        self._func = func
        # Create a Pydantic model from function signature
        self._param_model = self._create_param_model(func)

    def _create_param_model(self, func: Callable) -> type[BaseModel]:
        """Generate Pydantic model from function signature."""
        sig = inspect.signature(func)
        fields = {}
        for param_name, param in sig.parameters.items():
            if param.annotation != inspect.Parameter.empty:
                default = ... if param.default == inspect.Parameter.empty else param.default
                fields[param_name] = (param.annotation, default)

        return create_model(f"{func.__name__}_params", **fields)

    def validate_params(self, *args, **kwargs):
        # Pydantic handles all coercion automatically!
        validated = self._param_model(**kwargs)
        return (), validated.model_dump()
```

**Benefits:**
- Automatic enum coercion (Pydantic handles this)
- Automatic type validation
- Handles nested models, unions, Optional, etc.
- One consistent system

### Option 3: JSON Schema + Coercion
Use JSON Schema for validation and a separate coercion layer:

```python
class TypeCoercer:
    """Central type coercion logic."""

    @staticmethod
    def coerce(value: Any, target_type: type) -> Any:
        # Single place for all coercion logic
        if isinstance(target_type, type) and issubclass(target_type, Enum):
            return TypeCoercer._coerce_enum(value, target_type)
        if isinstance(target_type, type) and issubclass(target_type, BaseModel):
            return TypeCoercer._coerce_pydantic(value, target_type)
        return value
```

## My Recommendation for PyRig

**Use Option 1 (Keep Type References) as a minimal fix**, then gradually migrate to **Option 2 (Pydantic everywhere)** for long-term:
