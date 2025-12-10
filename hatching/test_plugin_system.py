#!/usr/bin/env python3
"""
Simple tests for the hatching plugin system.

Run with: python -m pytest hatching/test_plugin_system.py
Or: python hatching/test_plugin_system.py
"""

import sys
from typing import List, Tuple

# Test the plugin system
def test_registry_singleton():
    """Test that registry is a singleton."""
    from hatching.registry import HatchingRegistry

    r1 = HatchingRegistry()
    r2 = HatchingRegistry()

    assert r1 is r2, "Registry should be a singleton"
    print("✓ Registry singleton test passed")


def test_plugin_registration():
    """Test plugin registration and retrieval."""
    from hatching import registry, HatchingStrategy, LineHatchingPlugin

    # Should be auto-registered
    assert registry.is_registered(HatchingStrategy.LINES), "LINES should be auto-registered"

    # Get plugin
    plugin = registry.get_plugin(HatchingStrategy.LINES)
    assert plugin is not None, "Should retrieve plugin"
    assert isinstance(plugin, LineHatchingPlugin), "Should be LineHatchingPlugin instance"

    print("✓ Plugin registration test passed")


def test_list_strategies():
    """Test listing registered strategies."""
    from hatching import registry, HatchingStrategy

    strategies = registry.list_strategies()
    assert HatchingStrategy.LINES in strategies, "LINES should be in registered strategies"
    assert len(strategies) >= 1, "Should have at least one strategy"

    print(f"✓ List strategies test passed (found {len(strategies)} strategies)")


def test_basic_hatching():
    """Test basic hatching generation."""
    from hatching import registry, HatchingStrategy, HatchingParameters

    # Simple square
    square = [(0, 0), (10, 0), (10, 10), (0, 10)]
    contours = [square]

    # Get plugin
    plugin = registry.get_plugin(HatchingStrategy.LINES)

    # Generate hatching
    params = HatchingParameters(
        hatch_spacing=1.0,
        hatch_angle=0,
        enable_contours=True,
        bidirectional=True
    )

    hatch_lines = plugin.generate_hatching(contours, params, layer_index=0)

    assert len(hatch_lines) > 0, "Should generate hatch lines"

    # Check that we have both contour and infill lines
    contour_count = sum(1 for line in hatch_lines if line.is_contour)
    infill_count = sum(1 for line in hatch_lines if not line.is_contour)

    assert contour_count > 0, "Should have contour lines"
    assert infill_count > 0, "Should have infill lines"

    print(f"✓ Basic hatching test passed ({len(hatch_lines)} lines: {contour_count} contours, {infill_count} infill)")


def test_hatching_with_hole():
    """Test hatching with inner contour (hole)."""
    from hatching import registry, HatchingStrategy, HatchingParameters

    # Outer square
    outer = [(0, 0), (20, 0), (20, 20), (0, 20)]
    # Inner square (hole)
    inner = [(5, 5), (15, 5), (15, 15), (5, 15)]

    contours = [outer, inner]

    plugin = registry.get_plugin(HatchingStrategy.LINES)
    params = HatchingParameters(
        hatch_spacing=1.0,
        hatch_angle=0,
        enable_contours=False,  # Only test infill
        bidirectional=True
    )

    hatch_lines = plugin.generate_hatching(contours, params, layer_index=0)

    assert len(hatch_lines) > 0, "Should generate hatch lines"

    # All should be infill (no contours)
    assert all(not line.is_contour for line in hatch_lines), "All lines should be infill"

    print(f"✓ Hatching with hole test passed ({len(hatch_lines)} lines)")


def test_layer_rotation():
    """Test layer rotation."""
    from hatching import registry, HatchingStrategy, HatchingParameters

    square = [(0, 0), (10, 0), (10, 10), (0, 10)]
    contours = [square]

    plugin = registry.get_plugin(HatchingStrategy.LINES)
    params = HatchingParameters(
        hatch_spacing=1.0,
        hatch_angle=0,
        layer_rotation=90,  # 90 degree rotation per layer
        enable_contours=False
    )

    # Generate for two layers
    lines_layer0 = plugin.generate_hatching(contours, params, layer_index=0)
    lines_layer1 = plugin.generate_hatching(contours, params, layer_index=1)

    # Both should generate lines
    assert len(lines_layer0) > 0, "Layer 0 should have lines"
    assert len(lines_layer1) > 0, "Layer 1 should have lines"

    # Lines should be at different angles
    # (This is a simple check - just verify they're different)
    angle0 = lines_layer0[0].angle() if len(lines_layer0) > 0 else 0
    angle1 = lines_layer1[0].angle() if len(lines_layer1) > 0 else 0

    # Allow for some numerical tolerance
    assert abs(angle0 - angle1) > 45, f"Angles should differ significantly ({angle0:.1f}° vs {angle1:.1f}°)"

    print(f"✓ Layer rotation test passed (angle diff: {abs(angle0 - angle1):.1f}°)")


def test_parameter_validation():
    """Test parameter validation."""
    from hatching import registry, HatchingStrategy, HatchingParameters

    plugin = registry.get_plugin(HatchingStrategy.LINES)

    # Valid parameters
    valid_params = HatchingParameters(hatch_spacing=0.5, power_level=0.8)
    assert plugin.validate_parameters(valid_params), "Valid params should pass"

    # Invalid spacing
    invalid_params = HatchingParameters(hatch_spacing=0, power_level=0.8)
    assert not plugin.validate_parameters(invalid_params), "Zero spacing should fail"

    # Invalid power
    invalid_params = HatchingParameters(hatch_spacing=0.5, power_level=1.5)
    assert not plugin.validate_parameters(invalid_params), "Power > 1 should fail"

    print("✓ Parameter validation test passed")


def test_custom_plugin():
    """Test creating and using a custom plugin."""
    from hatching import HatchingPlugin, HatchingParameters, HatchLine, registry, HatchingStrategy
    from typing import List, Tuple

    class TestPlugin(HatchingPlugin):
        """Simple test plugin that generates a single diagonal line."""

        def generate_hatching(
            self,
            contours: List[List[Tuple[float, float]]],
            parameters: HatchingParameters,
            layer_index: int = 0
        ) -> List[HatchLine]:
            """Generate a single diagonal line."""
            if not contours or len(contours[0]) < 2:
                return []

            # Just create a single diagonal line from bottom-left to top-right
            return [HatchLine(
                start=(0, 0),
                end=(10, 10),
                speed=parameters.scan_speed,
                power=parameters.power_level,
                layer_index=layer_index,
                is_contour=False
            )]

    # Register custom plugin
    registry.register(HatchingStrategy.SPIRAL, TestPlugin)

    # Use it
    plugin = registry.get_plugin(HatchingStrategy.SPIRAL)
    assert plugin is not None, "Should retrieve custom plugin"

    params = HatchingParameters()
    square = [(0, 0), (10, 0), (10, 10), (0, 10)]
    lines = plugin.generate_hatching([square], params, 0)

    assert len(lines) == 1, "Should generate one line"
    assert lines[0].start == (0, 0), "Start should be (0, 0)"
    assert lines[0].end == (10, 10), "End should be (10, 10)"

    # Clean up
    registry.unregister(HatchingStrategy.SPIRAL)

    print("✓ Custom plugin test passed")


def test_utility_functions():
    """Test utility functions."""
    from hatching.utils import (
        get_bounding_box,
        create_polygon_from_contours,
        rotate_point
    )
    import math

    # Test bounding box
    square = [(0, 0), (10, 0), (10, 10), (0, 10)]
    bbox = get_bounding_box([square])
    assert bbox == (0, 0, 10, 10), f"Bounding box should be (0, 0, 10, 10), got {bbox}"

    # Test polygon creation
    polygon = create_polygon_from_contours([square])
    assert polygon is not None, "Should create polygon"
    assert polygon.is_valid, "Polygon should be valid"
    assert abs(polygon.area - 100) < 0.1, f"Area should be ~100, got {polygon.area}"

    # Test point rotation
    point = (1, 0)
    center = (0, 0)
    rotated = rotate_point(point, center, 90)
    # After 90° rotation, (1, 0) should be approximately (0, 1)
    assert abs(rotated[0] - 0) < 0.01, f"X should be ~0, got {rotated[0]}"
    assert abs(rotated[1] - 1) < 0.01, f"Y should be ~1, got {rotated[1]}"

    print("✓ Utility functions test passed")


def run_all_tests():
    """Run all tests."""
    tests = [
        test_registry_singleton,
        test_plugin_registration,
        test_list_strategies,
        test_basic_hatching,
        test_hatching_with_hole,
        test_layer_rotation,
        test_parameter_validation,
        test_custom_plugin,
        test_utility_functions,
    ]

    print("\n" + "=" * 60)
    print("Running Hatching Plugin System Tests")
    print("=" * 60 + "\n")

    failed = []

    for test in tests:
        try:
            test()
        except AssertionError as e:
            print(f"✗ {test.__name__} failed: {e}")
            failed.append(test.__name__)
        except Exception as e:
            print(f"✗ {test.__name__} error: {e}")
            failed.append(test.__name__)

    print("\n" + "=" * 60)
    if failed:
        print(f"FAILED: {len(failed)}/{len(tests)} tests failed")
        for name in failed:
            print(f"  - {name}")
        return 1
    else:
        print(f"SUCCESS: All {len(tests)} tests passed!")
    print("=" * 60 + "\n")

    return 0


if __name__ == '__main__':
    sys.exit(run_all_tests())
