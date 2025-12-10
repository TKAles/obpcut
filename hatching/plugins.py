"""
Built-in hatching plugins.

This module contains example hatching plugin implementations.
"""

from typing import List, Tuple
import numpy as np

from .base import HatchingPlugin, HatchingParameters, HatchLine
from .utils import (
    get_bounding_box,
    create_polygon_from_contours,
    clip_line_to_polygon,
    sort_segments_for_scanning
)


class LineHatchingPlugin(HatchingPlugin):
    """
    Parallel line hatching plugin.

    Generates parallel hatch lines at a specified angle and spacing.
    This is the most common hatching strategy in additive manufacturing.
    """

    def __init__(self):
        super().__init__()
        self._name = "Line Hatching"
        self._description = "Generates parallel hatch lines with configurable angle and spacing"
        self._version = "1.0.0"

    def generate_hatching(
        self,
        contours: List[List[Tuple[float, float]]],
        parameters: HatchingParameters,
        layer_index: int = 0
    ) -> List[HatchLine]:
        """
        Generate parallel line hatching for a layer.

        Args:
            contours: List of contours (first is outer boundary, rest are holes)
            parameters: Hatching parameters
            layer_index: Layer number (used for rotation)

        Returns:
            List of HatchLine objects
        """
        if not contours or len(contours[0]) < 3:
            return []

        # Validate parameters
        if not self.validate_parameters(parameters):
            return []

        # Create polygon from contours
        polygon = create_polygon_from_contours(contours)
        if polygon is None or polygon.is_empty:
            return []

        # Apply border offset if specified
        if parameters.border_offset > 0:
            from .utils import offset_polygon
            offset_poly = offset_polygon(polygon, parameters.border_offset)
            if offset_poly is not None and not offset_poly.is_empty:
                polygon = offset_poly
            else:
                # Offset made polygon disappear, skip hatching
                return []

        # Generate contour lines if enabled
        hatch_lines = []
        if parameters.enable_contours:
            hatch_lines.extend(self.generate_contours(contours, parameters, layer_index))

        # Calculate effective hatch angle for this layer
        effective_angle = self.get_effective_angle(
            parameters.hatch_angle,
            layer_index,
            parameters.layer_rotation
        )

        # Generate hatch lines
        infill_lines = self._generate_parallel_lines(
            polygon,
            parameters.hatch_spacing,
            effective_angle,
            parameters,
            layer_index
        )

        hatch_lines.extend(infill_lines)

        # Optimize scan path if requested
        if parameters.optimize_path and len(hatch_lines) > 1:
            hatch_lines = self.optimize_scan_path(hatch_lines)

        return hatch_lines

    def _generate_parallel_lines(
        self,
        polygon,
        spacing: float,
        angle: float,
        parameters: HatchingParameters,
        layer_index: int
    ) -> List[HatchLine]:
        """
        Generate parallel hatch lines at a given angle.

        Args:
            polygon: Shapely Polygon to fill
            spacing: Distance between lines in mm
            angle: Hatch angle in degrees
            parameters: Hatching parameters
            layer_index: Layer number

        Returns:
            List of HatchLine objects
        """
        from shapely.affinity import rotate as shapely_rotate

        # Get bounding box
        bounds = polygon.bounds  # (minx, miny, maxx, maxy)
        minx, miny, maxx, maxy = bounds

        # Calculate the center
        center_x = (minx + maxx) / 2
        center_y = (miny + maxy) / 2

        # Rotate polygon to align with scanning direction (makes line generation easier)
        # We rotate backwards, so we can generate horizontal lines
        rotated_polygon = shapely_rotate(polygon, -angle, origin=(center_x, center_y))

        # Get new bounding box
        rot_bounds = rotated_polygon.bounds
        rot_minx, rot_miny, rot_maxx, rot_maxy = rot_bounds

        # Generate horizontal lines in rotated space
        segments = []
        y = rot_miny + spacing / 2  # Start with offset

        while y <= rot_maxy:
            # Create a horizontal line across the bounding box
            line_start = (rot_minx - 1, y)  # Extend slightly beyond bounds
            line_end = (rot_maxx + 1, y)

            # Clip line to polygon
            clipped_segments = clip_line_to_polygon(line_start, line_end, rotated_polygon)
            segments.extend(clipped_segments)

            y += spacing

        # Sort segments for efficient scanning
        if parameters.bidirectional:
            segments = sort_segments_for_scanning(segments, bidirectional=True)

        # Rotate segments back to original orientation
        hatch_lines = []
        for start, end in segments:
            # Rotate points back
            from .utils import rotate_point
            rotated_start = rotate_point(start, (center_x, center_y), angle)
            rotated_end = rotate_point(end, (center_x, center_y), angle)

            hatch_lines.append(HatchLine(
                start=rotated_start,
                end=rotated_end,
                speed=parameters.scan_speed,
                power=parameters.power_level,
                layer_index=layer_index,
                is_contour=False
            ))

        return hatch_lines


# Additional plugins can be added here following the same pattern
# Example structure for future plugins:
#
# class ZigzagHatchingPlugin(HatchingPlugin):
#     """Zigzag hatching - continuous back-and-forth pattern."""
#     def generate_hatching(self, contours, parameters, layer_index):
#         # Implementation here
#         pass
#
# class GridHatchingPlugin(HatchingPlugin):
#     """Grid hatching - crossed parallel lines."""
#     def generate_hatching(self, contours, parameters, layer_index):
#         # Implementation here
#         pass
