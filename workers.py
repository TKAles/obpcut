"""
Worker threads for long-running operations to prevent UI blocking.
"""
from typing import Callable, Any, Optional
from PyQt6.QtCore import QThread, pyqtSignal


class WorkerThread(QThread):
    """
    Generic worker thread for running operations in the background.

    Signals:
        progress: Emitted with (current, total, message) during operation
        finished: Emitted with result when operation completes successfully
        error: Emitted with exception when operation fails
    """
    progress = pyqtSignal(int, int, str)  # current, total, message
    finished = pyqtSignal(object)  # result
    error = pyqtSignal(Exception)  # exception

    def __init__(self, func: Callable, *args, **kwargs):
        """
        Initialize worker thread.

        Args:
            func: Function to execute in the background
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func
        """
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self._is_cancelled = False

    def run(self):
        """Execute the function in the background thread."""
        try:
            # Add progress callback to kwargs if the function supports it
            if 'progress_callback' in self.func.__code__.co_varnames:
                self.kwargs['progress_callback'] = self.report_progress

            result = self.func(*self.args, **self.kwargs)

            if not self._is_cancelled:
                self.finished.emit(result)
        except Exception as e:
            if not self._is_cancelled:
                self.error.emit(e)

    def report_progress(self, current: int, total: int, message: str = ""):
        """Report progress from the worker function."""
        if not self._is_cancelled:
            self.progress.emit(current, total, message)

    def cancel(self):
        """Request cancellation of the operation."""
        self._is_cancelled = True


class CADLoadWorker(QThread):
    """
    Specialized worker for loading CAD files with progress reporting.

    Signals:
        progress: Emitted with (stage, message) during loading
        finished: Emitted with CADModel when loading completes
        error: Emitted with error message when loading fails
    """
    progress = pyqtSignal(str, str)  # stage, message
    finished = pyqtSignal(object)  # CADModel
    error = pyqtSignal(str)  # error message

    def __init__(self, file_path: str):
        """
        Initialize CAD load worker.

        Args:
            file_path: Path to the CAD file to load
        """
        super().__init__()
        self.file_path = file_path
        self._is_cancelled = False

    def run(self):
        """Load the CAD file in the background."""
        try:
            from cad_loader import load_cad_file_with_progress

            def progress_callback(stage: str, message: str):
                if not self._is_cancelled:
                    self.progress.emit(stage, message)

            model = load_cad_file_with_progress(self.file_path, progress_callback)

            if not self._is_cancelled:
                self.finished.emit(model)
        except Exception as e:
            if not self._is_cancelled:
                self.error.emit(str(e))

    def cancel(self):
        """Request cancellation of the loading operation."""
        self._is_cancelled = True


class SlicingWorker(QThread):
    """
    Specialized worker for slicing models with progress reporting.

    Signals:
        progress: Emitted with (current_layer, total_layers, message) during slicing
        finished: Emitted with sliced layers when complete
        error: Emitted with error message when slicing fails
    """
    progress = pyqtSignal(int, int, str)  # current, total, message
    finished = pyqtSignal(list)  # list of sliced layers
    error = pyqtSignal(str)  # error message

    def __init__(self, models: list, layer_thickness: float):
        """
        Initialize slicing worker.

        Args:
            models: List of model data dictionaries
            layer_thickness: Thickness of each layer in mm
        """
        super().__init__()
        self.models = models
        self.layer_thickness = layer_thickness
        self._is_cancelled = False

    def run(self):
        """Perform slicing in the background."""
        try:
            import numpy as np
            from typing import List, Tuple

            all_sliced_layers = []

            for i, model_data in enumerate(self.models):
                if self._is_cancelled:
                    return

                self.progress.emit(i, len(self.models), f"Slicing model {i+1}/{len(self.models)}")

                # Perform slicing using standalone implementation
                sliced_layers = self._slice_model_standalone(model_data, self.layer_thickness)
                all_sliced_layers.append(sliced_layers)

            if not self._is_cancelled:
                self.finished.emit(all_sliced_layers)
        except Exception as e:
            if not self._is_cancelled:
                self.error.emit(str(e))

    def _slice_model_standalone(self, model_data, layer_thickness):
        """
        Standalone slicing implementation using fully vectorized numpy operations.

        All vertices are pre-transformed once; per-layer work is numpy-only.
        """
        import numpy as np

        cad_model = model_data.get('model')
        if not cad_model or not cad_model.vertices or not cad_model.indices:
            return []

        model_bounds = model_data.get('bounds')
        if not model_bounds:
            return []

        position = np.asarray(model_data.get('position', [0, 0, 0]), dtype=np.float64)
        rotation = np.asarray(model_data.get('rotation', [0, 0, 0]), dtype=np.float64)
        scale    = np.asarray(model_data.get('scale',    [1, 1, 1]), dtype=np.float64)

        min_x, min_y, min_z, max_x, max_y, max_z = model_bounds
        model_height = (max_y - min_y) * scale[1]
        BUILD_PLATE_TOP_Y = 5.0
        model_bottom = BUILD_PLATE_TOP_Y + position[1]

        num_layers = int(np.ceil(model_height / layer_thickness))
        if num_layers == 0:
            return []

        # ------------------------------------------------------------------
        # Pre-process: convert and transform ALL vertices exactly ONCE
        # ------------------------------------------------------------------
        verts_raw = cad_model.vertices
        idx_raw   = cad_model.indices

        verts = (verts_raw.flatten() if isinstance(verts_raw, np.ndarray)
                 else np.array(verts_raw, dtype=np.float64).flatten()).astype(np.float64)
        indices = (idx_raw.flatten() if isinstance(idx_raw, np.ndarray)
                   else np.array(idx_raw, dtype=np.int32).flatten()).astype(np.int32)

        # Reshape to (N_verts, 3) and apply scale
        verts = verts.reshape(-1, 3) * scale

        # Apply rotations (X → Y → Z, same order as original _transform_vertex)
        rx, ry, rz = np.radians(rotation)
        if rotation[0] != 0:
            cx, sx = np.cos(rx), np.sin(rx)
            y, z = verts[:, 1].copy(), verts[:, 2].copy()
            verts[:, 1] = y * cx - z * sx
            verts[:, 2] = y * sx + z * cx
        if rotation[1] != 0:
            cy, sy = np.cos(ry), np.sin(ry)
            x, z = verts[:, 0].copy(), verts[:, 2].copy()
            verts[:, 0] = x * cy + z * sy
            verts[:, 2] = -x * sy + z * cy
        if rotation[2] != 0:
            cz, sz = np.cos(rz), np.sin(rz)
            x, y = verts[:, 0].copy(), verts[:, 1].copy()
            verts[:, 0] = x * cz - y * sz
            verts[:, 1] = x * sz + y * cz

        verts += position  # apply translation

        # Build per-triangle vertex arrays: shapes (N_tris, 3)
        tris = indices.reshape(-1, 3)
        v0 = verts[tris[:, 0]]
        v1 = verts[tris[:, 1]]
        v2 = verts[tris[:, 2]]
        y0, y1, y2 = v0[:, 1], v1[:, 1], v2[:, 1]

        # Pre-compute per-triangle Y extents for fast culling
        tri_ymin = np.minimum(np.minimum(y0, y1), y2)
        tri_ymax = np.maximum(np.maximum(y0, y1), y2)

        # ------------------------------------------------------------------
        # Slice each layer using vectorized intersection
        # ------------------------------------------------------------------
        all_layers = []
        for layer_idx in range(num_layers):
            if self._is_cancelled:
                return []

            plane_y = float(model_bottom + (layer_idx + 0.5) * layer_thickness)

            # Cull triangles whose Y range doesn't span this plane
            active = (tri_ymin <= plane_y) & (tri_ymax >= plane_y)
            if not np.any(active):
                segments = []
            else:
                segments = self._intersect_triangles_vectorized(
                    v0[active], v1[active], v2[active],
                    y0[active], y1[active], y2[active],
                    plane_y
                )

            all_layers.append({
                'z_height': plane_y,
                'layer_index': layer_idx,
                'segments': segments
            })

            if layer_idx % 10 == 0:
                self.progress.emit(layer_idx, num_layers, f"Slicing layer {layer_idx}/{num_layers}")

        return self._group_layers_into_sections(all_layers, model_bottom)

    def _intersect_triangles_vectorized(self, v0, v1, v2, y0, y1, y2, plane_y):
        """
        Vectorized plane-triangle intersection for a batch of pre-culled triangles.

        Returns a list of (x1, z1, x2, z2) segment tuples.
        """
        import numpy as np

        def _edge_cross(va, vb, ya, yb):
            """Return (crosses_mask, x, z) for edge va→vb."""
            crosses = (((ya <= plane_y) & (yb >= plane_y)) |
                       ((yb <= plane_y) & (ya >= plane_y)))
            non_degen = np.abs(yb - ya) > 1e-10
            crosses &= non_degen
            safe_dy = np.where(non_degen, yb - ya, 1.0)  # avoid div/0
            t = (plane_y - ya) / safe_dy
            x = va[:, 0] + t * (vb[:, 0] - va[:, 0])
            z = va[:, 2] + t * (vb[:, 2] - va[:, 2])
            return crosses, x, z

        c01, x01, z01 = _edge_cross(v0, v1, y0, y1)
        c12, x12, z12 = _edge_cross(v1, v2, y1, y2)
        c20, x20, z20 = _edge_cross(v2, v0, y2, y0)

        # Priority: prefer (01,12) > (01,20) > (12,20) to get exactly one
        # segment per triangle even in degenerate vertex-on-plane cases.
        m01_12 = c01 & c12
        m01_20 = c01 & c20 & ~m01_12
        m12_20 = c12 & c20 & ~m01_12 & ~m01_20

        parts = []
        for mask, xa, za, xb, zb in (
            (m01_12, x01, z01, x12, z12),
            (m01_20, x01, z01, x20, z20),
            (m12_20, x12, z12, x20, z20),
        ):
            if np.any(mask):
                parts.append(np.stack(
                    [xa[mask], za[mask], xb[mask], zb[mask]], axis=1))

        if not parts:
            return []
        segs = np.vstack(parts)
        return [tuple(row) for row in segs]

    def _group_layers_into_sections(self, all_layers, model_bottom):
        """Group consecutive layers with identical outlines into sections."""
        if not all_layers:
            return []

        sections = []
        current_section = {
            'start_layer': 0,
            'end_layer': 0,
            'z_start': all_layers[0]['z_height'],
            'z_end': all_layers[0]['z_height'],
            'segments': all_layers[0]['segments'],
            'layer_count': 1
        }

        for i in range(1, len(all_layers)):
            current_layer = all_layers[i]
            prev_layer = all_layers[i - 1]

            # Check if outlines are equal
            if self._outlines_are_equal(current_layer['segments'], prev_layer['segments']):
                current_section['end_layer'] = i
                current_section['z_end'] = current_layer['z_height']
                current_section['layer_count'] += 1
            else:
                sections.append(current_section)
                current_section = {
                    'start_layer': i,
                    'end_layer': i,
                    'z_start': current_layer['z_height'],
                    'z_end': current_layer['z_height'],
                    'segments': current_layer['segments'],
                    'layer_count': 1
                }

        sections.append(current_section)
        return sections

    def _outlines_are_equal(self, segments1, segments2, tolerance=1e-6):
        """Check if two sets of segments represent the same outline."""
        if len(segments1) != len(segments2):
            return False

        if len(segments1) == 0:
            return True

        # Simple comparison (can be improved with better matching)
        for s1, s2 in zip(segments1, segments2):
            if abs(s1[0] - s2[0]) > tolerance or \
               abs(s1[1] - s2[1]) > tolerance or \
               abs(s1[2] - s2[2]) > tolerance or \
               abs(s1[3] - s2[3]) > tolerance:
                return False

        return True

    def cancel(self):
        """Request cancellation of the slicing operation."""
        self._is_cancelled = True


class HatchingWorker(QThread):
    """
    Specialized worker for generating hatching with progress reporting.

    Signals:
        progress: Emitted with (current_layer, total_layers, message) during hatching
        finished: Emitted with hatching data when complete
        error: Emitted with error message when hatching fails
    """
    progress = pyqtSignal(int, int, str)  # current, total, message
    finished = pyqtSignal(dict)  # hatching data dictionary
    error = pyqtSignal(str)  # error message

    def __init__(self, sliced_layers: list, hatching_params, hatching_strategy):
        """
        Initialize hatching worker.

        Args:
            sliced_layers: List of sliced layer sections for all models
            hatching_params: HatchingParameters instance
            hatching_strategy: HatchingStrategy enum value
        """
        super().__init__()
        self.sliced_layers = sliced_layers
        self.hatching_params = hatching_params
        self.hatching_strategy = hatching_strategy
        self._is_cancelled = False

    def run(self):
        """Generate hatching in the background."""
        try:
            from hatching_integration import prepare_hatching_for_all_layers

            hatching_data = {}

            # Generate hatching for each model
            for model_idx, layer_sections in enumerate(self.sliced_layers):
                if self._is_cancelled:
                    return

                self.progress.emit(model_idx, len(self.sliced_layers),
                                 f"Generating hatching for model {model_idx+1}/{len(self.sliced_layers)}")

                # Progress callback for individual layers
                def layer_progress(layer_idx, total_layers, message):
                    if not self._is_cancelled:
                        self.progress.emit(layer_idx, total_layers, message)

                model_hatching = prepare_hatching_for_all_layers(
                    layer_sections,
                    self.hatching_params,
                    self.hatching_strategy,
                    progress_callback=layer_progress
                )

                # Store hatching data with (model_idx, layer_idx) keys
                for layer_idx, hatch_lines in model_hatching.items():
                    key = (model_idx, layer_idx)
                    hatching_data[key] = hatch_lines

            if not self._is_cancelled:
                self.finished.emit(hatching_data)
        except Exception as e:
            if not self._is_cancelled:
                self.error.emit(str(e))

    def cancel(self):
        """Request cancellation of the hatching operation."""
        self._is_cancelled = True
