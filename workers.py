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
        position = np.asarray(model_data.get('position', [0, 0, 0]), dtype=float)
        rotation = np.asarray(model_data.get('rotation', [0, 0, 0]), dtype=float)
        scale = np.asarray(model_data.get('scale', [1, 1, 1]), dtype=float)

        if not model_bounds:
            return []

        min_x, min_y, min_z, max_x, max_y, max_z = model_bounds

        # Calculate model height in world space
        model_height = (max_y - min_y) * float(scale[1])
        # Bottom of model sits on top of build plate (5mm) + user position offset
        BUILD_PLATE_TOP_Y = 5.0  # Top of 10mm thick build plate
        model_bottom = BUILD_PLATE_TOP_Y + float(position[1])

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

        try:
            # Convert to numpy arrays and flatten to ensure 1D
            vertices_raw = cad_model.vertices
            indices_raw = cad_model.indices

            # If already numpy arrays, get the flat data; otherwise convert
            if isinstance(vertices_raw, np.ndarray):
                vertices = vertices_raw.flatten().astype(float)
            else:
                vertices = np.array(vertices_raw, dtype=float).flatten()

            if isinstance(indices_raw, np.ndarray):
                indices = indices_raw.flatten().astype(int)
            else:
                indices = np.array(indices_raw, dtype=int).flatten()

            # Convert transformation parameters to Python lists of floats
            position = model_data.get('position', [0, 0, 0])
            position = [float(position[0]), float(position[1]), float(position[2])]

            rotation = model_data.get('rotation', [0, 0, 0])
            rotation = [float(rotation[0]), float(rotation[1]), float(rotation[2])]

            scale = model_data.get('scale', [1, 1, 1])
            scale = [float(scale[0]), float(scale[1]), float(scale[2])]

            slice_z = float(slice_z)
        except Exception as e:
            raise ValueError(f"Error converting data types: {e}")

        segments = []

        # Process each triangle
        for i in range(0, len(indices), 3):
            # Convert to Python int to avoid numpy indexing issues
            # Use .item() to ensure we get Python ints, not numpy types
            try:
                i0 = indices[i].item() if hasattr(indices[i], 'item') else int(indices[i])
                i1 = indices[i+1].item() if hasattr(indices[i+1], 'item') else int(indices[i+1])
                i2 = indices[i+2].item() if hasattr(indices[i+2], 'item') else int(indices[i+2])
            except (AttributeError, ValueError) as e:
                continue

            # Get triangle vertices - use .item() to extract numpy scalars as Python floats
            try:
                v0 = [vertices[i0*3].item(), vertices[i0*3+1].item(), vertices[i0*3+2].item()]
                v1 = [vertices[i1*3].item(), vertices[i1*3+1].item(), vertices[i1*3+2].item()]
                v2 = [vertices[i2*3].item(), vertices[i2*3+1].item(), vertices[i2*3+2].item()]
            except (AttributeError, IndexError) as e:
                # Skip this triangle if we can't extract vertices
                continue

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
        """Apply transformation to a vertex.

        Args:
            vertex: List of 3 floats [x, y, z]
            position: List of 3 floats [x, y, z]
            rotation: List of 3 floats [rx, ry, rz] in degrees
            scale: List of 3 floats [sx, sy, sz]

        Returns:
            List of 3 floats representing transformed vertex
        """
        import math

        # All inputs are already Python lists of floats
        # Apply scale
        v = [vertex[0] * scale[0], vertex[1] * scale[1], vertex[2] * scale[2]]

        # Apply rotation (X, Y, Z order)
        if rotation[0] != 0:  # X rotation
            angle = math.radians(rotation[0])
            cos_a, sin_a = math.cos(angle), math.sin(angle)
            y, z = v[1], v[2]
            v[1] = y * cos_a - z * sin_a
            v[2] = y * sin_a + z * cos_a

        if rotation[1] != 0:  # Y rotation
            angle = math.radians(rotation[1])
            cos_a, sin_a = math.cos(angle), math.sin(angle)
            x, z = v[0], v[2]
            v[0] = x * cos_a + z * sin_a
            v[2] = -x * sin_a + z * cos_a

        if rotation[2] != 0:  # Z rotation
            angle = math.radians(rotation[2])
            cos_a, sin_a = math.cos(angle), math.sin(angle)
            x, y = v[0], v[1]
            v[0] = x * cos_a - y * sin_a
            v[1] = x * sin_a + y * cos_a

        # Apply translation
        v[0] += position[0]
        v[1] += position[1]
        v[2] += position[2]

        return v

    def _intersect_triangle_plane(self, v0, v1, v2, plane_y):
        """Find intersection of triangle with horizontal plane."""
        # Get Y coordinates and convert to float to avoid numpy array comparison issues
        y0, y1, y2 = float(v0[1]), float(v1[1]), float(v2[1])
        plane_y = float(plane_y)

        # Find which edges cross the plane
        edges_cross = []

        # Check edge v0-v1
        if (y0 <= plane_y <= y1) or (y1 <= plane_y <= y0):
            if abs(y1 - y0) > 1e-10:
                t = (plane_y - y0) / (y1 - y0)
                x = float(v0[0]) + t * (float(v1[0]) - float(v0[0]))
                z = float(v0[2]) + t * (float(v1[2]) - float(v0[2]))
                edges_cross.append((x, z))

        # Check edge v1-v2
        if (y1 <= plane_y <= y2) or (y2 <= plane_y <= y1):
            if abs(y2 - y1) > 1e-10:
                t = (plane_y - y1) / (y2 - y1)
                x = float(v1[0]) + t * (float(v2[0]) - float(v1[0]))
                z = float(v1[2]) + t * (float(v2[2]) - float(v1[2]))
                edges_cross.append((x, z))

        # Check edge v2-v0
        if (y2 <= plane_y <= y0) or (y0 <= plane_y <= y2):
            if abs(y0 - y2) > 1e-10:
                t = (plane_y - y2) / (y0 - y2)
                x = float(v2[0]) + t * (float(v0[0]) - float(v2[0]))
                z = float(v2[2]) + t * (float(v0[2]) - float(v2[2]))
                edges_cross.append((x, z))

        # Need exactly 2 intersection points
        if len(edges_cross) == 2:
            p0, p1 = edges_cross[0], edges_cross[1]
            # Return as (x1, z1, x2, z2)
            return (float(p0[0]), float(p0[1]), float(p1[0]), float(p1[1]))

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
