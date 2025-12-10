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

            if model is not None and not self._is_cancelled:
                self.finished.emit(model)
            elif model is None:
                self.error.emit("Failed to load CAD file")
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
        Standalone slicing implementation (mirrors OpenGLWidget.slice_model).

        Args:
            model_data: Model data dictionary with 'model', 'bounds', 'position', etc.
            layer_thickness: Thickness of each layer in mm

        Returns:
            List of layer sections with segments
        """
        import numpy as np

        cad_model = model_data.get('model')
        if not cad_model or not cad_model.vertices or not cad_model.indices:
            return []

        # Get model bounds and transformation
        model_bounds = model_data.get('bounds')
        position = model_data.get('position', [0, 0, 0])
        rotation = model_data.get('rotation', [0, 0, 0])
        scale = model_data.get('scale', [1, 1, 1])

        if not model_bounds:
            return []

        min_x, min_y, min_z, max_x, max_y, max_z = model_bounds

        # Calculate model height in world space
        model_height = (max_y - min_y) * scale[1]
        model_bottom = position[1]

        # Calculate number of layers
        num_layers = int(np.ceil(model_height / layer_thickness))
        if num_layers == 0:
            return []

        # Slice all layers
        all_layers = []
        for layer_idx in range(num_layers):
            if self._is_cancelled:
                return []

            layer_z = model_bottom + (layer_idx + 0.5) * layer_thickness
            segments = self._slice_at_height(cad_model, model_data, layer_z)
            all_layers.append({
                'z_height': layer_z,
                'layer_index': layer_idx,
                'segments': segments
            })

            # Report progress for individual layers
            if layer_idx % 10 == 0:
                self.progress.emit(layer_idx, num_layers, f"Slicing layer {layer_idx}/{num_layers}")

        # Group layers into sections
        sections = self._group_layers_into_sections(all_layers, model_bottom)

        return sections

    def _slice_at_height(self, cad_model, model_data, slice_z):
        """Slice the model at a specific height (standalone version)."""
        import numpy as np

        vertices = cad_model.vertices
        indices = cad_model.indices

        position = model_data.get('position', [0, 0, 0])
        rotation = model_data.get('rotation', [0, 0, 0])
        scale = model_data.get('scale', [1, 1, 1])

        segments = []

        # Process each triangle
        for i in range(0, len(indices), 3):
            i0, i1, i2 = indices[i], indices[i+1], indices[i+2]

            # Get triangle vertices
            v0 = vertices[i0*3:i0*3+3]
            v1 = vertices[i1*3:i1*3+3]
            v2 = vertices[i2*3:i2*3+3]

            # Apply transformations
            v0_t = self._transform_vertex(v0, position, rotation, scale)
            v1_t = self._transform_vertex(v1, position, rotation, scale)
            v2_t = self._transform_vertex(v2, position, rotation, scale)

            # Intersect with horizontal plane
            line_segment = self._intersect_triangle_plane(v0_t, v1_t, v2_t, slice_z)
            if line_segment:
                segments.append(line_segment)

        return segments

    def _transform_vertex(self, vertex, position, rotation, scale):
        """Apply transformation to a vertex."""
        import numpy as np

        # Apply scale
        v = np.array([vertex[0] * scale[0], vertex[1] * scale[1], vertex[2] * scale[2]])

        # Apply rotation (X, Y, Z order)
        if rotation[0] != 0:  # X rotation
            angle = np.radians(rotation[0])
            cos_a, sin_a = np.cos(angle), np.sin(angle)
            y, z = v[1], v[2]
            v[1] = y * cos_a - z * sin_a
            v[2] = y * sin_a + z * cos_a

        if rotation[1] != 0:  # Y rotation
            angle = np.radians(rotation[1])
            cos_a, sin_a = np.cos(angle), np.sin(angle)
            x, z = v[0], v[2]
            v[0] = x * cos_a + z * sin_a
            v[2] = -x * sin_a + z * cos_a

        if rotation[2] != 0:  # Z rotation
            angle = np.radians(rotation[2])
            cos_a, sin_a = np.cos(angle), np.sin(angle)
            x, y = v[0], v[1]
            v[0] = x * cos_a - y * sin_a
            v[1] = x * sin_a + y * cos_a

        # Apply translation
        v += np.array(position)

        return v

    def _intersect_triangle_plane(self, v0, v1, v2, plane_y):
        """Find intersection of triangle with horizontal plane."""
        # Get Y coordinates
        y0, y1, y2 = v0[1], v1[1], v2[1]

        # Find which edges cross the plane
        edges_cross = []

        # Check edge v0-v1
        if (y0 <= plane_y <= y1) or (y1 <= plane_y <= y0):
            if abs(y1 - y0) > 1e-10:
                t = (plane_y - y0) / (y1 - y0)
                x = v0[0] + t * (v1[0] - v0[0])
                z = v0[2] + t * (v1[2] - v0[2])
                edges_cross.append((x, z))

        # Check edge v1-v2
        if (y1 <= plane_y <= y2) or (y2 <= plane_y <= y1):
            if abs(y2 - y1) > 1e-10:
                t = (plane_y - y1) / (y2 - y1)
                x = v1[0] + t * (v2[0] - v1[0])
                z = v1[2] + t * (v2[2] - v1[2])
                edges_cross.append((x, z))

        # Check edge v2-v0
        if (y2 <= plane_y <= y0) or (y0 <= plane_y <= y2):
            if abs(y0 - y2) > 1e-10:
                t = (plane_y - y2) / (y0 - y2)
                x = v2[0] + t * (v0[0] - v2[0])
                z = v2[2] + t * (v0[2] - v2[2])
                edges_cross.append((x, z))

        # Need exactly 2 intersection points
        if len(edges_cross) == 2:
            p0, p1 = edges_cross[0], edges_cross[1]
            # Return as (x1, z1, x2, z2)
            return (p0[0], p0[1], p1[0], p1[1])

        return None

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
