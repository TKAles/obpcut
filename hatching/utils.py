"""
Utility functions for hatching operations.
"""

from typing import List, Tuple, Optional
import numpy as np
from shapely.geometry import Polygon, LineString, Point
from shapely.ops import unary_union
from shapely.affinity import rotate as shapely_rotate


def get_bounding_box(contours: List[List[Tuple[float, float]]]) -> Tuple[float, float, float, float]:
    """
    Calculate the bounding box of a set of contours.

    Args:
        contours: List of contours, where each contour is a list of (x, y) points

    Returns:
        Tuple of (min_x, min_y, max_x, max_y)
    """
    all_points = [point for contour in contours for point in contour]
    if not all_points:
        return (0.0, 0.0, 0.0, 0.0)

    xs = [p[0] for p in all_points]
    ys = [p[1] for p in all_points]

    return (min(xs), min(ys), max(xs), max(ys))


def create_polygon_from_contours(contours: List[List[Tuple[float, float]]]) -> Optional[Polygon]:
    """
    Create a Shapely Polygon from contours.

    Args:
        contours: List of contours. First is outer boundary, rest are holes.

    Returns:
        Shapely Polygon object, or None if invalid
    """
    if not contours or len(contours[0]) < 3:
        return None

    try:
        # First contour is the exterior
        exterior = contours[0]

        # Remaining contours are holes (if any)
        holes = contours[1:] if len(contours) > 1 else []

        # Filter out invalid holes (less than 3 points)
        valid_holes = [hole for hole in holes if len(hole) >= 3]

        polygon = Polygon(exterior, valid_holes)

        # Ensure valid polygon
        if not polygon.is_valid:
            # Try to fix it
            polygon = polygon.buffer(0)

        return polygon if polygon.is_valid else None

    except Exception:
        return None


def clip_line_to_polygon(
    line_start: Tuple[float, float],
    line_end: Tuple[float, float],
    polygon: Polygon
) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """
    Clip a line segment to a polygon boundary.

    Args:
        line_start: Starting point of the line (x, y)
        line_end: Ending point of the line (x, y)
        polygon: Shapely Polygon to clip against

    Returns:
        List of line segments (start, end) that are inside the polygon
    """
    line = LineString([line_start, line_end])

    try:
        intersection = line.intersection(polygon)

        segments = []

        # Handle different geometry types
        if intersection.is_empty:
            return []
        elif intersection.geom_type == 'LineString':
            coords = list(intersection.coords)
            if len(coords) >= 2:
                segments.append((coords[0], coords[-1]))
        elif intersection.geom_type == 'MultiLineString':
            for geom in intersection.geoms:
                coords = list(geom.coords)
                if len(coords) >= 2:
                    segments.append((coords[0], coords[-1]))
        elif intersection.geom_type == 'Point':
            # Single point intersection - ignore
            pass
        elif intersection.geom_type == 'GeometryCollection':
            for geom in intersection.geoms:
                if geom.geom_type == 'LineString':
                    coords = list(geom.coords)
                    if len(coords) >= 2:
                        segments.append((coords[0], coords[-1]))

        return segments

    except Exception:
        return []


def rotate_point(
    point: Tuple[float, float],
    center: Tuple[float, float],
    angle_degrees: float
) -> Tuple[float, float]:
    """
    Rotate a point around a center point.

    Args:
        point: Point to rotate (x, y)
        center: Center of rotation (x, y)
        angle_degrees: Rotation angle in degrees (counter-clockwise)

    Returns:
        Rotated point (x, y)
    """
    angle_rad = np.radians(angle_degrees)
    cos_a = np.cos(angle_rad)
    sin_a = np.sin(angle_rad)

    # Translate to origin
    dx = point[0] - center[0]
    dy = point[1] - center[1]

    # Rotate
    x_new = dx * cos_a - dy * sin_a
    y_new = dx * sin_a + dy * cos_a

    # Translate back
    return (x_new + center[0], y_new + center[1])


def offset_polygon(polygon: Polygon, offset: float) -> Optional[Polygon]:
    """
    Create an offset (inward or outward) of a polygon.

    Args:
        polygon: Input polygon
        offset: Offset distance (positive for outward, negative for inward)

    Returns:
        Offset polygon, or None if invalid
    """
    try:
        # Shapely's buffer creates offset
        # Negative offset = inward, positive = outward
        offset_poly = polygon.buffer(
            -offset,  # Negative because we typically want inward offset
            join_style='mitre',
            mitre_limit=2.0
        )

        if offset_poly.is_empty or not offset_poly.is_valid:
            return None

        # Handle MultiPolygon result (take largest)
        if offset_poly.geom_type == 'MultiPolygon':
            # Return the polygon with largest area
            offset_poly = max(offset_poly.geoms, key=lambda p: p.area)

        return offset_poly if offset_poly.geom_type == 'Polygon' else None

    except Exception:
        return None


def sort_segments_for_scanning(
    segments: List[Tuple[Tuple[float, float], Tuple[float, float]]],
    bidirectional: bool = True
) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """
    Sort line segments for efficient scanning.

    Args:
        segments: List of line segments (start, end)
        bidirectional: If True, alternate scan direction for adjacent lines

    Returns:
        Sorted and oriented line segments
    """
    if not segments:
        return []

    # Sort segments by their average y-coordinate (or x if horizontal)
    def get_sort_key(seg):
        return (seg[0][1] + seg[1][1]) / 2

    sorted_segments = sorted(segments, key=get_sort_key)

    if bidirectional:
        # Reverse every other segment for bidirectional scanning
        result = []
        for i, seg in enumerate(sorted_segments):
            if i % 2 == 1:
                # Reverse the segment
                result.append((seg[1], seg[0]))
            else:
                result.append(seg)
        return result
    else:
        return sorted_segments


def line_intersection(
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    p3: Tuple[float, float],
    p4: Tuple[float, float]
) -> Optional[Tuple[float, float]]:
    """
    Find intersection point of two line segments.

    Args:
        p1, p2: First line segment endpoints
        p3, p4: Second line segment endpoints

    Returns:
        Intersection point (x, y) or None if no intersection
    """
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4

    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)

    if abs(denom) < 1e-10:
        return None  # Parallel or coincident

    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denom

    if 0 <= t <= 1 and 0 <= u <= 1:
        # Intersection within both segments
        x = x1 + t * (x2 - x1)
        y = y1 + t * (y2 - y1)
        return (x, y)

    return None


def simplify_contour(contour: List[Tuple[float, float]], tolerance: float = 0.01) -> List[Tuple[float, float]]:
    """
    Simplify a contour by removing redundant points.

    Args:
        contour: List of points
        tolerance: Simplification tolerance in mm

    Returns:
        Simplified contour
    """
    if len(contour) < 3:
        return contour

    try:
        line = LineString(contour)
        simplified = line.simplify(tolerance, preserve_topology=True)
        return list(simplified.coords)
    except Exception:
        return contour
