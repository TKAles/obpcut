"""
Integration utilities for connecting slicing to hatching system.

This module provides functions to convert between slice segments
and contour formats, and to integrate hatching generation with the
OpenGL visualization.
"""

from typing import List, Tuple, Dict, Any
import numpy as np


def segments_to_contours(segments: List[Tuple[float, float, float, float]]) -> List[List[Tuple[float, float]]]:
    """
    Convert slice segments to closed contours for hatching.

    Segments are in format (x1, z1, x2, z2). This function connects
    segments into closed polygons, handling both outer boundaries and holes.

    Args:
        segments: List of line segments from slicing

    Returns:
        List of contours, where each contour is a list of (x, y) points.
        First contour is outer boundary, subsequent contours are holes.
    """
    if not segments:
        return []

    # Build adjacency graph of connected points
    from collections import defaultdict

    # Use a tolerance for point matching
    tolerance = 1e-6

    def point_key(x, z):
        """Create a hashable key for a point with tolerance."""
        return (round(x / tolerance) * tolerance, round(z / tolerance) * tolerance)

    # Build graph: point -> list of connected points
    graph = defaultdict(list)
    edges = []

    for seg in segments:
        x1, z1, x2, z2 = seg
        p1 = point_key(x1, z1)
        p2 = point_key(x2, z2)

        graph[p1].append(p2)
        graph[p2].append(p1)
        edges.append((p1, p2))

    # Extract closed loops from graph
    contours = []
    visited_edges = set()

    def find_loop(start_point):
        """Find a closed loop starting from a point."""
        loop = [start_point]
        current = start_point
        visited_local = set()

        while True:
            # Find next unvisited neighbor
            next_point = None
            for neighbor in graph[current]:
                edge = (min(current, neighbor), max(current, neighbor))
                if edge not in visited_local:
                    next_point = neighbor
                    visited_local.add(edge)
                    visited_edges.add(edge)
                    break

            if next_point is None:
                break

            if next_point == start_point:
                # Closed loop found
                return loop

            loop.append(next_point)
            current = next_point

            if len(loop) > len(edges):
                # Safety check to prevent infinite loops
                break

        return None

    # Extract all loops
    for point in list(graph.keys()):
        if any((min(point, neighbor), max(point, neighbor)) not in visited_edges
               for neighbor in graph[point]):
            loop = find_loop(point)
            if loop and len(loop) >= 3:
                contours.append(loop)

    return contours


def group_contours_into_islands(contours: List[List[Tuple[float, float]]]) -> List[List[List[Tuple[float, float]]]]:
    """
    Group contours into separate islands, identifying which contours are holes.

    Args:
        contours: List of closed contours

    Returns:
        List of island groups, where each group is [outer_contour, hole1, hole2, ...]
    """
    if not contours:
        return []

    from shapely.geometry import Polygon, Point

    def contour_area(contour):
        """Calculate signed area of a contour using shoelace formula."""
        area = 0.0
        for i in range(len(contour)):
            j = (i + 1) % len(contour)
            area += contour[i][0] * contour[j][1]
            area -= contour[j][0] * contour[i][1]
        return area / 2.0

    def is_contour_inside(inner, outer):
        """Check if inner contour is inside outer contour."""
        try:
            outer_poly = Polygon(outer)
            # Check if a point from inner is inside outer
            if len(inner) > 0:
                point = Point(inner[0])
                return outer_poly.contains(point)
        except:
            pass
        return False

    # Calculate area for each contour (signed area tells us orientation)
    contours_with_area = [(c, contour_area(c)) for c in contours]

    # Separate into potential outer boundaries (CCW, positive area) and holes (CW, negative area)
    # But we need to be careful - just use absolute area for sorting
    contours_with_area.sort(key=lambda x: abs(x[1]), reverse=True)

    islands = []
    used = set()

    for i, (contour, area) in enumerate(contours_with_area):
        if i in used:
            continue

        # This is a potential outer boundary
        island = [contour]
        used.add(i)

        # Find all holes for this island
        for j, (other_contour, other_area) in enumerate(contours_with_area):
            if j in used:
                continue

            # Check if other_contour is a hole inside this island
            if is_contour_inside(other_contour, contour):
                island.append(other_contour)
                used.add(j)

        islands.append(island)

    return islands


def generate_hatching_for_layer(
    segments: List[Tuple[float, float, float, float]],
    layer_index: int,
    hatch_params: 'HatchingParameters',
    strategy: 'HatchingStrategy' = None
) -> List['HatchLine']:
    """
    Generate hatching for a single layer from slice segments.

    Args:
        segments: Slice segments [(x1, z1, x2, z2), ...]
        layer_index: Layer number
        hatch_params: Hatching parameters
        strategy: Hatching strategy to use (default: LINES)

    Returns:
        List of HatchLine objects
    """
    from hatching import registry, HatchingStrategy

    if strategy is None:
        strategy = HatchingStrategy.LINES

    # Convert segments to contours
    contours = segments_to_contours(segments)

    if not contours:
        return []

    # Group contours into separate islands (each with their holes)
    islands = group_contours_into_islands(contours)

    if not islands:
        return []

    # Get hatching plugin
    plugin = registry.get_plugin(strategy)
    if plugin is None:
        return []

    # Generate hatching for each island separately
    all_hatch_lines = []
    for island_contours in islands:
        # Generate hatching for this island
        hatch_lines = plugin.generate_hatching(island_contours, hatch_params, layer_index)
        all_hatch_lines.extend(hatch_lines)

    return all_hatch_lines


def prepare_hatching_for_all_layers(
    layer_sections: List[Dict[str, Any]],
    hatch_params: 'HatchingParameters',
    strategy: 'HatchingStrategy' = None,
    progress_callback=None
) -> Dict[int, List['HatchLine']]:
    """
    Generate hatching for all layer sections.

    Args:
        layer_sections: List of layer section dictionaries from slicing
        hatch_params: Hatching parameters
        strategy: Hatching strategy to use
        progress_callback: Optional callback(layer_idx, total_layers, message)

    Returns:
        Dictionary mapping layer_index -> list of HatchLine objects
    """
    from hatching import HatchingStrategy

    if strategy is None:
        strategy = HatchingStrategy.LINES

    hatching_data = {}

    # Count total layers
    total_layers = sum(section['layer_count'] for section in layer_sections)

    layer_idx = 0
    for section in layer_sections:
        # Generate hatching for this section
        # All layers in a section have the same outline, so we can reuse the hatching pattern
        segments = section['segments']

        # Generate hatching once for the section
        hatch_lines = generate_hatching_for_layer(
            segments,
            section['start_layer'],  # Use first layer index
            hatch_params,
            strategy
        )

        # Apply to all layers in the section
        for layer_offset in range(section['layer_count']):
            current_layer_idx = section['start_layer'] + layer_offset

            # Clone hatch lines and update layer index
            layer_hatch_lines = []
            for line in hatch_lines:
                from hatching import HatchLine
                new_line = HatchLine(
                    start=line.start,
                    end=line.end,
                    speed=line.speed,
                    power=line.power,
                    layer_index=current_layer_idx,
                    is_contour=line.is_contour
                )
                layer_hatch_lines.append(new_line)

            hatching_data[current_layer_idx] = layer_hatch_lines

            if progress_callback:
                progress_callback(layer_idx, total_layers, f"Generated hatching for layer {layer_idx}/{total_layers}")

            layer_idx += 1

    return hatching_data


def convert_hatching_to_obp_format(
    hatching_data: Dict[int, List['HatchLine']],
    layer_thickness: float
) -> List[Dict[str, Any]]:
    """
    Convert hatching data to OBP format for Freemelt export.

    Args:
        hatching_data: Dictionary mapping layer_index -> HatchLine list
        layer_thickness: Layer thickness in mm

    Returns:
        List of layer dictionaries in OBP format
    """
    obp_layers = []

    for layer_idx in sorted(hatching_data.keys()):
        hatch_lines = hatching_data[layer_idx]

        # Separate contours and infill
        contour_lines = [line for line in hatch_lines if line.is_contour]
        infill_lines = [line for line in hatch_lines if not line.is_contour]

        # Build layer data structure for OBP
        layer_data = {
            'layer_index': layer_idx,
            'z_height': layer_idx * layer_thickness,
            'thickness': layer_thickness,
            'contours': [],
            'infill': []
        }

        # Add contours
        for line in contour_lines:
            layer_data['contours'].append({
                'start': {'x': line.start[0], 'y': line.start[1]},
                'end': {'x': line.end[0], 'y': line.end[1]},
                'speed': line.speed if line.speed else 1000.0,
                'power': line.power if line.power else 1.0
            })

        # Add infill
        for line in infill_lines:
            layer_data['infill'].append({
                'start': {'x': line.start[0], 'y': line.start[1]},
                'end': {'x': line.end[0], 'y': line.end[1]},
                'speed': line.speed if line.speed else 1000.0,
                'power': line.power if line.power else 1.0
            })

        obp_layers.append(layer_data)

    return obp_layers


def estimate_build_time(hatching_data: Dict[int, List['HatchLine']]) -> float:
    """
    Estimate total build time from hatching data.

    Args:
        hatching_data: Dictionary mapping layer_index -> HatchLine list

    Returns:
        Estimated build time in seconds
    """
    total_time = 0.0

    for layer_idx, hatch_lines in hatching_data.items():
        for line in hatch_lines:
            if line.speed and line.speed > 0:
                distance = line.length()
                time = distance / line.speed  # seconds
                total_time += time

    return total_time


def get_hatching_statistics(hatching_data: Dict[int, List['HatchLine']]) -> Dict[str, Any]:
    """
    Calculate statistics about generated hatching.

    Args:
        hatching_data: Dictionary mapping layer_index -> HatchLine list

    Returns:
        Dictionary with statistics
    """
    total_lines = 0
    total_contour_lines = 0
    total_infill_lines = 0
    total_scan_length = 0.0
    total_contour_length = 0.0
    total_infill_length = 0.0

    for layer_idx, hatch_lines in hatching_data.items():
        for line in hatch_lines:
            length = line.length()
            total_lines += 1
            total_scan_length += length

            if line.is_contour:
                total_contour_lines += 1
                total_contour_length += length
            else:
                total_infill_lines += 1
                total_infill_length += length

    stats = {
        'total_layers': len(hatching_data),
        'total_lines': total_lines,
        'contour_lines': total_contour_lines,
        'infill_lines': total_infill_lines,
        'total_scan_length_mm': total_scan_length,
        'contour_length_mm': total_contour_length,
        'infill_length_mm': total_infill_length,
        'estimated_time_seconds': estimate_build_time(hatching_data),
        'avg_lines_per_layer': total_lines / len(hatching_data) if hatching_data else 0
    }

    return stats
