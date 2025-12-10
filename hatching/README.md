# Hatching Plugin System

A flexible, extensible plugin system for generating hatching patterns in additive manufacturing applications.

## Overview

This plugin system provides a modular architecture for implementing various hatching strategies used in 3D printing, powder bed fusion (SLM/SLS), and other layer-based manufacturing processes.

## Architecture

The system consists of four main components:

1. **Base Classes** (`base.py`): Abstract interfaces and data structures
2. **Registry** (`registry.py`): Plugin management and discovery
3. **Utilities** (`utils.py`): Geometric operations and helper functions
4. **Plugins** (`plugins.py`): Concrete hatching implementations

## Quick Start

```python
from hatching import registry, HatchingStrategy, HatchingParameters

# Get a plugin
plugin = registry.get_plugin(HatchingStrategy.LINES)

# Define geometry (outer contour, optional inner holes)
contours = [
    [(0, 0), (10, 0), (10, 10), (0, 10)]  # Outer square
]

# Set parameters
params = HatchingParameters(
    hatch_spacing=0.5,      # Distance between lines in mm
    hatch_angle=45,         # Hatch angle in degrees
    layer_rotation=67,      # Rotation per layer
    enable_contours=True,   # Include boundary lines
    scan_speed=1000,        # Scan speed in mm/s
    power_level=1.0         # Power level (0-1)
)

# Generate hatching
hatch_lines = plugin.generate_hatching(contours, params, layer_index=0)

# Use the results
for line in hatch_lines:
    print(f"Line from {line.start} to {line.end}")
    print(f"  Speed: {line.speed} mm/s, Power: {line.power}")
```

## Core Concepts

### Hatching Strategies

Predefined strategies in `HatchingStrategy` enum:
- `LINES` - Parallel line hatching (implemented)
- `ZIGZAG` - Continuous back-and-forth pattern
- `GRID` - Crossed parallel lines
- `HONEYCOMB` - Hexagonal pattern
- `CONCENTRIC` - Offset contours spiraling inward
- `HILBERT` - Space-filling Hilbert curve
- `SPIRAL` - Spiral pattern from outside to center
- `ADAPTIVE` - Density-based adaptive hatching

### Data Structures

#### HatchLine
Represents a single hatch line segment:
```python
@dataclass
class HatchLine:
    start: Tuple[float, float]        # Starting point (x, y) in mm
    end: Tuple[float, float]          # Ending point (x, y) in mm
    speed: Optional[float] = None     # Scan speed in mm/s
    power: Optional[float] = None     # Power level 0-1
    layer_index: int = 0              # Layer number
    is_contour: bool = False          # Contour vs infill
```

#### HatchingParameters
Configuration for hatching generation:
```python
@dataclass
class HatchingParameters:
    hatch_spacing: float = 0.1        # Distance between lines (mm)
    hatch_angle: float = 0.0          # Base angle (degrees)
    layer_rotation: float = 67.0      # Rotation per layer (degrees)
    border_offset: float = 0.0        # Offset from contour (mm)
    enable_contours: bool = True      # Include contour lines
    contour_count: int = 1            # Number of contour passes
    scan_speed: float = 1000.0        # Scan speed (mm/s)
    power_level: float = 1.0          # Power level (0-1)
    enable_skywriting: bool = True    # Beam off during jumps
    jump_speed: float = 5000.0        # Non-printing speed (mm/s)
    infill_density: float = 1.0       # Fill density (0-1)
    min_feature_size: float = 0.05    # Minimum feature (mm)
    optimize_path: bool = True        # Optimize scan path
    bidirectional: bool = True        # Alternate scan direction
    custom_params: Dict[str, Any]     # Strategy-specific params
```

## Creating Custom Plugins

### Basic Plugin

```python
from hatching import HatchingPlugin, HatchingParameters, HatchLine
from typing import List, Tuple

class MyCustomPlugin(HatchingPlugin):
    def __init__(self):
        super().__init__()
        self._name = "My Custom Hatch"
        self._description = "Custom hatching strategy"
        self._version = "1.0.0"

    def generate_hatching(
        self,
        contours: List[List[Tuple[float, float]]],
        parameters: HatchingParameters,
        layer_index: int = 0
    ) -> List[HatchLine]:
        """Generate custom hatching pattern."""

        # Validate parameters
        if not self.validate_parameters(parameters):
            return []

        hatch_lines = []

        # Your custom hatching logic here
        # ...

        # Optionally add contours
        if parameters.enable_contours:
            hatch_lines.extend(
                self.generate_contours(contours, parameters, layer_index)
            )

        # Optionally optimize path
        if parameters.optimize_path:
            hatch_lines = self.optimize_scan_path(hatch_lines)

        return hatch_lines
```

### Register Your Plugin

```python
from hatching import registry, HatchingStrategy

# Register with an existing strategy
registry.register(HatchingStrategy.SPIRAL, MyCustomPlugin)

# Or define a custom strategy enum value
# (requires extending HatchingStrategy enum)
```

## Utility Functions

The `utils.py` module provides helpful geometric operations:

- `get_bounding_box(contours)` - Calculate bounding box
- `create_polygon_from_contours(contours)` - Create Shapely polygon
- `clip_line_to_polygon(start, end, polygon)` - Clip line to polygon
- `rotate_point(point, center, angle)` - Rotate point around center
- `offset_polygon(polygon, offset)` - Inward/outward offset
- `sort_segments_for_scanning(segments, bidirectional)` - Optimize scan order
- `line_intersection(p1, p2, p3, p4)` - Find line intersection
- `simplify_contour(contour, tolerance)` - Simplify contour

## Built-in Plugins

### LineHatchingPlugin

Generates parallel hatch lines at specified angle and spacing.

**Features:**
- Configurable hatch angle and spacing
- Layer-by-layer rotation
- Border offset support
- Bidirectional scanning
- Path optimization

**Example:**
```python
from hatching import registry, HatchingStrategy, HatchingParameters

plugin = registry.get_plugin(HatchingStrategy.LINES)

params = HatchingParameters(
    hatch_spacing=0.5,
    hatch_angle=45,
    layer_rotation=67,
    bidirectional=True,
    optimize_path=True
)

hatch_lines = plugin.generate_hatching(contours, params, layer_index=0)
```

## Registry API

### Register Plugin
```python
registry.register(HatchingStrategy.LINES, MyPlugin)
```

### Get Plugin Instance
```python
plugin = registry.get_plugin(HatchingStrategy.LINES)
```

### Get Plugin Class
```python
PluginClass = registry.get_plugin_class(HatchingStrategy.LINES)
```

### List Strategies
```python
strategies = registry.list_strategies()
```

### Check Registration
```python
if registry.is_registered(HatchingStrategy.LINES):
    plugin = registry.get_plugin(HatchingStrategy.LINES)
```

### Unregister
```python
registry.unregister(HatchingStrategy.LINES)
```

## Examples

See `example.py` for comprehensive examples including:

1. Basic square with line hatching
2. Square with hole (multiple contours)
3. Layer rotation demonstration
4. Creating custom plugins
5. Registry management

Run examples:
```bash
python hatching/example.py
```

## Dependencies

Required:
- `numpy` - Numerical operations
- `shapely` - Geometric operations

Optional (for examples):
- `matplotlib` - Visualization

Install:
```bash
pip install numpy shapely matplotlib
```

## Extending the System

### Adding New Strategies

1. Define your plugin class inheriting from `HatchingPlugin`
2. Implement `generate_hatching()` method
3. Register with the registry
4. Use like any other plugin

### Advanced Features

The base `HatchingPlugin` class provides helper methods:

- `validate_parameters(params)` - Parameter validation
- `optimize_scan_path(lines)` - Greedy nearest-neighbor optimization
- `get_effective_angle(base, layer, rotation)` - Calculate layer angle
- `generate_contours(contours, params, layer)` - Generate boundary lines

Override these methods for custom behavior.

## Best Practices

1. **Validate Parameters**: Always call `validate_parameters()` before processing
2. **Handle Edge Cases**: Check for empty contours, invalid polygons
3. **Optimize Paths**: Use `optimize_scan_path()` to reduce travel time
4. **Use Utilities**: Leverage `utils.py` functions for geometric operations
5. **Document**: Provide clear name, description, and version in your plugin
6. **Test**: Test with various contour shapes, including holes and complex geometries

## Thread Safety

The registry uses a singleton pattern. While generally safe for read operations, avoid concurrent registration/unregistration from multiple threads.

## Performance Considerations

- Use `optimize_path=True` to minimize scan time
- Consider `bidirectional=True` for faster scanning
- Larger `hatch_spacing` reduces computation and scan time
- Complex contours with many points may benefit from simplification

## Future Enhancements

The following strategies are planned for future implementation:
- Zigzag hatching
- Grid/cross-hatch
- Honeycomb pattern
- Concentric offset
- Hilbert curve
- Spiral pattern
- Adaptive density hatching

Contributions are welcome!

## License

This plugin system is part of the OBPCut project.
