"""
Base classes and interfaces for the hatching plugin system.
"""

from abc import ABC, abstractmethod
from typing import List, Tuple, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
import numpy as np


class HatchingStrategy(Enum):
    """Enumeration of available hatching strategies."""
    LINES = "lines"
    ZIGZAG = "zigzag"
    GRID = "grid"
    HONEYCOMB = "honeycomb"
    CONCENTRIC = "concentric"
    HILBERT = "hilbert"
    SPIRAL = "spiral"
    ADAPTIVE = "adaptive"


@dataclass
class HatchLine:
    """
    Represents a single hatch line segment.

    Attributes:
        start: Starting point (x, y) in mm
        end: Ending point (x, y) in mm
        speed: Scanning speed in mm/s (optional)
        power: Laser/beam power 0-1 (optional)
        layer_index: Layer number this hatch belongs to
        is_contour: Whether this is a contour line (outline)
    """
    start: Tuple[float, float]
    end: Tuple[float, float]
    speed: Optional[float] = None
    power: Optional[float] = None
    layer_index: int = 0
    is_contour: bool = False

    def length(self) -> float:
        """Calculate the length of this hatch line."""
        dx = self.end[0] - self.start[0]
        dy = self.end[1] - self.start[1]
        return np.sqrt(dx * dx + dy * dy)

    def angle(self) -> float:
        """Calculate the angle of this hatch line in degrees."""
        dx = self.end[0] - self.start[0]
        dy = self.end[1] - self.start[1]
        return np.degrees(np.arctan2(dy, dx))


@dataclass
class HatchingParameters:
    """
    Parameters for hatching generation.

    Attributes:
        hatch_spacing: Distance between hatch lines in mm
        hatch_angle: Base hatch angle in degrees
        layer_rotation: Rotation increment per layer in degrees
        border_offset: Offset from contour in mm
        enable_contours: Whether to include contour lines
        contour_count: Number of contour passes
        scan_speed: Default scan speed in mm/s
        power_level: Default power level 0-1
        enable_skywriting: Enable skywriting (beam off during jumps)
        jump_speed: Speed during non-printing moves in mm/s
    """
    hatch_spacing: float = 0.1  # mm
    hatch_angle: float = 0.0  # degrees
    layer_rotation: float = 67.0  # degrees (common in SLM)
    border_offset: float = 0.0  # mm
    enable_contours: bool = True
    contour_count: int = 1
    scan_speed: float = 1000.0  # mm/s
    power_level: float = 1.0  # 0-1
    enable_skywriting: bool = True
    jump_speed: float = 5000.0  # mm/s

    # Strategy-specific parameters
    infill_density: float = 1.0  # 0-1, for adaptive strategies
    min_feature_size: float = 0.05  # mm
    optimize_path: bool = True
    bidirectional: bool = True  # For line hatching

    # Advanced parameters
    custom_params: Dict[str, Any] = field(default_factory=dict)


class HatchingPlugin(ABC):
    """
    Abstract base class for hatching plugins.

    All hatching strategies must inherit from this class and implement
    the generate_hatching method.
    """

    def __init__(self):
        """Initialize the hatching plugin."""
        self._name = self.__class__.__name__
        self._description = ""
        self._version = "1.0.0"

    @property
    def name(self) -> str:
        """Get the plugin name."""
        return self._name

    @property
    def description(self) -> str:
        """Get the plugin description."""
        return self._description

    @property
    def version(self) -> str:
        """Get the plugin version."""
        return self._version

    @abstractmethod
    def generate_hatching(
        self,
        contours: List[List[Tuple[float, float]]],
        parameters: HatchingParameters,
        layer_index: int = 0
    ) -> List[HatchLine]:
        """
        Generate hatching lines for a layer.

        Args:
            contours: List of contours, where each contour is a list of (x, y) points.
                     First contour is the outer boundary, subsequent contours are holes.
            parameters: Hatching parameters
            layer_index: Layer number (for rotation strategies)

        Returns:
            List of HatchLine objects representing the hatching pattern
        """
        pass

    def validate_parameters(self, parameters: HatchingParameters) -> bool:
        """
        Validate parameters for this hatching strategy.

        Args:
            parameters: Parameters to validate

        Returns:
            True if parameters are valid, False otherwise
        """
        if parameters.hatch_spacing <= 0:
            return False
        if parameters.contour_count < 0:
            return False
        if not 0 <= parameters.power_level <= 1:
            return False
        if not 0 <= parameters.infill_density <= 1:
            return False
        return True

    def optimize_scan_path(self, hatch_lines: List[HatchLine]) -> List[HatchLine]:
        """
        Optimize the scanning path to minimize travel time.

        This is a simple greedy nearest-neighbor optimization.
        Subclasses can override for more sophisticated optimization.

        Args:
            hatch_lines: Unoptimized hatch lines

        Returns:
            Optimized hatch lines
        """
        if not hatch_lines:
            return []

        optimized = []
        remaining = hatch_lines.copy()
        current_pos = remaining[0].start

        while remaining:
            # Find nearest line (by start or end point)
            min_dist = float('inf')
            best_idx = 0
            flip = False

            for i, line in enumerate(remaining):
                # Distance to start
                dist_start = self._point_distance(current_pos, line.start)
                if dist_start < min_dist:
                    min_dist = dist_start
                    best_idx = i
                    flip = False

                # Distance to end
                dist_end = self._point_distance(current_pos, line.end)
                if dist_end < min_dist:
                    min_dist = dist_end
                    best_idx = i
                    flip = True

            # Add the best line
            line = remaining.pop(best_idx)
            if flip:
                # Reverse the line
                line = HatchLine(
                    start=line.end,
                    end=line.start,
                    speed=line.speed,
                    power=line.power,
                    layer_index=line.layer_index,
                    is_contour=line.is_contour
                )

            optimized.append(line)
            current_pos = line.end

        return optimized

    def _point_distance(self, p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
        """Calculate Euclidean distance between two points."""
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        return np.sqrt(dx * dx + dy * dy)

    def get_effective_angle(self, base_angle: float, layer_index: int, rotation: float) -> float:
        """
        Calculate the effective hatch angle for a given layer.

        Args:
            base_angle: Base hatch angle in degrees
            layer_index: Layer number
            rotation: Rotation per layer in degrees

        Returns:
            Effective angle in degrees, normalized to [0, 180)
        """
        angle = (base_angle + layer_index * rotation) % 180
        return angle

    def generate_contours(
        self,
        contours: List[List[Tuple[float, float]]],
        parameters: HatchingParameters,
        layer_index: int
    ) -> List[HatchLine]:
        """
        Generate contour lines from polygon boundaries.

        Args:
            contours: List of contours
            parameters: Hatching parameters
            layer_index: Layer number

        Returns:
            List of contour HatchLine objects
        """
        contour_lines = []

        if not parameters.enable_contours or parameters.contour_count == 0:
            return contour_lines

        for contour in contours:
            if len(contour) < 2:
                continue

            # Generate contour lines
            for i in range(len(contour)):
                start = contour[i]
                end = contour[(i + 1) % len(contour)]

                contour_lines.append(HatchLine(
                    start=start,
                    end=end,
                    speed=parameters.scan_speed,
                    power=parameters.power_level,
                    layer_index=layer_index,
                    is_contour=True
                ))

        return contour_lines
