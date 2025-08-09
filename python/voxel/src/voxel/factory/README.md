# Spinner - Object Building and Dependency Resolution

The spinner package provides a powerful system for building complex object graphs with automatic dependency resolution.
It's designed to create objects from specifications while handling dependencies and error reporting.

## Core Components

- **`BuildSpec`** - Defines how to build an object (target class, args, kwargs)
- **`ObjectBuilder`** - Builds single objects from specifications
- **`GraphBuilder`** - Builds collections of interdependent objects
- **`Spinner`** - Loads specifications from JSON/dict sources

### Built-in Stores

- **`DictSpecStore`** - In-memory dictionary store
- **`JSONSpecStore`** - JSON file store
- **`YAMLSpecStore`** - YAML file store

## Key Features

- **Dependency Resolution** - Automatically resolves object references in specifications
- **Error Handling** - Structured error reporting with detailed diagnostics
- **Circular Dependency Detection** - Prevents infinite loops during building
- **Type Validation** - Ensures built objects match expected base classes
- **Auto-injection** - Injects object names as `uid` parameters when required

## Quick Start

### Single Object Building

Start with the simplest case - building one object with `ObjectBuilder`:

```python
from spinner import ObjectBuilder, BuildSpec

# Define what to build
spec = BuildSpec(target="mymodule.Engine", kwargs={"power": 200})

# Build it
builder = ObjectBuilder(spec)
engine = builder.build()
```

### Multiple Objects with Dependencies

For multiple objects that reference each other, use `Spinner`:

```python
from spinner import Spinner

# Multiple objects with dependencies
specs = {
    "engine": {
        "target": "mymodule.Engine",
        "kwargs": {"power": 200}
    },
    "car": {
        "target": "mymodule.Car",
        "kwargs": {
            "engine": "engine",  # Reference to engine object
            "model": "Tesla"
        }
    }
}

factory = Spinner.from_dict(specs)
objects, errors = factory.load_and_build()
```

```python
# From a JSON file
factory = Spinner.from_json_file("config.json")
objects, errors = factory.load_and_build()
```

### Advanced Usage - Step by Step

For more control, you can load specs and build separately:

```python
from spinner import ObjectBuilder, BuildSpec, GraphBuilder

# Single object
spec = BuildSpec(target="mymodule.Engine", kwargs={"power": 200})
builder = ObjectBuilder(spec)
engine = builder.build()

# Collection with dependencies
specs = {
    "engine": BuildSpec(target="mymodule.Engine", kwargs={"power": 200}),
    "car": BuildSpec(target="mymodule.Car", kwargs={
        "engine": "engine",  # Reference to engine object
        "model": "Tesla"
    })
}

builder = GraphBuilder(specs)
objects, errors = builder.build()
```

### Working with Stores

For more advanced scenarios, you can work with stores directly:

```python
from spinner import DictSpecStore, Spinner, GraphBuilder

# Using stores directly
store = DictSpecStore(specs_dict)
factory = Spinner(store)
specs, errors = factory.load()

# Then build if no errors
if not errors:
    builder = GraphBuilder(specs)
    objects, build_errors = builder.build()
```

### Error Reporting

```python
from spinner.utils import print_build_results

# Clean, formatted output of build results
print_build_results(objects, errors, "Build Results")
```

## Auto-injection

When a class constructor has a required `uid` parameter (no default value), the spinner automatically injects the
 object's name from the specification:

```python
class Component:
    def __init__(self, config: str, uid: str):  # No default for uid
        self.config = config
        self.uid = uid

specs = {
    "my_component": BuildSpec(target="Component", kwargs={"config": "test"})
}
# Result: Component with uid="my_component"
```

## Examples

See `/examples/spinner/` for comprehensive demonstrations:

- `01_objectbuilder_basics.py` - Single object building
- `02_graph_builder_basics.py` - Dependencies and auto-injection
- `03_json_loading.py` - External configuration
- `04_error_handling.py` - Error scenarios
- `05_bike_demo.py` - Real-world example
