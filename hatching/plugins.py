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
        from shapely.geometry import MultiLineString

        # Get bounding box
        bounds = polygon.bounds  # (minx, miny, maxx, maxy)
        minx, miny, maxx, maxy = bounds

        # Calculate the center
        center_x = (minx + maxx) / 2
        center_y = (miny + maxy) / 2

        # Rotate polygon to align with scanning direction (makes line generation easier)
        rotated_polygon = shapely_rotate(polygon, -angle, origin=(center_x, center_y))

        # Get new bounding box
        rot_bounds = rotated_polygon.bounds
        rot_minx, rot_miny, rot_maxx, rot_maxy = rot_bounds

        # Build all scan lines at once using np.arange, then do a single intersection call
        ys = np.arange(rot_miny + spacing / 2, rot_maxy + 1e-10, spacing)
        if len(ys) == 0:
            return []

        scan_lines = [((rot_minx - 1, y), (rot_maxx + 1, y)) for y in ys]
        multi_line = MultiLineString(scan_lines)

        # Single intersection call instead of one per scan line
        intersection = multi_line.intersection(rotated_polygon)
        if intersection.is_empty:
            return []

        # Extract segments from result
        segments = []
        geoms = intersection.geoms if hasattr(intersection, 'geoms') else [intersection]
        for geom in geoms:
            if geom.geom_type == 'LineString':
                coords = list(geom.coords)
                if len(coords) >= 2:
                    segments.append((coords[0], coords[-1]))

        if not segments:
            return []

        # Sort segments for efficient scanning
        if parameters.bidirectional:
            segments = sort_segments_for_scanning(segments, bidirectional=True)

        # Vectorized rotation of all endpoints back to original orientation
        angle_rad = np.radians(angle)
        cos_a = np.cos(angle_rad)
        sin_a = np.sin(angle_rad)

        pts_start = np.array([s[0] for s in segments])
        pts_end = np.array([s[1] for s in segments])

        def _rotate_batch(pts):
            dx = pts[:, 0] - center_x
            dy = pts[:, 1] - center_y
            return np.column_stack([
                dx * cos_a - dy * sin_a + center_x,
                dx * sin_a + dy * cos_a + center_y,
            ])

        r_starts = _rotate_batch(pts_start)
        r_ends = _rotate_batch(pts_end)

        return [
            HatchLine(
                start=(float(r_starts[i, 0]), float(r_starts[i, 1])),
                end=(float(r_ends[i, 0]), float(r_ends[i, 1])),
                speed=parameters.scan_speed,
                power=parameters.power_level,
                layer_index=layer_index,
                is_contour=False
            )
            for i in range(len(segments))
        ]


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
