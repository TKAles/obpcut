"""
Hatching plugin system for generating infill and support patterns.

This package provides a plugin-based architecture for various hatching strategies
used in additive manufacturing (3D printing, powder bed fusion, etc.).

Usage:
    from hatching import registry, HatchingStrategy, HatchingParameters
    from hatching.plugins import LineHatchingPlugin

    # Register a plugin
    registry.register(HatchingStrategy.LINES, LineHatchingPlugin)

    # Get a plugin instance
    plugin = registry.get_plugin(HatchingStrategy.LINES)

    # Generate hatching
    contours = [[(0, 0), (10, 0), (10, 10), (0, 10)]]
    params = HatchingParameters(hatch_spacing=0.5, hatch_angle=45)
    hatch_lines = plugin.generate_hatching(contours, params, layer_index=0)
"""

from .base import HatchingPlugin, HatchingParameters, HatchLine, HatchingStrategy
from .registry import HatchingRegistry, registry
from .plugins import LineHatchingPlugin

# Auto-register built-in plugins
registry.register(HatchingStrategy.LINES, LineHatchingPlugin)

__all__ = [
    'HatchingPlugin',
    'HatchingParameters',
    'HatchLine',
    'HatchingStrategy',
    'HatchingRegistry',
    'registry',
    'LineHatchingPlugin',
]
