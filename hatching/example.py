#!/usr/bin/env python3
"""
Example script demonstrating the hatching plugin system.

This script shows how to:
1. Use the built-in LineHatchingPlugin
2. Create a custom hatching plugin
3. Register plugins with the registry
4. Generate hatching patterns
"""

import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from typing import List, Tuple

from hatching import (
    registry,
    HatchingStrategy,
    HatchingParameters,
    HatchingPlugin,
    HatchLine,
    LineHatchingPlugin
)


def visualize_hatching(hatch_lines: List[HatchLine], title: str = "Hatching Pattern"):
    """
    Visualize hatching lines using matplotlib.

    Args:
        hatch_lines: List of HatchLine objects to visualize
        title: Plot title
    """
    fig, ax = plt.subplots(figsize=(10, 10))

    # Separate contour and infill lines
    contour_lines = [line for line in hatch_lines if line.is_contour]
    infill_lines = [line for line in hatch_lines if not line.is_contour]

    # Plot infill lines
    if infill_lines:
        infill_segments = [[(line.start[0], line.start[1]), (line.end[0], line.end[1])]
                          for line in infill_lines]
        infill_collection = LineCollection(infill_segments, colors='blue', linewidths=0.5, label='Infill')
        ax.add_collection(infill_collection)

    # Plot contour lines
    if contour_lines:
        contour_segments = [[(line.start[0], line.start[1]), (line.end[0], line.end[1])]
                           for line in contour_lines]
        contour_collection = LineCollection(contour_segments, colors='red', linewidths=1.5, label='Contour')
        ax.add_collection(contour_collection)

    # Set axis properties
    ax.autoscale()
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.3)
    ax.set_xlabel('X (mm)')
    ax.set_ylabel('Y (mm)')
    ax.set_title(title)
    ax.legend()

    plt.tight_layout()
    plt.show()


def example_1_basic_square():
    """Example 1: Basic square with line hatching."""
    print("=" * 60)
    print("Example 1: Basic Square with Line Hatching")
    print("=" * 60)

    # Define a simple square contour
    square = [(0, 0), (10, 0), (10, 10), (0, 10)]
    contours = [square]

    # Get the line hatching plugin
    plugin = registry.get_plugin(HatchingStrategy.LINES)

    # Set parameters
    params = HatchingParameters(
        hatch_spacing=0.5,
        hatch_angle=45,
        enable_contours=True,
        scan_speed=1000,
        power_level=1.0
    )

    # Generate hatching
    hatch_lines = plugin.generate_hatching(contours, params, layer_index=0)

    print(f"Generated {len(hatch_lines)} hatch lines")
    print(f"  - Contours: {sum(1 for l in hatch_lines if l.is_contour)}")
    print(f"  - Infill: {sum(1 for l in hatch_lines if not l.is_contour)}")

    # Visualize
    visualize_hatching(hatch_lines, "Example 1: Square with 45° Line Hatching")


def example_2_square_with_hole():
    """Example 2: Square with a hole (inner contour)."""
    print("\n" + "=" * 60)
    print("Example 2: Square with Hole")
    print("=" * 60)

    # Outer square
    outer = [(0, 0), (20, 0), (20, 20), (0, 20)]

    # Inner square (hole)
    inner = [(7, 7), (13, 7), (13, 13), (7, 13)]

    contours = [outer, inner]

    # Get plugin
    plugin = registry.get_plugin(HatchingStrategy.LINES)

    # Parameters
    params = HatchingParameters(
        hatch_spacing=0.8,
        hatch_angle=0,
        enable_contours=True,
        bidirectional=True
    )

    # Generate hatching
    hatch_lines = plugin.generate_hatching(contours, params, layer_index=0)

    print(f"Generated {len(hatch_lines)} hatch lines")

    # Visualize
    visualize_hatching(hatch_lines, "Example 2: Square with Hole (Horizontal Hatching)")


def example_3_layer_rotation():
    """Example 3: Demonstrate layer rotation."""
    print("\n" + "=" * 60)
    print("Example 3: Layer Rotation")
    print("=" * 60)

    # Circle approximation
    import numpy as np
    angles = np.linspace(0, 2 * np.pi, 32, endpoint=False)
    radius = 10
    circle = [(radius * np.cos(a), radius * np.sin(a)) for a in angles]
    contours = [circle]

    # Get plugin
    plugin = registry.get_plugin(HatchingStrategy.LINES)

    # Generate multiple layers with rotation
    params = HatchingParameters(
        hatch_spacing=0.6,
        hatch_angle=0,
        layer_rotation=67,  # Rotate by 67° each layer
        enable_contours=False,
        bidirectional=True
    )

    # Generate 3 layers
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    for layer_idx in range(3):
        hatch_lines = plugin.generate_hatching(contours, params, layer_index=layer_idx)

        print(f"Layer {layer_idx}: {len(hatch_lines)} lines, angle = {layer_idx * 67}°")

        # Plot
        ax = axes[layer_idx]
        segments = [[(line.start[0], line.start[1]), (line.end[0], line.end[1])]
                   for line in hatch_lines]
        collection = LineCollection(segments, colors='blue', linewidths=0.5)
        ax.add_collection(collection)
        ax.autoscale()
        ax.set_aspect('equal')
        ax.grid(True, alpha=0.3)
        ax.set_title(f'Layer {layer_idx} ({layer_idx * 67}°)')

    plt.tight_layout()
    plt.show()


def example_4_custom_plugin():
    """Example 4: Create and use a custom hatching plugin."""
    print("\n" + "=" * 60)
    print("Example 4: Custom Hatching Plugin")
    print("=" * 60)

    # Define a custom plugin
    class CrossHatchPlugin(HatchingPlugin):
        """Simple cross-hatch plugin (0° + 90° lines)."""

        def __init__(self):
            super().__init__()
            self._name = "Cross Hatch"
            self._description = "Perpendicular crossed lines"

        def generate_hatching(
            self,
            contours: List[List[Tuple[float, float]]],
            parameters: HatchingParameters,
            layer_index: int = 0
        ) -> List[HatchLine]:
            """Generate cross-hatching."""
            # Use the line plugin twice with different angles
            line_plugin = LineHatchingPlugin()

            # First set of lines at 0°
            params1 = HatchingParameters(
                hatch_spacing=parameters.hatch_spacing,
                hatch_angle=0,
                enable_contours=False,
                scan_speed=parameters.scan_speed,
                power_level=parameters.power_level,
                bidirectional=parameters.bidirectional
            )
            lines1 = line_plugin.generate_hatching(contours, params1, layer_index)

            # Second set at 90°
            params2 = HatchingParameters(
                hatch_spacing=parameters.hatch_spacing,
                hatch_angle=90,
                enable_contours=False,
                scan_speed=parameters.scan_speed,
                power_level=parameters.power_level,
                bidirectional=parameters.bidirectional
            )
            lines2 = line_plugin.generate_hatching(contours, params2, layer_index)

            # Combine
            all_lines = lines1 + lines2

            # Add contours if requested
            if parameters.enable_contours:
                all_lines.extend(self.generate_contours(contours, parameters, layer_index))

            return all_lines

    # Register the custom plugin
    registry.register(HatchingStrategy.GRID, CrossHatchPlugin)
    print("Custom CrossHatchPlugin registered!")

    # Use it
    square = [(0, 0), (15, 0), (15, 15), (0, 15)]
    contours = [square]

    plugin = registry.get_plugin(HatchingStrategy.GRID)
    params = HatchingParameters(
        hatch_spacing=1.0,
        enable_contours=True
    )

    hatch_lines = plugin.generate_hatching(contours, params, layer_index=0)
    print(f"Generated {len(hatch_lines)} hatch lines")

    visualize_hatching(hatch_lines, "Example 4: Custom Cross-Hatch Pattern")


def example_5_registry_management():
    """Example 5: Registry management operations."""
    print("\n" + "=" * 60)
    print("Example 5: Registry Management")
    print("=" * 60)

    # List registered strategies
    print(f"Registered strategies: {registry.list_strategies()}")
    print(f"Total plugins: {len(registry)}")

    # Check if a strategy is registered
    print(f"LINES registered: {registry.is_registered(HatchingStrategy.LINES)}")
    print(f"SPIRAL registered: {registry.is_registered(HatchingStrategy.SPIRAL)}")

    # Get plugin info
    plugin = registry.get_plugin(HatchingStrategy.LINES)
    if plugin:
        print(f"\nLINES plugin info:")
        print(f"  Name: {plugin.name}")
        print(f"  Description: {plugin.description}")
        print(f"  Version: {plugin.version}")


def main():
    """Run all examples."""
    print("\nHatching Plugin System Examples")
    print("================================\n")

    # Run examples
    example_1_basic_square()
    example_2_square_with_hole()
    example_3_layer_rotation()
    example_4_custom_plugin()
    example_5_registry_management()

    print("\n" + "=" * 60)
    print("All examples completed!")
    print("=" * 60)


if __name__ == '__main__':
    # Note: You may need to install matplotlib for visualization
    # pip install matplotlib shapely

    try:
        main()
    except ImportError as e:
        print(f"Error: Missing dependency - {e}")
        print("Please install required packages: pip install matplotlib shapely numpy")
