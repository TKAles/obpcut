from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtGui import QOpenGLContext, QSurfaceFormat, QPainter, QFont, QColor, QFontMetrics
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from OpenGL.GL import *
from OpenGL.GLU import *
import sys
import numpy as np
from cad_loader import load_cad_file, CADModel

class OpenGLWidget(QOpenGLWidget):
    # Build plate constants
    BUILD_PLATE_THICKNESS = 10.0  # mm
    BUILD_PLATE_TOP_Y = BUILD_PLATE_THICKNESS / 2  # Top surface at Y = 5mm

    # Signal emitted when model transformation changes via gizmo
    transformation_changed = pyqtSignal()
    # Signals for async operations
    slicing_requested = pyqtSignal(list, float)  # models, layer_thickness
    hatching_requested = pyqtSignal(list, object, object)  # sliced_layers, params, strategy

    def __init__(self, parent=None):
        super().__init__(parent)
        # Set isometric view angles (standard isometric: 35.264° on X, 45° on Y)
        self.rotation_x = 30.0  # Isometric tilt
        self.rotation_y = 45.0  # Isometric rotation
        self.rotation_z = 0.0
        # Model management - support multiple models
        self.models = []  # List of loaded models (each with CADModel data, name, bounds, etc.)
        self.selected_model_index = None  # Index of currently selected model

        # Transformation mode ('move', 'rotate', 'scale', or None)
        self.transform_mode = None
        self.hovered_gizmo_axis = None  # Which gizmo axis is hovered ('x', 'y', 'z', or None)
        self.selected_gizmo_axis = None  # Which gizmo axis is being dragged
        self.is_dragging_gizmo = False  # True when actively dragging a gizmo
        self.transform_start_mouse = None  # Mouse position when drag started
        self.transform_start_value = None  # Initial transformation value

        # Camera controls
        self.camera_distance = 200.0  # Distance from origin (increased to see build plate)
        self.pan_x = 0.0
        self.pan_y = 0.0

        # Mouse interaction state
        self.last_mouse_pos = None
        self.is_rotating = False
        self.is_panning = False
        self.is_zooming = False

        # Timer for updating the display
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(33)  # ~30 FPS (enough for smooth display)

        # Enable mouse tracking
        self.setMouseTracking(True)

        # Face picking mode for align to build plate
        self.face_picking_mode = False
        self.face_aligned_callback = None  # Callback when face is aligned

        # Grid label positions for rendering (updated during draw_build_plate)
        self.grid_labels = []  # List of (screen_x, screen_y, text) tuples
        self.triad_labels = []  # List of (screen_x, screen_y, text, color) tuples

        # Slice mode state
        self.view_mode = 'layout'  # 'layout' or 'slice'
        self.layer_thickness = 0.2  # mm
        self.current_layer_index = 0  # Current layer being viewed
        self.sliced_layers = []  # List of sliced layer outlines for each model

        # Slice mode scrollbar gizmo state
        self.scrollbar_dragging = False
        self.scrollbar_hover = False
        self.scrollbar_width = 20  # pixels
        self.scrollbar_margin = 10  # pixels from right edge

        # Hatching state
        self.hatching_enabled = False  # Whether to show hatching in slice mode
        self.hatching_data = {}  # Dict mapping (model_idx, layer_idx) -> List[HatchLine]
        self.hatching_params = None  # HatchingParameters instance
        self.hatching_strategy = None  # HatchingStrategy enum value

    def initializeGL(self):
        """Initialize OpenGL context and settings"""
        # Set up OpenGL context
        self.makeCurrent()
        
        # Enable depth testing
        glEnable(GL_DEPTH_TEST)

        # Disable face culling to see both sides of faces
        glDisable(GL_CULL_FACE)
        
        # Set clear color to light gray background (70% gray)
        glClearColor(0.7, 0.7, 0.7, 1.0)

        # Set up lighting with multiple lights for even illumination
        glEnable(GL_LIGHTING)

        # Enable ambient light for base illumination
        glLightModelfv(GL_LIGHT_MODEL_AMBIENT, [0.4, 0.4, 0.4, 1.0])

        # Main key light (top-front-right)
        glEnable(GL_LIGHT0)
        glLightfv(GL_LIGHT0, GL_POSITION, [1.0, 1.0, 1.0, 0.0])
        glLightfv(GL_LIGHT0, GL_DIFFUSE, [0.6, 0.6, 0.6, 1.0])
        glLightfv(GL_LIGHT0, GL_SPECULAR, [0.3, 0.3, 0.3, 1.0])

        # Fill light (top-front-left) for better illumination
        glEnable(GL_LIGHT1)
        glLightfv(GL_LIGHT1, GL_POSITION, [-1.0, 1.0, 1.0, 0.0])
        glLightfv(GL_LIGHT1, GL_DIFFUSE, [0.4, 0.4, 0.4, 1.0])
        glLightfv(GL_LIGHT1, GL_SPECULAR, [0.1, 0.1, 0.1, 1.0])

        # Back light (from below-back) to prevent dark silhouettes
        glEnable(GL_LIGHT2)
        glLightfv(GL_LIGHT2, GL_POSITION, [0.0, -0.5, -1.0, 0.0])
        glLightfv(GL_LIGHT2, GL_DIFFUSE, [0.3, 0.3, 0.3, 1.0])
        glLightfv(GL_LIGHT2, GL_SPECULAR, [0.0, 0.0, 0.0, 1.0])

        # Set material properties
        glMaterialfv(GL_FRONT, GL_DIFFUSE, [0.8, 0.8, 0.8, 1.0])
        glMaterialfv(GL_FRONT, GL_SPECULAR, [1.0, 1.0, 1.0, 1.0])
        glMaterialf(GL_FRONT, GL_SHININESS, 50.0)

        # Enable flat shading (slicer-style)
        glShadeModel(GL_FLAT)
        
    def resizeGL(self, width, height):
        """Handle window resize"""
        # Make sure we have a valid context
        if not self.context():
            return

        # Protect against division by zero
        if height == 0:
            height = 1

        self.makeCurrent()

        # Set viewport to match new window size
        glViewport(0, 0, width, height)

        # Set up projection matrix
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45.0, width / height, 0.1, 1000.0)

        # Switch back to modelview matrix
        glMatrixMode(GL_MODELVIEW)
        
    def paintGL(self):
        """Main rendering function"""
        # Make sure we have a valid context
        context = self.context()
        if not context or not context.isValid():
            return

        self.makeCurrent()

        # Ensure depth testing is enabled (might be lost during context switches)
        glEnable(GL_DEPTH_TEST)

        # Clear buffers with proper color and depth clearing
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        # Set up projection matrix (ensure it's correct after any context changes)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        width = self.width()
        height = self.height()
        if height == 0:
            height = 1
        gluPerspective(45.0, width / height, 0.1, 1000.0)

        # Switch to modelview matrix
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

        # Draw based on view mode
        if self.view_mode == 'slice':
            # Slice mode: 2D orthographic view from the build direction (looking at XZ plane)
            # Set up orthographic projection for 2D view
            glMatrixMode(GL_PROJECTION)
            glLoadIdentity()

            # Calculate the view bounds (show build plate area)
            view_size = 60.0  # Show 120mm x 120mm area (build plate is 100mm diameter)
            glOrtho(-view_size, view_size, -view_size, view_size, -100, 100)

            glMatrixMode(GL_MODELVIEW)
            glLoadIdentity()

            # View from the build direction (as if we're the electron gun)
            # We want to look at the XZ plane (horizontal plane)
            # Rotate 90 degrees around X axis to look from below upward
            glRotatef(-90, 1.0, 0.0, 0.0)

            # Draw sliced layer outlines
            self.draw_sliced_layers()

            # Draw scrollbar gizmo
            self.draw_scrollbar_gizmo()
        else:
            # Layout mode: 3D perspective view
            # Move camera back based on zoom level
            glTranslatef(0.0, 0.0, -self.camera_distance)

            # Apply pan (in camera space, before rotation)
            glTranslatef(self.pan_x, self.pan_y, 0.0)

            # Apply rotations around the build plate center
            glRotatef(self.rotation_x, 1.0, 0.0, 0.0)
            glRotatef(self.rotation_y, 0.0, 1.0, 0.0)
            glRotatef(self.rotation_z, 0.0, 0.0, 1.0)

            # Draw the build plate
            self.draw_build_plate()

            # Draw all loaded CAD models
            for i, model_data in enumerate(self.models):
                is_selected = (i == self.selected_model_index)
                self.draw_cad_model(model_data, is_selected)

            # Draw transformation gizmo for selected model
            if self.selected_model_index is not None and self.transform_mode:
                self.draw_gizmo(self.models[self.selected_model_index])

            # Draw orientation triad in bottom-left corner
            self.draw_orientation_triad()

            # Draw grid labels using QPainter overlay
            self.draw_grid_labels()

        # Draw slice mode info overlay (in both modes, but only has content in slice mode)
        self.draw_slice_info_overlay()
        
    def draw_cube(self):
        """Draw a simple colored cube"""
        # Temporarily disable lighting to use vertex colors
        glDisable(GL_LIGHTING)

        # Define vertices of a cube
        vertices = [
            [-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
            [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]
        ]

        # Define faces (indices of vertices)
        faces = [
            [0, 1, 2, 3], [4, 7, 6, 5], [0, 4, 5, 1],
            [3, 2, 6, 7], [0, 3, 7, 4], [1, 5, 6, 2]
        ]

        # Define colors for each face
        colors = [
            [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0],
            [1.0, 1.0, 0.0], [1.0, 0.0, 1.0], [0.0, 1.0, 1.0]
        ]

        # Draw each face
        for i, face in enumerate(faces):
            glBegin(GL_QUADS)
            glColor3fv(colors[i])
            for vertex_index in face:
                glVertex3fv(vertices[vertex_index])
            glEnd()

        # Re-enable lighting for other objects
        glEnable(GL_LIGHTING)

    def draw_build_plate(self):
        """Draw cylindrical build plate (100mm diameter, 10mm thick, stainless steel) with grid"""
        # Build plate dimensions (in same units as CAD model)
        radius = 50.0  # 100mm diameter
        thickness = self.BUILD_PLATE_THICKNESS
        segments = 64  # Number of segments for smooth cylinder

        glPushMatrix()

        # Position the build plate at the bottom
        # Top surface will be at Y = BUILD_PLATE_TOP_Y (5mm)
        glTranslatef(0.0, -thickness/2, 0.0)

        # Set stainless steel material properties
        glEnable(GL_LIGHTING)
        glMaterialfv(GL_FRONT_AND_BACK, GL_AMBIENT, [0.25, 0.25, 0.25, 1.0])
        glMaterialfv(GL_FRONT_AND_BACK, GL_DIFFUSE, [0.4, 0.4, 0.4, 1.0])
        glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [0.774597, 0.774597, 0.774597, 1.0])
        glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 76.8)

        # Draw cylinder sides
        glBegin(GL_QUAD_STRIP)
        for i in range(segments + 1):
            angle = (i / segments) * 2.0 * np.pi
            x = radius * np.cos(angle)
            z = radius * np.sin(angle)

            # Normal points outward
            glNormal3f(np.cos(angle), 0.0, np.sin(angle))
            glVertex3f(x, 0.0, z)
            glVertex3f(x, thickness, z)
        glEnd()

        # Draw top disk
        glBegin(GL_TRIANGLE_FAN)
        glNormal3f(0.0, 1.0, 0.0)
        glVertex3f(0.0, thickness, 0.0)  # Center point
        for i in range(segments + 1):
            angle = (i / segments) * 2.0 * np.pi
            x = radius * np.cos(angle)
            z = radius * np.sin(angle)
            glVertex3f(x, thickness, z)
        glEnd()

        # Draw bottom disk
        glBegin(GL_TRIANGLE_FAN)
        glNormal3f(0.0, -1.0, 0.0)
        glVertex3f(0.0, 0.0, 0.0)  # Center point
        for i in range(segments + 1):
            angle = (segments - i) / segments * 2.0 * np.pi  # Reverse winding
            x = radius * np.cos(angle)
            z = radius * np.sin(angle)
            glVertex3f(x, 0.0, z)
        glEnd()

        # Draw grid on top of build plate
        self.draw_build_plate_grid(radius, thickness)

        # Draw outlines/edges for slicer-style appearance
        glDisable(GL_LIGHTING)
        glColor3f(0.1, 0.1, 0.1)  # Dark outline color
        glLineWidth(1.5)

        # Top edge outline
        glBegin(GL_LINE_LOOP)
        for i in range(segments):
            angle = (i / segments) * 2.0 * np.pi
            x = radius * np.cos(angle)
            z = radius * np.sin(angle)
            glVertex3f(x, thickness, z)
        glEnd()

        # Bottom edge outline
        glBegin(GL_LINE_LOOP)
        for i in range(segments):
            angle = (i / segments) * 2.0 * np.pi
            x = radius * np.cos(angle)
            z = radius * np.sin(angle)
            glVertex3f(x, 0.0, z)
        glEnd()

        glPopMatrix()

    def draw_build_plate_grid(self, radius, thickness):
        """Draw ghosted grid on build plate with major (20mm) and minor (5mm) lines"""
        grid_y = thickness + 0.1  # Slightly above the plate surface

        # Grid settings
        minor_spacing = 5.0   # 5mm minor grid
        major_spacing = 20.0  # 20mm major grid

        # Ghost colors (high alpha = more transparent)
        minor_color = (0.5, 0.5, 0.5, 0.15)  # Very faint minor lines
        major_color = (0.6, 0.6, 0.6, 0.3)   # Slightly more visible major lines

        glDisable(GL_LIGHTING)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_LINE_SMOOTH)
        glHint(GL_LINE_SMOOTH_HINT, GL_NICEST)

        # Clear grid labels
        self.grid_labels = []

        # Function to clip line to circle
        def clip_line_to_circle(x1, z1, x2, z2, r):
            """Clip a line segment to a circle, return clipped endpoints or None"""
            # For horizontal lines (z1 == z2)
            if abs(z1 - z2) < 0.001:
                z = z1
                if abs(z) > r:
                    return None
                x_extent = np.sqrt(r * r - z * z)
                return (max(x1, -x_extent), z, min(x2, x_extent), z)
            # For vertical lines (x1 == x2)
            elif abs(x1 - x2) < 0.001:
                x = x1
                if abs(x) > r:
                    return None
                z_extent = np.sqrt(r * r - x * x)
                return (x, max(z1, -z_extent), x, min(z2, z_extent))
            return None

        # Draw minor grid lines (every 5mm, excluding major lines)
        glLineWidth(1.0)
        glColor4f(*minor_color)
        glBegin(GL_LINES)

        # Vertical lines (along Z axis)
        for i in range(-int(radius / minor_spacing), int(radius / minor_spacing) + 1):
            x = i * minor_spacing
            # Skip major lines (every 4th minor line = 20mm)
            if i % 4 == 0:
                continue
            if abs(x) < radius:
                z_extent = np.sqrt(radius * radius - x * x)
                glVertex3f(x, grid_y, -z_extent)
                glVertex3f(x, grid_y, z_extent)

        # Horizontal lines (along X axis)
        for i in range(-int(radius / minor_spacing), int(radius / minor_spacing) + 1):
            z = i * minor_spacing
            # Skip major lines
            if i % 4 == 0:
                continue
            if abs(z) < radius:
                x_extent = np.sqrt(radius * radius - z * z)
                glVertex3f(-x_extent, grid_y, z)
                glVertex3f(x_extent, grid_y, z)

        glEnd()

        # Draw major grid lines (every 20mm)
        glLineWidth(1.5)
        glColor4f(*major_color)
        glBegin(GL_LINES)

        # Vertical major lines (along Z axis)
        for i in range(-int(radius / major_spacing), int(radius / major_spacing) + 1):
            x = i * major_spacing
            if abs(x) < radius:
                z_extent = np.sqrt(radius * radius - x * x)
                glVertex3f(x, grid_y, -z_extent)
                glVertex3f(x, grid_y, z_extent)

        # Horizontal major lines (along X axis)
        for i in range(-int(radius / major_spacing), int(radius / major_spacing) + 1):
            z = i * major_spacing
            if abs(z) < radius:
                x_extent = np.sqrt(radius * radius - z * z)
                glVertex3f(-x_extent, grid_y, z)
                glVertex3f(x_extent, grid_y, z)

        glEnd()

        # Draw center crosshair (0,0) slightly more visible
        glLineWidth(2.0)
        glColor4f(0.7, 0.7, 0.7, 0.4)
        glBegin(GL_LINES)
        # X axis through center
        glVertex3f(-radius, grid_y, 0)
        glVertex3f(radius, grid_y, 0)
        # Z axis through center
        glVertex3f(0, grid_y, -radius)
        glVertex3f(0, grid_y, radius)
        glEnd()

        # Collect label positions for major grid lines
        # We'll project 3D points to 2D screen coordinates
        modelview = glGetDoublev(GL_MODELVIEW_MATRIX)
        projection = glGetDoublev(GL_PROJECTION_MATRIX)
        viewport = glGetIntegerv(GL_VIEWPORT)

        # Add labels along X axis (at Z = -radius - offset for visibility)
        label_offset = 3.0  # Offset from grid edge
        x = -40  # Start from -40 to 40 in steps of 20
        while x <= 40:
            if abs(x) <= radius:
                # Project point to screen coordinates
                try:
                    # Label at the edge of the circle along Z axis
                    z_pos = -radius - label_offset
                    screen = gluProject(x, grid_y, z_pos, modelview, projection, viewport)
                    if screen:
                        # Store label info (screen coords and text)
                        self.grid_labels.append((screen[0], screen[1], str(int(x))))
                except:
                    pass
            x += major_spacing

        # Add labels along Z axis (at X = -radius - offset)
        z = -40
        while z <= 40:
            if abs(z) <= radius and z != 0:  # Skip 0 since we labeled it on X axis
                try:
                    x_pos = -radius - label_offset
                    screen = gluProject(x_pos, grid_y, z, modelview, projection, viewport)
                    if screen:
                        self.grid_labels.append((screen[0], screen[1], str(int(z))))
                except:
                    pass
            z += major_spacing

        glDisable(GL_BLEND)
        glDisable(GL_LINE_SMOOTH)

    def draw_orientation_triad(self):
        """Draw orientation triad gizmo in bottom-left corner"""
        # Save current state
        glPushAttrib(GL_ALL_ATTRIB_BITS)

        # Triad viewport settings
        triad_size = 80  # Size of the triad viewport in pixels
        margin = 10  # Margin from corner
        axis_length = 0.6  # Length of each axis (normalized)

        # Set up a small viewport in the bottom-left corner
        glViewport(margin, margin, triad_size, triad_size)

        # Set up orthographic projection for the triad
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(-1, 1, -1, 1, -2, 2)

        # Set up modelview with only rotation (no translation/zoom)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()

        # Apply the same rotation as the main view
        glRotatef(self.rotation_x, 1.0, 0.0, 0.0)
        glRotatef(self.rotation_y, 0.0, 1.0, 0.0)
        glRotatef(self.rotation_z, 0.0, 0.0, 1.0)

        # Disable lighting and depth test for clean rendering
        glDisable(GL_LIGHTING)
        glDisable(GL_DEPTH_TEST)
        glEnable(GL_LINE_SMOOTH)
        glHint(GL_LINE_SMOOTH_HINT, GL_NICEST)
        glLineWidth(2.0)

        # Draw X axis (Red) - plate plane
        glColor3f(0.9, 0.2, 0.2)
        glBegin(GL_LINES)
        glVertex3f(0, 0, 0)
        glVertex3f(axis_length, 0, 0)
        glEnd()
        # Arrow head
        glBegin(GL_TRIANGLES)
        glVertex3f(axis_length, 0, 0)
        glVertex3f(axis_length - 0.15, 0.05, 0)
        glVertex3f(axis_length - 0.15, -0.05, 0)
        glEnd()

        # Draw Z axis (Green) - plate plane (note: in our coord system Z is horizontal)
        glColor3f(0.2, 0.9, 0.2)
        glBegin(GL_LINES)
        glVertex3f(0, 0, 0)
        glVertex3f(0, 0, axis_length)
        glEnd()
        # Arrow head
        glBegin(GL_TRIANGLES)
        glVertex3f(0, 0, axis_length)
        glVertex3f(0.05, 0, axis_length - 0.15)
        glVertex3f(-0.05, 0, axis_length - 0.15)
        glEnd()

        # Draw Y axis (Blue) - build direction (vertical)
        glColor3f(0.2, 0.4, 0.9)
        glBegin(GL_LINES)
        glVertex3f(0, 0, 0)
        glVertex3f(0, axis_length, 0)
        glEnd()
        # Arrow head
        glBegin(GL_TRIANGLES)
        glVertex3f(0, axis_length, 0)
        glVertex3f(0.05, axis_length - 0.15, 0)
        glVertex3f(-0.05, axis_length - 0.15, 0)
        glEnd()

        # Store axis endpoint screen positions for labels
        # We need to project the axis endpoints to get label positions
        self.triad_labels = []

        # Get the current matrices for projection
        modelview = glGetDoublev(GL_MODELVIEW_MATRIX)
        projection = glGetDoublev(GL_PROJECTION_MATRIX)
        viewport = (margin, margin, triad_size, triad_size)

        try:
            # Project axis endpoints
            label_offset = 0.15
            x_end = gluProject(axis_length + label_offset, 0, 0, modelview, projection, viewport)
            y_end = gluProject(0, axis_length + label_offset, 0, modelview, projection, viewport)
            z_end = gluProject(0, 0, axis_length + label_offset, modelview, projection, viewport)

            if x_end:
                self.triad_labels.append((x_end[0], x_end[1], 'X', (0.9, 0.2, 0.2)))
            if y_end:
                self.triad_labels.append((y_end[0], y_end[1], 'Z', (0.2, 0.4, 0.9)))  # Y axis = Z (build)
            if z_end:
                self.triad_labels.append((z_end[0], z_end[1], 'Y', (0.2, 0.9, 0.2)))  # Z axis = Y (plate)
        except:
            pass

        # Restore matrices
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()

        # Restore viewport to full window
        glViewport(0, 0, self.width(), self.height())

        # Restore attributes
        glPopAttrib()

    def draw_grid_labels(self):
        """Draw grid labels using QPainter overlay"""
        # Get widget dimensions
        widget_height = self.height()
        pixel_ratio = self.devicePixelRatio()

        # Create painter for 2D overlay
        painter = QPainter(self)
        painter.beginNativePainting()
        painter.endNativePainting()

        # Draw grid labels if any
        if self.grid_labels:
            # Set up font - nice sans-serif
            font = QFont("Arial", 9)
            font.setStyleHint(QFont.StyleHint.SansSerif)
            painter.setFont(font)

            # Set ghosted text color (semi-transparent)
            text_color = QColor(180, 180, 180, 100)  # Light gray, semi-transparent
            painter.setPen(text_color)

            # Get font metrics for centering
            fm = QFontMetrics(font)

            # Draw each label
            for screen_x, screen_y, text in self.grid_labels:
                # Convert OpenGL screen coords to Qt coords (flip Y)
                qt_x = int(screen_x / pixel_ratio)
                qt_y = int((widget_height * pixel_ratio - screen_y) / pixel_ratio)

                # Center text on the point
                text_width = fm.horizontalAdvance(text)
                text_height = fm.height()

                painter.drawText(
                    qt_x - text_width // 2,
                    qt_y + text_height // 4,
                    text
                )

        # Draw triad axis labels
        if hasattr(self, 'triad_labels') and self.triad_labels:
            font = QFont("Arial", 10, QFont.Weight.Bold)
            font.setStyleHint(QFont.StyleHint.SansSerif)
            painter.setFont(font)
            fm = QFontMetrics(font)

            for screen_x, screen_y, text, color in self.triad_labels:
                # Convert coords
                qt_x = int(screen_x / pixel_ratio)
                qt_y = int((widget_height * pixel_ratio - screen_y) / pixel_ratio)

                # Set color for this axis label
                painter.setPen(QColor(int(color[0]*255), int(color[1]*255), int(color[2]*255)))

                text_width = fm.horizontalAdvance(text)
                painter.drawText(
                    qt_x - text_width // 2,
                    qt_y + fm.height() // 4,
                    text
                )

        painter.end()

    def draw_slice_info_overlay(self):
        """Draw slice information text overlay in slice mode"""
        if self.view_mode != 'slice' or not hasattr(self, 'slice_info_text'):
            return

        # Create painter for 2D overlay
        painter = QPainter(self)
        painter.beginNativePainting()
        painter.endNativePainting()

        # Set up font - larger, bold for visibility
        font = QFont("Arial", 12, QFont.Weight.Bold)
        font.setStyleHint(QFont.StyleHint.SansSerif)
        painter.setFont(font)

        # Set text color - solid white for good contrast
        text_color = QColor(255, 255, 255, 255)
        painter.setPen(text_color)

        # Draw text at the stored position
        x, y = self.slice_info_position
        painter.drawText(int(x), int(y), self.slice_info_text)

        painter.end()

    def draw_cad_model(self, model_data, is_selected=False):
        """Draw the actual CAD model using mesh data"""
        cad_model = model_data.get('model')
        model_bounds = model_data.get('bounds')
        model_center = model_data.get('center')
        position = model_data.get('position', [0, 0, 0])
        rotation = model_data.get('rotation', [0, 0, 0])
        scale = model_data.get('scale', [1, 1, 1])

        if not cad_model or not cad_model.vertices:
            return

        glPushMatrix()

        # First, apply user transformations (position, rotation, scale)
        glTranslatef(position[0], position[1], position[2])

        # Apply model rotation (around its geometric center - same as gizmo position)
        if model_bounds:
            min_x, min_y, min_z, max_x, max_y, max_z = model_bounds
            center_x = model_center[0]
            center_z = model_center[2]
            # Use geometric center Y (matches gizmo position)
            center_y = (max_y - min_y) / 2  # Height above build plate

            # Translate to model geometric center for rotation
            glTranslatef(center_x, center_y, center_z)
            glRotatef(rotation[2], 0, 0, 1)  # Z rotation
            glRotatef(rotation[1], 0, 1, 0)  # Y rotation
            glRotatef(rotation[0], 1, 0, 0)  # X rotation
            glTranslatef(-center_x, -center_y, -center_z)

        # Apply scale (around model geometric center)
        if scale != [1, 1, 1]:
            if model_bounds:
                center_y = (max_y - min_y) / 2
                glTranslatef(center_x, center_y, center_z)
                glScalef(scale[0], scale[1], scale[2])
                glTranslatef(-center_x, -center_y, -center_z)

        # Then translate so the model sits on top of the build plate
        # Center it in X and Z, but place bottom at Y=BUILD_PLATE_TOP_Y (top of build plate)
        if model_bounds:
            min_x, min_y, min_z, max_x, max_y, max_z = model_bounds
            # Center in X and Z, but align bottom (min_y) to the top of build plate
            glTranslatef(-model_center[0], self.BUILD_PLATE_TOP_Y - min_y, -model_center[2])
        else:
            # Fallback if no bounds
            glTranslatef(-model_center[0], self.BUILD_PLATE_TOP_Y - model_center[1], -model_center[2])

        # Enable lighting for proper shading
        glEnable(GL_LIGHTING)

        # Set material properties based on selection state
        if is_selected:
            # Blue color for selected model (darker for better contrast)
            glMaterialfv(GL_FRONT_AND_BACK, GL_AMBIENT, [0.15, 0.2, 0.35, 1.0])
            glMaterialfv(GL_FRONT_AND_BACK, GL_DIFFUSE, [0.2, 0.4, 0.8, 1.0])
            glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [0.3, 0.4, 0.6, 1.0])
            glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 30.0)
        else:
            # Default gray color for unselected models (darker for visibility)
            glMaterialfv(GL_FRONT_AND_BACK, GL_AMBIENT, [0.2, 0.2, 0.2, 1.0])
            glMaterialfv(GL_FRONT_AND_BACK, GL_DIFFUSE, [0.45, 0.45, 0.48, 1.0])
            glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [0.25, 0.25, 0.25, 1.0])
            glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 20.0)

        # Draw using vertex arrays for better performance
        vertices = cad_model.vertices
        normals = cad_model.normals
        indices = cad_model.indices

        # Enable vertex and normal arrays
        glEnableClientState(GL_VERTEX_ARRAY)
        glEnableClientState(GL_NORMAL_ARRAY)

        # Convert to numpy arrays for OpenGL
        vertex_array = np.array(vertices, dtype=np.float32)
        normal_array = np.array(normals, dtype=np.float32)
        index_array = np.array(indices, dtype=np.uint32)

        # Set the pointers
        glVertexPointer(3, GL_FLOAT, 0, vertex_array)
        glNormalPointer(GL_FLOAT, 0, normal_array)

        # Draw the triangles with lighting
        glDrawElements(GL_TRIANGLES, len(indices), GL_UNSIGNED_INT, index_array)

        # Disable face arrays
        glDisableClientState(GL_VERTEX_ARRAY)
        glDisableClientState(GL_NORMAL_ARRAY)

        # Draw BREP edges for clean outline appearance
        if cad_model.edge_vertices and cad_model.edge_indices:
            glDisable(GL_LIGHTING)
            glColor3f(0.0, 0.0, 0.0)  # Black edge color
            glLineWidth(1.5)

            # Enable line smoothing for better appearance
            glEnable(GL_LINE_SMOOTH)
            glHint(GL_LINE_SMOOTH_HINT, GL_NICEST)

            # Enable polygon offset to draw edges on top of faces
            glEnable(GL_POLYGON_OFFSET_LINE)
            glPolygonOffset(-1.0, -1.0)

            # Convert edge data to numpy arrays
            edge_vertex_array = np.array(cad_model.edge_vertices, dtype=np.float32)
            edge_index_array = np.array(cad_model.edge_indices, dtype=np.uint32)

            # Set up vertex array for edges
            glEnableClientState(GL_VERTEX_ARRAY)
            glVertexPointer(3, GL_FLOAT, 0, edge_vertex_array)

            # Draw edges as lines
            glDrawElements(GL_LINES, len(cad_model.edge_indices), GL_UNSIGNED_INT, edge_index_array)

            glDisableClientState(GL_VERTEX_ARRAY)
            glDisable(GL_POLYGON_OFFSET_LINE)
            glDisable(GL_LINE_SMOOTH)

        glPopMatrix()
        
    def load_cad_model(self, file_path):
        """Load and prepare CAD model for rendering (synchronous)"""
        print(f"Loading CAD model from: {file_path}")

        # Load the CAD file and extract mesh data
        model = load_cad_file(file_path)

        if model:
            return self.add_loaded_model(model, file_path)
        else:
            print("Failed to load CAD model")
            return None

    def add_loaded_model(self, model, file_path):
        """
        Add an already-loaded CAD model to the scene.

        Args:
            model: CADModel instance
            file_path: Path to the original CAD file

        Returns:
            Index of the newly added model, or None if model is invalid
        """
        if not model:
            return None

        # Extract filename for display
        import os
        filename = os.path.basename(file_path)

        # Create model data dictionary
        model_data = {
            'model': model,
            'name': filename,
            'path': file_path,
            'center': model.get_center(),
            'bounds': model.bounds,
            # Transformation properties
            'position': [0.0, 0.0, 0.0],  # Translation offset from auto-centered position
            'rotation': [0.0, 0.0, 0.0],  # Rotation in degrees around X, Y, Z
            'scale': [1.0, 1.0, 1.0]  # Scale factors for X, Y, Z
        }

        # Add to models list
        self.models.append(model_data)

        print(f"Model added successfully: {filename}")
        print(f"Model bounds: {model.bounds}")

        self.update()  # Trigger repaint

        # Return the index of the newly added model
        return len(self.models) - 1

    def set_selected_model(self, index):
        """Set the selected model by index"""
        if index is not None and 0 <= index < len(self.models):
            self.selected_model_index = index
        else:
            self.selected_model_index = None
        self.update()  # Trigger repaint

    def set_transform_mode(self, mode):
        """Set the transformation mode ('move', 'rotate', 'scale', or None)"""
        self.transform_mode = mode
        self.selected_gizmo_axis = None
        self.update()  # Trigger repaint

    def draw_gizmo(self, model_data):
        """Draw transformation gizmo for the selected model"""
        if not model_data:
            return

        # Get model center position
        model_bounds = model_data.get('bounds')
        model_center = model_data.get('center')
        position = model_data.get('position', [0, 0, 0])

        if not model_bounds:
            return

        min_x, min_y, min_z, max_x, max_y, max_z = model_bounds

        # Calculate gizmo position at the geometric center of the model
        # Model center is in model's local coordinates, we need world coordinates
        # The model is centered at (0, 0, 0) in X and Z, and sits on Y=0
        # So the actual center in world space is:
        gizmo_x = position[0]  # X offset
        gizmo_y = position[1] + (max_y - min_y) / 2  # Y position at geometric center
        gizmo_z = position[2]  # Z offset

        # Calculate appropriate gizmo size based on model dimensions
        model_size = max(max_x - min_x, max_y - min_y, max_z - min_z)
        gizmo_scale = max(model_size * 0.5, 20.0)  # At least 20mm, or 50% of model size

        # Draw appropriate gizmo based on mode
        if self.transform_mode == 'move' or self.transform_mode == 'scale':
            self.draw_arrow_triad(gizmo_x, gizmo_y, gizmo_z, gizmo_scale)
        elif self.transform_mode == 'rotate':
            self.draw_rotation_rings(gizmo_x, gizmo_y, gizmo_z, gizmo_scale)

    def draw_arrow_triad(self, x, y, z, scale=30.0):
        """Draw 3-axis arrow triad for move/scale gizmos"""
        glPushMatrix()
        glTranslatef(x, y, z)

        # Disable lighting for gizmo (flat shading)
        glDisable(GL_LIGHTING)
        glLineWidth(3.0)

        arrow_length = scale  # Scale arrow to model size
        arrow_head_length = scale * 0.15
        arrow_head_radius = scale * 0.06

        # X axis - Light gray or white if hovered
        if self.hovered_gizmo_axis == 'x':
            glColor3f(1.0, 1.0, 1.0)  # White when hovered
        else:
            glColor3f(0.7, 0.7, 0.7)  # Gray normally
        self.draw_arrow([0, 0, 0], [arrow_length, 0, 0], arrow_head_length, arrow_head_radius)

        # Y axis - Light gray or white if hovered
        if self.hovered_gizmo_axis == 'y':
            glColor3f(1.0, 1.0, 1.0)
        else:
            glColor3f(0.7, 0.7, 0.7)
        self.draw_arrow([0, 0, 0], [0, arrow_length, 0], arrow_head_length, arrow_head_radius)

        # Z axis - Light gray or white if hovered
        if self.hovered_gizmo_axis == 'z':
            glColor3f(1.0, 1.0, 1.0)
        else:
            glColor3f(0.7, 0.7, 0.7)
        self.draw_arrow([0, 0, 0], [0, 0, arrow_length], arrow_head_length, arrow_head_radius)

        glEnable(GL_LIGHTING)
        glPopMatrix()

    def draw_arrow(self, start, end, head_length, head_radius):
        """Draw a single arrow from start to end"""
        # Draw line
        glBegin(GL_LINES)
        glVertex3f(start[0], start[1], start[2])
        glVertex3f(end[0], end[1], end[2])
        glEnd()

        # Draw arrowhead (simplified cone)
        direction = np.array(end) - np.array(start)
        length = np.linalg.norm(direction)
        if length == 0:
            return

        direction = direction / length

        # Position arrowhead
        head_base = np.array(end) - direction * head_length

        # Draw simple pyramid for arrowhead
        perpendicular = np.cross(direction, [0, 1, 0] if abs(direction[1]) < 0.9 else [1, 0, 0])
        perpendicular = perpendicular / np.linalg.norm(perpendicular) * head_radius

        glBegin(GL_TRIANGLES)
        # Draw 4 triangular faces
        for i in range(4):
            angle1 = (i / 4.0) * 2 * np.pi
            angle2 = ((i + 1) / 4.0) * 2 * np.pi

            p1 = head_base + perpendicular * np.cos(angle1) + np.cross(direction, perpendicular) * np.sin(angle1)
            p2 = head_base + perpendicular * np.cos(angle2) + np.cross(direction, perpendicular) * np.sin(angle2)

            glVertex3fv(end)
            glVertex3fv(p1)
            glVertex3fv(p2)
        glEnd()

    def draw_rotation_rings(self, x, y, z, scale=35.0):
        """Draw 3-axis rotation rings for rotate gizmo"""
        glPushMatrix()
        glTranslatef(x, y, z)

        # Disable lighting for gizmo
        glDisable(GL_LIGHTING)

        ring_radius = scale  # Scale ring to model size
        segments = 64

        # X axis ring (rotates around X) - Light gray or white if hovered
        if self.hovered_gizmo_axis == 'x':
            glLineWidth(4.0)
            glColor3f(1.0, 1.0, 1.0)
        else:
            glLineWidth(2.0)
            glColor3f(0.7, 0.7, 0.7)
        glBegin(GL_LINE_LOOP)
        for i in range(segments):
            angle = (i / segments) * 2.0 * np.pi
            y_pos = ring_radius * np.cos(angle)
            z_pos = ring_radius * np.sin(angle)
            glVertex3f(0, y_pos, z_pos)
        glEnd()

        # Y axis ring (rotates around Y) - Light gray or white if hovered
        if self.hovered_gizmo_axis == 'y':
            glLineWidth(4.0)
            glColor3f(1.0, 1.0, 1.0)
        else:
            glLineWidth(2.0)
            glColor3f(0.7, 0.7, 0.7)
        glBegin(GL_LINE_LOOP)
        for i in range(segments):
            angle = (i / segments) * 2.0 * np.pi
            x_pos = ring_radius * np.cos(angle)
            z_pos = ring_radius * np.sin(angle)
            glVertex3f(x_pos, 0, z_pos)
        glEnd()

        # Z axis ring (rotates around Z) - Light gray or white if hovered
        if self.hovered_gizmo_axis == 'z':
            glLineWidth(4.0)
            glColor3f(1.0, 1.0, 1.0)
        else:
            glLineWidth(2.0)
            glColor3f(0.7, 0.7, 0.7)
        glBegin(GL_LINE_LOOP)
        for i in range(segments):
            angle = (i / segments) * 2.0 * np.pi
            x_pos = ring_radius * np.cos(angle)
            y_pos = ring_radius * np.sin(angle)
            glVertex3f(x_pos, y_pos, 0)
        glEnd()

        glEnable(GL_LIGHTING)
        glPopMatrix()

    def remove_model(self, index):
        """Remove a model from the scene"""
        if 0 <= index < len(self.models):
            self.models.pop(index)
            # Adjust selected index if needed
            if self.selected_model_index == index:
                self.selected_model_index = None
            elif self.selected_model_index is not None and self.selected_model_index > index:
                self.selected_model_index -= 1
            self.update()  # Trigger repaint
        
    def set_background_color(self, r, g, b):
        """Set the background color"""
        if self.context():
            self.makeCurrent()
            glClearColor(r, g, b, 1.0)
            self.update()  # Trigger repaint with new background color

    def reset_view(self):
        """Reset camera view to defaults"""
        self.camera_distance = 200.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.reset_rotation()
        
    def clear_scene(self):
        """Clear the scene properly"""
        if self.context():
            self.makeCurrent()
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            self.update()  # Trigger repaint after clearing
            
    def reset_rotation(self):
        """Reset rotation to initial state"""
        self.rotation_x = 30.0  # Reset to isometric
        self.rotation_y = 45.0
        self.rotation_z = 0.0
        self.update()  # Trigger repaint with reset rotation

    def mousePressEvent(self, event):
        """Handle mouse press events"""
        from PyQt6.QtCore import Qt
        if event.button() == Qt.MouseButton.LeftButton:
            # In slice mode, check for scrollbar interaction
            if self.view_mode == 'slice':
                if self.is_point_in_scrollbar(event.pos().x(), event.pos().y()):
                    self.scrollbar_dragging = True
                    self.handle_scrollbar_click(event.pos().y())
                    return

            # Check if in face picking mode
            if self.face_picking_mode:
                face_normal = self.pick_face_at(event.pos().x(), event.pos().y())
                if face_normal is not None:
                    self.align_face_to_build_plate(face_normal)
                    # Notify callback if set
                    if self.face_aligned_callback:
                        self.face_aligned_callback()
                # Exit face picking mode
                self.set_face_picking_mode(False)
                return

            # Check if clicking on a gizmo
            if self.hovered_gizmo_axis and self.transform_mode:
                self.is_dragging_gizmo = True
                self.selected_gizmo_axis = self.hovered_gizmo_axis
                self.transform_start_mouse = event.pos()

                # Store initial transformation values
                if self.selected_model_index is not None:
                    model_data = self.models[self.selected_model_index]
                    if self.transform_mode == 'move':
                        self.transform_start_value = model_data['position'].copy()
                    elif self.transform_mode == 'rotate':
                        self.transform_start_value = model_data['rotation'].copy()
                    elif self.transform_mode == 'scale':
                        self.transform_start_value = model_data['scale'].copy()
            else:
                # Normal camera controls (only in layout mode)
                if self.view_mode == 'layout':
                    modifiers = event.modifiers()

                    # Check which modifier key is held
                    if modifiers & Qt.KeyboardModifier.AltModifier:
                        self.is_panning = True
                    elif modifiers & Qt.KeyboardModifier.ControlModifier:
                        self.is_zooming = True
                    else:
                        self.is_rotating = True

            self.last_mouse_pos = event.pos()

    def mouseMoveEvent(self, event):
        """Handle mouse move events for rotation, panning, zooming, and gizmo interaction"""
        from PyQt6.QtCore import Qt

        # In slice mode, handle scrollbar interaction
        if self.view_mode == 'slice':
            # Check for scrollbar hover
            was_hover = self.scrollbar_hover
            self.scrollbar_hover = self.is_point_in_scrollbar(event.pos().x(), event.pos().y())
            if was_hover != self.scrollbar_hover:
                self.update()

            # Handle scrollbar dragging
            if self.scrollbar_dragging:
                self.handle_scrollbar_drag(event.pos().y())
                return

        # Check for gizmo hover (only when in transform mode and not currently dragging)
        if self.transform_mode and self.selected_model_index is not None and not self.is_dragging_gizmo:
            self.update_gizmo_hover(event.pos())

        # Handle gizmo dragging
        if self.is_dragging_gizmo and self.last_mouse_pos is not None:
            dx = event.pos().x() - self.last_mouse_pos.x()
            dy = event.pos().y() - self.last_mouse_pos.y()

            if self.selected_model_index is not None:
                self.apply_transformation(dx, dy)

            self.last_mouse_pos = event.pos()
            self.update()
            return  # Don't process camera controls when dragging gizmo

        # Normal camera controls (only if we have a valid interaction mode)
        if self.last_mouse_pos is not None and (self.is_rotating or self.is_panning or self.is_zooming):
            # Calculate mouse delta
            dx = event.pos().x() - self.last_mouse_pos.x()
            dy = event.pos().y() - self.last_mouse_pos.y()

            if self.is_rotating:
                # Update rotation angles based on mouse movement
                # Horizontal movement rotates around Y axis
                # Vertical movement rotates around X axis
                self.rotation_y += dx * 0.5  # Sensitivity factor
                self.rotation_x += dy * 0.5
            elif self.is_panning:
                # Pan the camera
                # Scale pan speed based on camera distance
                pan_speed = self.camera_distance * 0.002
                self.pan_x += dx * pan_speed
                self.pan_y -= dy * pan_speed  # Invert Y for natural panning
            elif self.is_zooming:
                # Zoom by changing camera distance
                # Vertical movement controls zoom
                zoom_speed = self.camera_distance * 0.01
                self.camera_distance -= dy * zoom_speed
                # Clamp camera distance to reasonable values
                self.camera_distance = max(10.0, min(1000.0, self.camera_distance))

            # Update last position
            self.last_mouse_pos = event.pos()

            # Trigger repaint
            self.update()

    def mouseReleaseEvent(self, event):
        """Handle mouse release events"""
        from PyQt6.QtCore import Qt
        if event.button() == Qt.MouseButton.LeftButton:
            # Emit transformation changed signal if we were dragging a gizmo
            was_dragging = self.is_dragging_gizmo

            self.is_rotating = False
            self.is_panning = False
            self.is_zooming = False
            self.is_dragging_gizmo = False
            self.selected_gizmo_axis = None
            self.scrollbar_dragging = False
            self.last_mouse_pos = None

            if was_dragging:
                self.transformation_changed.emit()

    def update_gizmo_hover(self, mouse_pos):
        """Update which gizmo axis is hovered using color-coded picking (pixel-perfect)"""
        if not self.transform_mode or self.selected_model_index is None:
            self.hovered_gizmo_axis = None
            return

        model_data = self.models[self.selected_model_index]
        model_bounds = model_data.get('bounds')

        if not model_bounds:
            self.hovered_gizmo_axis = None
            return

        old_hover = self.hovered_gizmo_axis

        # Perform color-coded picking
        picked_axis = self.pick_gizmo_axis(mouse_pos.x(), mouse_pos.y())
        self.hovered_gizmo_axis = picked_axis

        # Trigger update if hover changed
        if old_hover != self.hovered_gizmo_axis:
            self.update()

    def pick_gizmo_axis(self, mouse_x, mouse_y):
        """Pick gizmo axis using color-coded rendering"""
        if self.selected_model_index is None:
            return None

        self.makeCurrent()

        # Get device pixel ratio for HiDPI displays
        pixel_ratio = self.devicePixelRatio()
        actual_x = int(mouse_x * pixel_ratio)
        actual_y = int(mouse_y * pixel_ratio)

        # Save current state
        glPushAttrib(GL_ALL_ATTRIB_BITS)

        # Clear with black (no axis)
        glClearColor(0.0, 0.0, 0.0, 1.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        # Set up projection and modelview matrices (same as paintGL)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        width = self.width()
        height = self.height()
        if height == 0:
            height = 1
        gluPerspective(45.0, width / height, 0.1, 1000.0)

        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glTranslatef(0.0, 0.0, -self.camera_distance)
        glTranslatef(self.pan_x, self.pan_y, 0.0)
        glRotatef(self.rotation_x, 1.0, 0.0, 0.0)
        glRotatef(self.rotation_y, 0.0, 1.0, 0.0)
        glRotatef(self.rotation_z, 0.0, 0.0, 1.0)

        # Disable everything that could affect colors
        glDisable(GL_LIGHTING)
        glDisable(GL_TEXTURE_2D)
        glDisable(GL_BLEND)
        glDisable(GL_DITHER)
        glDisable(GL_FOG)
        glDisable(GL_LINE_SMOOTH)
        glDisable(GL_POLYGON_SMOOTH)
        glShadeModel(GL_FLAT)

        # Draw gizmo with picking colors
        model_data = self.models[self.selected_model_index]
        self.draw_gizmo_for_picking(model_data)

        glFlush()
        glFinish()

        # Read pixel at mouse position (flip Y for OpenGL coordinate system)
        fb_height = int(height * pixel_ratio)
        pixel_y = fb_height - actual_y - 1

        # Read pixel - glReadPixels returns a numpy array or bytes
        pixel_data = glReadPixels(actual_x, pixel_y, 1, 1, GL_RGB, GL_UNSIGNED_BYTE)

        # Restore state
        glPopAttrib()

        # Restore background color
        glClearColor(0.7, 0.7, 0.7, 1.0)

        # Parse pixel data - handle both numpy array and bytes formats
        r, g, b = 0, 0, 0
        if pixel_data is not None:
            # Convert to flat array/bytes
            if hasattr(pixel_data, 'flatten'):
                flat = pixel_data.flatten()
                if len(flat) >= 3:
                    r, g, b = int(flat[0]), int(flat[1]), int(flat[2])
            elif len(pixel_data) >= 3:
                r, g, b = int(pixel_data[0]), int(pixel_data[1]), int(pixel_data[2])

        # Determine which axis was picked based on color
        # Color thresholds (allow some tolerance)
        threshold = 50

        if r > threshold and g < threshold and b < threshold:
            return 'x'  # Red = X axis
        elif g > threshold and r < threshold and b < threshold:
            return 'y'  # Green = Y axis
        elif b > threshold and r < threshold and g < threshold:
            return 'z'  # Blue = Z axis

        return None

    def draw_gizmo_for_picking(self, model_data):
        """Draw gizmo with color-coded axes for picking"""
        if not model_data:
            return

        model_bounds = model_data.get('bounds')
        position = model_data.get('position', [0, 0, 0])

        if not model_bounds:
            return

        min_x, min_y, min_z, max_x, max_y, max_z = model_bounds

        # Calculate gizmo position (same as draw_gizmo)
        gizmo_x = position[0]
        gizmo_y = position[1] + (max_y - min_y) / 2
        gizmo_z = position[2]

        # Calculate gizmo size
        model_size = max(max_x - min_x, max_y - min_y, max_z - min_z)
        gizmo_scale = max(model_size * 0.5, 20.0)

        # Draw appropriate gizmo based on mode
        if self.transform_mode == 'move' or self.transform_mode == 'scale':
            self.draw_arrow_triad_for_picking(gizmo_x, gizmo_y, gizmo_z, gizmo_scale)
        elif self.transform_mode == 'rotate':
            self.draw_rotation_rings_for_picking(gizmo_x, gizmo_y, gizmo_z, gizmo_scale)

    def draw_arrow_triad_for_picking(self, x, y, z, scale=30.0):
        """Draw 3-axis arrow triad with picking colors (RGB = XYZ)"""
        glPushMatrix()
        glTranslatef(x, y, z)

        # Use thicker lines for better picking
        glLineWidth(8.0)

        arrow_length = scale
        arrow_head_length = scale * 0.2  # Larger head for picking
        arrow_head_radius = scale * 0.1

        # X axis - RED
        glColor3f(1.0, 0.0, 0.0)
        self.draw_arrow_for_picking([0, 0, 0], [arrow_length, 0, 0], arrow_head_length, arrow_head_radius)

        # Y axis - GREEN
        glColor3f(0.0, 1.0, 0.0)
        self.draw_arrow_for_picking([0, 0, 0], [0, arrow_length, 0], arrow_head_length, arrow_head_radius)

        # Z axis - BLUE
        glColor3f(0.0, 0.0, 1.0)
        self.draw_arrow_for_picking([0, 0, 0], [0, 0, arrow_length], arrow_head_length, arrow_head_radius)

        glPopMatrix()

    def draw_arrow_for_picking(self, start, end, head_length, head_radius):
        """Draw a single arrow for picking (thicker geometry)"""
        direction = np.array(end) - np.array(start)
        length = np.linalg.norm(direction)
        if length == 0:
            return

        direction = direction / length

        # Create perpendicular vectors for cylinder
        up = np.array([0, 1, 0]) if abs(direction[1]) < 0.9 else np.array([1, 0, 0])
        perp1 = np.cross(direction, up)
        perp1 = perp1 / np.linalg.norm(perp1)
        perp2 = np.cross(direction, perp1)

        # Draw cylinder (shaft) as a quad strip for better picking
        shaft_radius = head_radius * 0.4
        shaft_end = np.array(end) - direction * head_length
        segments = 8

        glBegin(GL_QUAD_STRIP)
        for i in range(segments + 1):
            angle = (i / segments) * 2 * np.pi
            offset = (perp1 * np.cos(angle) + perp2 * np.sin(angle)) * shaft_radius
            glVertex3fv(np.array(start) + offset)
            glVertex3fv(shaft_end + offset)
        glEnd()

        # Draw arrowhead as cone
        head_base = np.array(end) - direction * head_length

        # Draw cone with triangles
        glBegin(GL_TRIANGLE_FAN)
        glVertex3fv(end)  # Tip
        for i in range(segments + 1):
            angle = (i / segments) * 2 * np.pi
            offset = (perp1 * np.cos(angle) + perp2 * np.sin(angle)) * head_radius
            glVertex3fv(head_base + offset)
        glEnd()

        # Draw base of cone
        glBegin(GL_TRIANGLE_FAN)
        glVertex3fv(head_base)  # Center
        for i in range(segments + 1):
            angle = ((segments - i) / segments) * 2 * np.pi  # Reverse winding
            offset = (perp1 * np.cos(angle) + perp2 * np.sin(angle)) * head_radius
            glVertex3fv(head_base + offset)
        glEnd()

    def draw_rotation_rings_for_picking(self, x, y, z, scale=35.0):
        """Draw 3-axis rotation rings with picking colors"""
        glPushMatrix()
        glTranslatef(x, y, z)

        ring_radius = scale
        tube_radius = scale * 0.06  # Thickness of the ring tube
        ring_segments = 48
        tube_segments = 8

        # X axis ring - RED (YZ plane)
        glColor3f(1.0, 0.0, 0.0)
        self.draw_torus_for_picking(ring_radius, tube_radius, ring_segments, tube_segments, 'x')

        # Y axis ring - GREEN (XZ plane)
        glColor3f(0.0, 1.0, 0.0)
        self.draw_torus_for_picking(ring_radius, tube_radius, ring_segments, tube_segments, 'y')

        # Z axis ring - BLUE (XY plane)
        glColor3f(0.0, 0.0, 1.0)
        self.draw_torus_for_picking(ring_radius, tube_radius, ring_segments, tube_segments, 'z')

        glPopMatrix()

    def draw_torus_for_picking(self, ring_radius, tube_radius, ring_segments, tube_segments, axis):
        """Draw a torus (donut shape) for picking"""
        for i in range(ring_segments):
            glBegin(GL_QUAD_STRIP)
            for j in range(tube_segments + 1):
                for k in range(2):
                    ring_angle = ((i + k) / ring_segments) * 2 * np.pi
                    tube_angle = (j / tube_segments) * 2 * np.pi

                    # Calculate point on torus
                    # Standard torus: (R + r*cos(v)) * cos(u), (R + r*cos(v)) * sin(u), r*sin(v)
                    cos_tube = np.cos(tube_angle)
                    sin_tube = np.sin(tube_angle)
                    cos_ring = np.cos(ring_angle)
                    sin_ring = np.sin(ring_angle)

                    r = ring_radius + tube_radius * cos_tube

                    if axis == 'x':
                        # Ring around X axis (in YZ plane)
                        px = tube_radius * sin_tube
                        py = r * cos_ring
                        pz = r * sin_ring
                    elif axis == 'y':
                        # Ring around Y axis (in XZ plane)
                        px = r * cos_ring
                        py = tube_radius * sin_tube
                        pz = r * sin_ring
                    else:  # z
                        # Ring around Z axis (in XY plane)
                        px = r * cos_ring
                        py = r * sin_ring
                        pz = tube_radius * sin_tube

                    glVertex3f(px, py, pz)
            glEnd()

    def get_axis_screen_direction(self, axis):
        """Get the screen-space direction of a world axis for the current view"""
        # Get current matrices
        modelview = glGetDoublev(GL_MODELVIEW_MATRIX)
        projection = glGetDoublev(GL_PROJECTION_MATRIX)
        viewport = glGetIntegerv(GL_VIEWPORT)

        # Get gizmo center in world space
        model_data = self.models[self.selected_model_index]
        position = model_data.get('position', [0, 0, 0])
        model_bounds = model_data.get('bounds')

        if model_bounds:
            min_x, min_y, min_z, max_x, max_y, max_z = model_bounds
            gizmo_center = [position[0], position[1] + (max_y - min_y) / 2, position[2]]
        else:
            gizmo_center = position

        # Define axis direction in world space
        if axis == 'x':
            axis_dir = [1, 0, 0]
        elif axis == 'y':
            axis_dir = [0, 1, 0]
        else:  # z
            axis_dir = [0, 0, 1]

        try:
            # Project gizmo center to screen
            center_screen = gluProject(gizmo_center[0], gizmo_center[1], gizmo_center[2],
                                       modelview, projection, viewport)

            # Project a point along the axis
            end_point = [gizmo_center[0] + axis_dir[0],
                        gizmo_center[1] + axis_dir[1],
                        gizmo_center[2] + axis_dir[2]]
            end_screen = gluProject(end_point[0], end_point[1], end_point[2],
                                   modelview, projection, viewport)

            if center_screen and end_screen:
                # Calculate screen-space direction
                screen_dx = end_screen[0] - center_screen[0]
                screen_dy = end_screen[1] - center_screen[1]

                # Negate only Z axis to fix inverted movement
                # X axis should not be negated for correct mouse movement
                if axis == 'z':
                    screen_dx = -screen_dx
                    screen_dy = -screen_dy

                # Normalize
                length = np.sqrt(screen_dx * screen_dx + screen_dy * screen_dy)
                if length > 0.001:
                    return (screen_dx / length, screen_dy / length)
        except:
            pass

        # Fallback to default directions
        if axis == 'x':
            return (1, 0)   # X not negated
        elif axis == 'y':
            return (0, 1)   # Y not negated
        else:  # z
            return (0, -1)  # Z negated

    def apply_transformation(self, dx, dy):
        """Apply transformation based on mouse movement projected onto axis direction"""
        if self.selected_model_index is None or not self.selected_gizmo_axis:
            return

        model_data = self.models[self.selected_model_index]

        # Get the screen-space direction of the selected axis
        axis_dir = self.get_axis_screen_direction(self.selected_gizmo_axis)

        # Project mouse movement onto the axis direction
        # Note: dy is negated because screen Y is flipped vs OpenGL Y
        projected = dx * axis_dir[0] + (-dy) * axis_dir[1]

        # Movement sensitivity
        move_speed = 0.5  # mm per pixel
        rotate_speed = 1.0  # degrees per pixel
        scale_speed = 0.01  # scale factor per pixel

        if self.transform_mode == 'move':
            # Move along selected axis using projected mouse movement
            # Coordinate system note: OpenGL Y=user's Z (vertical), OpenGL Z=user's Y (horizontal)
            if self.selected_gizmo_axis == 'x':
                model_data['position'][0] += projected * move_speed
            elif self.selected_gizmo_axis == 'y':
                model_data['position'][1] += projected * move_speed
            elif self.selected_gizmo_axis == 'z':
                model_data['position'][2] += projected * move_speed

        elif self.transform_mode == 'rotate':
            # Rotate around selected axis using projected movement
            if self.selected_gizmo_axis == 'x':
                model_data['rotation'][0] += projected * rotate_speed
            elif self.selected_gizmo_axis == 'y':
                model_data['rotation'][1] += projected * rotate_speed
            elif self.selected_gizmo_axis == 'z':
                model_data['rotation'][2] += projected * rotate_speed

        elif self.transform_mode == 'scale':
            # Scale along selected axis
            # Use projected movement (positive = bigger)
            scale_delta = projected * scale_speed
            if self.selected_gizmo_axis == 'x':
                model_data['scale'][0] = max(0.1, model_data['scale'][0] + scale_delta)
            elif self.selected_gizmo_axis == 'y':
                model_data['scale'][1] = max(0.1, model_data['scale'][1] + scale_delta)
            elif self.selected_gizmo_axis == 'z':
                model_data['scale'][2] = max(0.1, model_data['scale'][2] + scale_delta)

    def set_face_picking_mode(self, enabled, callback=None):
        """Enable or disable face picking mode for aligning faces to build plate"""
        self.face_picking_mode = enabled
        self.face_aligned_callback = callback
        if enabled:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def pick_face_at(self, mouse_x, mouse_y):
        """Pick a face at the given mouse position and return its normal"""
        if self.selected_model_index is None:
            return None

        model_data = self.models[self.selected_model_index]
        cad_model = model_data.get('model')

        if not cad_model or not cad_model.vertices or not cad_model.indices:
            return None

        self.makeCurrent()

        # Get device pixel ratio for HiDPI displays
        pixel_ratio = self.devicePixelRatio()
        actual_x = int(mouse_x * pixel_ratio)
        actual_y = int(mouse_y * pixel_ratio)

        # Save current state
        glPushAttrib(GL_ALL_ATTRIB_BITS)

        # Clear with black
        glClearColor(0.0, 0.0, 0.0, 1.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        # Set up matrices (same as paintGL)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        width = self.width()
        height = self.height()
        if height == 0:
            height = 1
        gluPerspective(45.0, width / height, 0.1, 1000.0)

        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glTranslatef(0.0, 0.0, -self.camera_distance)
        glTranslatef(self.pan_x, self.pan_y, 0.0)
        glRotatef(self.rotation_x, 1.0, 0.0, 0.0)
        glRotatef(self.rotation_y, 0.0, 1.0, 0.0)
        glRotatef(self.rotation_z, 0.0, 0.0, 1.0)

        # Disable lighting and effects
        glDisable(GL_LIGHTING)
        glDisable(GL_TEXTURE_2D)
        glDisable(GL_BLEND)
        glDisable(GL_DITHER)
        glShadeModel(GL_FLAT)

        # Draw model with color-coded triangles
        self.draw_model_for_face_picking(model_data)

        glFlush()
        glFinish()

        # Read pixel
        fb_height = int(height * pixel_ratio)
        pixel_y = fb_height - actual_y - 1

        pixel_data = glReadPixels(actual_x, pixel_y, 1, 1, GL_RGB, GL_UNSIGNED_BYTE)

        # Restore state
        glPopAttrib()
        glClearColor(0.7, 0.7, 0.7, 1.0)

        # Decode triangle index from color
        r, g, b = 0, 0, 0
        if pixel_data is not None:
            if hasattr(pixel_data, 'flatten'):
                flat = pixel_data.flatten()
                if len(flat) >= 3:
                    r, g, b = int(flat[0]), int(flat[1]), int(flat[2])
            elif len(pixel_data) >= 3:
                r, g, b = int(pixel_data[0]), int(pixel_data[1]), int(pixel_data[2])

        # Decode triangle index (RGB encodes triangle index)
        triangle_index = r + g * 256 + b * 65536 - 1  # -1 because we start at 1

        if triangle_index < 0:
            return None

        # Get triangle vertices and compute normal
        indices = cad_model.indices
        vertices = cad_model.vertices

        if triangle_index * 3 + 2 >= len(indices):
            return None

        i0 = indices[triangle_index * 3]
        i1 = indices[triangle_index * 3 + 1]
        i2 = indices[triangle_index * 3 + 2]

        v0 = np.array(vertices[i0])
        v1 = np.array(vertices[i1])
        v2 = np.array(vertices[i2])

        # Compute face normal
        edge1 = v1 - v0
        edge2 = v2 - v0
        normal = np.cross(edge1, edge2)
        length = np.linalg.norm(normal)
        if length > 0:
            normal = normal / length
        else:
            return None

        return normal

    def draw_model_for_face_picking(self, model_data):
        """Draw model with each triangle having a unique color for picking"""
        cad_model = model_data.get('model')
        model_bounds = model_data.get('bounds')
        model_center = model_data.get('center')
        position = model_data.get('position', [0, 0, 0])
        rotation = model_data.get('rotation', [0, 0, 0])
        scale = model_data.get('scale', [1, 1, 1])

        if not cad_model or not cad_model.vertices:
            return

        glPushMatrix()

        # Apply same transformations as draw_cad_model
        glTranslatef(position[0], position[1], position[2])

        if model_bounds:
            min_x, min_y, min_z, max_x, max_y, max_z = model_bounds
            center_x = model_center[0]
            center_z = model_center[2]
            center_y = (max_y - min_y) / 2

            glTranslatef(center_x, center_y, center_z)
            glRotatef(rotation[2], 0, 0, 1)
            glRotatef(rotation[1], 0, 1, 0)
            glRotatef(rotation[0], 1, 0, 0)
            glTranslatef(-center_x, -center_y, -center_z)

        if scale != [1, 1, 1]:
            if model_bounds:
                center_y = (max_y - min_y) / 2
                glTranslatef(center_x, center_y, center_z)
                glScalef(scale[0], scale[1], scale[2])
                glTranslatef(-center_x, -center_y, -center_z)

        if model_bounds:
            min_x, min_y, min_z, max_x, max_y, max_z = model_bounds
            # Place model on top of build plate (same as draw_cad_model)
            glTranslatef(-model_center[0], self.BUILD_PLATE_TOP_Y - min_y, -model_center[2])

        # Draw triangles with unique colors
        vertices = cad_model.vertices
        indices = cad_model.indices
        num_triangles = len(indices) // 3

        glBegin(GL_TRIANGLES)
        for tri in range(num_triangles):
            # Encode triangle index as RGB color (starting at 1 to distinguish from black background)
            color_id = tri + 1
            r = (color_id % 256) / 255.0
            g = ((color_id // 256) % 256) / 255.0
            b = ((color_id // 65536) % 256) / 255.0
            glColor3f(r, g, b)

            i0 = indices[tri * 3]
            i1 = indices[tri * 3 + 1]
            i2 = indices[tri * 3 + 2]

            glVertex3fv(vertices[i0])
            glVertex3fv(vertices[i1])
            glVertex3fv(vertices[i2])
        glEnd()

        glPopMatrix()

    def align_face_to_build_plate(self, face_normal):
        """Calculate rotation to align a face normal to point downward (toward build plate)"""
        if self.selected_model_index is None or face_normal is None:
            return

        model_data = self.models[self.selected_model_index]

        # We want the face normal to point down (-Y direction)
        # So we need to rotate the model so that face_normal aligns with (0, -1, 0)
        target = np.array([0, -1, 0])
        normal = np.array(face_normal)

        # Handle case where normal is already aligned
        dot = np.dot(normal, target)
        if abs(dot - 1.0) < 0.0001:
            # Already aligned
            model_data['rotation'] = [0.0, 0.0, 0.0]
            self.update()
            return
        elif abs(dot + 1.0) < 0.0001:
            # Opposite direction - rotate 180 around X or Z
            model_data['rotation'] = [180.0, 0.0, 0.0]
            self.update()
            return

        # Calculate rotation axis (cross product)
        axis = np.cross(normal, target)
        axis_length = np.linalg.norm(axis)
        if axis_length < 0.0001:
            return

        axis = axis / axis_length

        # Calculate rotation angle
        angle = np.arccos(np.clip(dot, -1.0, 1.0))
        angle_deg = np.degrees(angle)

        # Convert axis-angle to Euler angles (approximate)
        # This is a simplified conversion - for more accuracy, use quaternions
        # For now, we'll compute a rotation matrix and extract Euler angles

        # Rodrigues' rotation formula to get rotation matrix
        K = np.array([
            [0, -axis[2], axis[1]],
            [axis[2], 0, -axis[0]],
            [-axis[1], axis[0], 0]
        ])
        R = np.eye(3) + np.sin(angle) * K + (1 - np.cos(angle)) * (K @ K)

        # Extract Euler angles (XYZ order) from rotation matrix
        # This assumes the rotation order is X, then Y, then Z
        if abs(R[2, 0]) < 0.9999:
            rot_y = -np.arcsin(R[2, 0])
            rot_x = np.arctan2(R[2, 1] / np.cos(rot_y), R[2, 2] / np.cos(rot_y))
            rot_z = np.arctan2(R[1, 0] / np.cos(rot_y), R[0, 0] / np.cos(rot_y))
        else:
            # Gimbal lock
            rot_z = 0
            if R[2, 0] < 0:
                rot_y = np.pi / 2
                rot_x = np.arctan2(R[0, 1], R[0, 2])
            else:
                rot_y = -np.pi / 2
                rot_x = np.arctan2(-R[0, 1], -R[0, 2])

        # Convert to degrees and update model
        model_data['rotation'] = [
            np.degrees(rot_x),
            np.degrees(rot_y),
            np.degrees(rot_z)
        ]

        self.update()

    def set_view_mode(self, mode, layer_thickness=None):
        """Set the view mode to 'layout' or 'slice'"""
        self.view_mode = mode
        if layer_thickness is not None:
            self.layer_thickness = layer_thickness

        if mode == 'slice':
            # Request async slicing (UI will handle the worker)
            self.slicing_requested.emit(self.models, self.layer_thickness)
        else:
            # Clear slices and hatching
            self.sliced_layers = []
            self.hatching_data = {}

        self.update()

    def set_sliced_layers(self, sliced_layers):
        """Set the sliced layers after async slicing completes."""
        self.sliced_layers = sliced_layers
        self.current_layer_index = 0
        self.update()

        # Generate hatching if enabled and parameters are set
        if self.hatching_enabled and self.hatching_params:
            self.request_hatching_generation()

    def request_hatching_generation(self):
        """Request async hatching generation (UI will handle the worker)."""
        if self.sliced_layers and self.hatching_params:
            self.hatching_requested.emit(
                self.sliced_layers,
                self.hatching_params,
                self.hatching_strategy
            )

    def set_hatching_data(self, hatching_data):
        """Set the hatching data after async hatching generation completes."""
        self.hatching_data = hatching_data
        self.update()

    def update_slice_thickness(self, layer_thickness):
        """Update the layer thickness and re-slice"""
        self.layer_thickness = layer_thickness
        if self.view_mode == 'slice':
            # Request async slicing with new thickness
            self.slicing_requested.emit(self.models, self.layer_thickness)

    def set_current_layer(self, layer_index):
        """Set the current layer index for slice view"""
        self.current_layer_index = layer_index
        self.update()

    def slice_all_models(self):
        """Slice all loaded models into layers"""
        self.sliced_layers = []

        for model_data in self.models:
            layers = self.slice_model(model_data)
            self.sliced_layers.append(layers)

    def slice_model(self, model_data):
        """Slice a single model into horizontal sections with unique outlines

        Returns a list of sections, where each section represents a range of layers
        with the same outline shape
        """
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

        # Calculate model height in world space (after transformations)
        model_height = (max_y - min_y) * scale[1]
        # Bottom of model sits on top of build plate + user position offset
        model_bottom = self.BUILD_PLATE_TOP_Y + position[1]

        # Calculate number of layers
        num_layers = int(np.ceil(model_height / self.layer_thickness))
        if num_layers == 0:
            return []

        # Slice all layers first
        all_layers = []
        for layer_idx in range(num_layers):
            layer_z = model_bottom + (layer_idx + 0.5) * self.layer_thickness
            segments = self.slice_at_height(cad_model, model_data, layer_z)
            all_layers.append({
                'z_height': layer_z,
                'layer_index': layer_idx,
                'segments': segments
            })

        # Group consecutive layers with the same outline into sections
        sections = self.group_layers_into_sections(all_layers, model_bottom)

        return sections

    def group_layers_into_sections(self, all_layers, model_bottom):
        """Group consecutive layers with identical outlines into sections

        Returns a list of sections:
        [{
            'start_layer': int,
            'end_layer': int,
            'z_start': float,
            'z_end': float,
            'segments': [...],
            'layer_count': int
        }, ...]
        """
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

            # Check if this layer has the same outline as the previous
            if self.outlines_are_equal(current_layer['segments'], prev_layer['segments']):
                # Extend current section
                current_section['end_layer'] = i
                current_section['z_end'] = current_layer['z_height']
                current_section['layer_count'] += 1
            else:
                # Save current section and start a new one
                sections.append(current_section)
                current_section = {
                    'start_layer': i,
                    'end_layer': i,
                    'z_start': current_layer['z_height'],
                    'z_end': current_layer['z_height'],
                    'segments': current_layer['segments'],
                    'layer_count': 1
                }

        # Don't forget the last section
        sections.append(current_section)

        return sections

    def outlines_are_equal(self, segments1, segments2, tolerance=0.01):
        """Check if two sets of outline segments are equal (within tolerance)

        Two outlines are considered equal if they have the same number of segments
        and each segment matches (order may differ)
        """
        if len(segments1) != len(segments2):
            return False

        if len(segments1) == 0:
            return True

        # Sort segments for comparison
        # Sort by first point, then second point
        def segment_key(seg):
            x1, z1, x2, z2 = seg
            # Normalize so smaller point comes first
            if (x1, z1) > (x2, z2):
                x1, z1, x2, z2 = x2, z2, x1, z1
            return (round(x1 / tolerance), round(z1 / tolerance),
                    round(x2 / tolerance), round(z2 / tolerance))

        sorted_seg1 = sorted(segments1, key=segment_key)
        sorted_seg2 = sorted(segments2, key=segment_key)

        # Compare each segment
        for seg1, seg2 in zip(sorted_seg1, sorted_seg2):
            x1_1, z1_1, x2_1, z2_1 = seg1
            x1_2, z1_2, x2_2, z2_2 = seg2

            # Check if segments match (considering both orderings)
            if not (self.points_equal((x1_1, z1_1), (x1_2, z1_2), tolerance) and
                    self.points_equal((x2_1, z2_1), (x2_2, z2_2), tolerance)) and \
               not (self.points_equal((x1_1, z1_1), (x2_2, z2_2), tolerance) and
                    self.points_equal((x2_1, z2_1), (x1_2, z1_2), tolerance)):
                return False

        return True

    def points_equal(self, p1, p2, tolerance=0.01):
        """Check if two 2D points are equal within tolerance"""
        return abs(p1[0] - p2[0]) < tolerance and abs(p1[1] - p2[1]) < tolerance

    def slice_at_height(self, cad_model, model_data, z_height):
        """Find all line segments where triangles intersect a horizontal plane at z_height

        Returns a list of line segments [(x1, y1, x2, y2), ...]
        """
        vertices = np.array(cad_model.vertices)
        indices = cad_model.indices

        # Get transformation parameters
        position = model_data.get('position', [0, 0, 0])
        rotation = model_data.get('rotation', [0, 0, 0])
        scale = model_data.get('scale', [1, 1, 1])
        model_bounds = model_data.get('bounds')
        model_center = model_data.get('center')

        if not model_bounds:
            return []

        min_x, min_y, min_z, max_x, max_y, max_z = model_bounds

        segments = []

        # Process each triangle
        num_triangles = len(indices) // 3
        for tri_idx in range(num_triangles):
            i0 = indices[tri_idx * 3]
            i1 = indices[tri_idx * 3 + 1]
            i2 = indices[tri_idx * 3 + 2]

            # Get triangle vertices
            v0 = np.array(vertices[i0])
            v1 = np.array(vertices[i1])
            v2 = np.array(vertices[i2])

            # Apply transformations to get world space coordinates
            v0_world = self.transform_vertex(v0, model_data)
            v1_world = self.transform_vertex(v1, model_data)
            v2_world = self.transform_vertex(v2, model_data)

            # Check if triangle intersects the Z plane
            segment = self.intersect_triangle_plane(v0_world, v1_world, v2_world, z_height)
            if segment:
                segments.append(segment)

        return segments

    def transform_vertex(self, vertex, model_data):
        """Transform a vertex from model space to world space

        This must match the transformation pipeline in draw_cad_model exactly
        """
        position = model_data.get('position', [0, 0, 0])
        rotation = model_data.get('rotation', [0, 0, 0])
        scale = model_data.get('scale', [1, 1, 1])
        model_bounds = model_data.get('bounds')
        model_center = model_data.get('center')

        if not model_bounds:
            return vertex

        min_x, min_y, min_z, max_x, max_y, max_z = model_bounds

        # Start with the vertex in model space
        v = np.array(vertex, dtype=float)

        # Step 1: Center the model (align bottom to Y=0, center in X and Z)
        v[0] -= model_center[0]
        v[1] -= min_y
        v[2] -= model_center[2]

        # Step 2: Apply scale around geometric center
        center_y = (max_y - min_y) / 2
        center_x = model_center[0]
        center_z = model_center[2]

        # Translate to geometric center
        v[0] -= center_x
        v[1] -= center_y
        v[2] -= center_z

        # Apply scale
        v = v * scale

        # Translate back
        v[0] += center_x
        v[1] += center_y
        v[2] += center_z

        # Step 3: Apply rotation around geometric center
        # Translate to geometric center
        v[0] -= center_x
        v[1] -= center_y
        v[2] -= center_z

        # Apply rotations in order: Z, Y, X
        # Convert degrees to radians
        rx = np.radians(rotation[0])
        ry = np.radians(rotation[1])
        rz = np.radians(rotation[2])

        # Z rotation
        if abs(rz) > 1e-6:
            cos_z = np.cos(rz)
            sin_z = np.sin(rz)
            x_new = v[0] * cos_z - v[1] * sin_z
            y_new = v[0] * sin_z + v[1] * cos_z
            v[0] = x_new
            v[1] = y_new

        # Y rotation
        if abs(ry) > 1e-6:
            cos_y = np.cos(ry)
            sin_y = np.sin(ry)
            x_new = v[0] * cos_y + v[2] * sin_y
            z_new = -v[0] * sin_y + v[2] * cos_y
            v[0] = x_new
            v[2] = z_new

        # X rotation
        if abs(rx) > 1e-6:
            cos_x = np.cos(rx)
            sin_x = np.sin(rx)
            y_new = v[1] * cos_x - v[2] * sin_x
            z_new = v[1] * sin_x + v[2] * cos_x
            v[1] = y_new
            v[2] = z_new

        # Translate back
        v[0] += center_x
        v[1] += center_y
        v[2] += center_z

        # Step 4: Apply position translation
        v = v + position

        return v

    def intersect_triangle_plane(self, v0, v1, v2, z_height):
        """Find where a triangle intersects a horizontal plane at z_height

        Returns a line segment (x1, y1, x2, y2) or None if no intersection
        Note: y here refers to the horizontal plane coordinate (model's Z in our system)
        """
        # Check which vertices are above and below the plane
        # We're slicing on the Y axis (vertical in our system)
        y0, y1, y2 = v0[1], v1[1], v2[1]

        # Find intersection points
        intersections = []

        # Check edge v0-v1
        if (y0 <= z_height <= y1) or (y1 <= z_height <= y0):
            if abs(y1 - y0) > 1e-6:  # Avoid division by zero
                t = (z_height - y0) / (y1 - y0)
                x = v0[0] + t * (v1[0] - v0[0])
                z = v0[2] + t * (v1[2] - v0[2])
                intersections.append((x, z))

        # Check edge v1-v2
        if (y1 <= z_height <= y2) or (y2 <= z_height <= y1):
            if abs(y2 - y1) > 1e-6:
                t = (z_height - y1) / (y2 - y1)
                x = v1[0] + t * (v2[0] - v1[0])
                z = v1[2] + t * (v2[2] - v1[2])
                intersections.append((x, z))

        # Check edge v2-v0
        if (y2 <= z_height <= y0) or (y0 <= z_height <= y2):
            if abs(y0 - y2) > 1e-6:
                t = (z_height - y2) / (y0 - y2)
                x = v2[0] + t * (v0[0] - v2[0])
                z = v2[2] + t * (v0[2] - v2[2])
                intersections.append((x, z))

        # Remove duplicates
        unique_intersections = []
        for p in intersections:
            is_duplicate = False
            for existing in unique_intersections:
                if abs(p[0] - existing[0]) < 1e-6 and abs(p[1] - existing[1]) < 1e-6:
                    is_duplicate = True
                    break
            if not is_duplicate:
                unique_intersections.append(p)

        # Should have exactly 2 intersection points for a valid slice
        if len(unique_intersections) == 2:
            p1, p2 = unique_intersections
            return (p1[0], p1[1], p2[0], p2[1])

        return None

    def draw_sliced_layers(self):
        """Draw the current layer's outlines for all models"""
        if not self.sliced_layers:
            return

        # Disable lighting for line drawing
        glDisable(GL_LIGHTING)
        glLineWidth(2.0)

        # Draw each model's sections
        for model_idx, model_sections in enumerate(self.sliced_layers):
            if not model_sections:
                continue

            # Find which section contains the current layer index
            section = self.find_section_for_layer(model_sections, self.current_layer_index)
            if not section:
                continue

            segments = section['segments']
            # Use the middle Z height of the section for display
            z_height = (section['z_start'] + section['z_end']) / 2

            # Set color - use different colors for different models
            if model_idx == self.selected_model_index:
                glColor3f(0.2, 0.4, 0.9)  # Blue for selected
            else:
                glColor3f(0.2, 0.2, 0.2)  # Dark gray for unselected

            # Draw all segments
            glBegin(GL_LINES)
            for seg in segments:
                x1, z1, x2, z2 = seg
                # Remember: in our coordinate system, the slice Y is the world Y
                glVertex3f(x1, z_height, z1)
                glVertex3f(x2, z_height, z2)
            glEnd()

        # Draw hatching if enabled
        if self.hatching_enabled:
            self.draw_hatching_for_layer(self.current_layer_index)

        # Re-enable lighting
        glEnable(GL_LIGHTING)

    def find_section_for_layer(self, sections, layer_index):
        """Find the section that contains the given layer index"""
        for section in sections:
            if section['start_layer'] <= layer_index <= section['end_layer']:
                return section
        return None

    def get_total_layers(self):
        """Get the total number of layers across all models"""
        if not self.sliced_layers:
            return 0

        max_layers = 0
        for model_sections in self.sliced_layers:
            if model_sections:
                # Find the highest end_layer across all sections
                for section in model_sections:
                    max_layers = max(max_layers, section['end_layer'] + 1)

        return max_layers

    def draw_scrollbar_gizmo(self):
        """Draw a scrollbar gizmo on the right side of the viewport for layer navigation"""
        if not self.sliced_layers:
            return

        total_layers = self.get_total_layers()
        if total_layers <= 0:
            return

        # Switch to 2D orthographic projection for UI overlay
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, self.width(), self.height(), 0, -1, 1)

        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()

        # Disable depth test and lighting for 2D overlay
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_LIGHTING)

        # Calculate scrollbar dimensions
        viewport_height = self.height()
        scrollbar_x = self.width() - self.scrollbar_width - self.scrollbar_margin
        scrollbar_y = self.scrollbar_margin
        scrollbar_height = viewport_height - 2 * self.scrollbar_margin

        # Draw scrollbar track (background)
        glColor4f(0.3, 0.3, 0.3, 0.5)
        glBegin(GL_QUADS)
        glVertex2f(scrollbar_x, scrollbar_y)
        glVertex2f(scrollbar_x + self.scrollbar_width, scrollbar_y)
        glVertex2f(scrollbar_x + self.scrollbar_width, scrollbar_y + scrollbar_height)
        glVertex2f(scrollbar_x, scrollbar_y + scrollbar_height)
        glEnd()

        # Calculate thumb position and size
        thumb_height = max(20, scrollbar_height / max(total_layers, 1))
        thumb_y = scrollbar_y + (scrollbar_height - thumb_height) * (self.current_layer_index / max(total_layers - 1, 1))

        # Draw scrollbar thumb (handle)
        if self.scrollbar_hover or self.scrollbar_dragging:
            glColor4f(0.6, 0.6, 0.8, 0.9)  # Lighter when hovered/dragging
        else:
            glColor4f(0.4, 0.4, 0.6, 0.8)  # Normal color

        glBegin(GL_QUADS)
        glVertex2f(scrollbar_x + 2, thumb_y)
        glVertex2f(scrollbar_x + self.scrollbar_width - 2, thumb_y)
        glVertex2f(scrollbar_x + self.scrollbar_width - 2, thumb_y + thumb_height)
        glVertex2f(scrollbar_x + 2, thumb_y + thumb_height)
        glEnd()

        # Store layer info for text rendering
        self.slice_info_text = f"{self.current_layer_index + 1}/{total_layers}"
        self.slice_info_position = (scrollbar_x - 60, scrollbar_y + scrollbar_height // 2)

        # Restore matrices and state
        glPopMatrix()
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)

        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)

        # Store scrollbar info for mouse interaction
        self.scrollbar_rect = (scrollbar_x, scrollbar_y, self.scrollbar_width, scrollbar_height)
        self.scrollbar_thumb_rect = (scrollbar_x, thumb_y, self.scrollbar_width, thumb_height)

    def is_point_in_scrollbar(self, x, y):
        """Check if a point is inside the scrollbar area"""
        if not hasattr(self, 'scrollbar_rect'):
            return False
        sx, sy, sw, sh = self.scrollbar_rect
        return sx <= x <= sx + sw and sy <= y <= sy + sh

    def handle_scrollbar_click(self, y):
        """Handle click on scrollbar"""
        if not hasattr(self, 'scrollbar_rect'):
            return

        sx, sy, sw, sh = self.scrollbar_rect
        total_layers = self.get_total_layers()
        if total_layers <= 0:
            return

        # Calculate which layer was clicked based on Y position
        relative_y = y - sy
        layer_index = int((relative_y / sh) * total_layers)
        layer_index = max(0, min(total_layers - 1, layer_index))

        self.set_current_layer(layer_index)

    def handle_scrollbar_drag(self, y):
        """Handle dragging the scrollbar"""
        self.handle_scrollbar_click(y)
    # ============================================================================
    # Hatching Integration Methods
    # ============================================================================

    def enable_hatching(self, enabled=True):
        """Enable or disable hatching visualization in slice mode."""
        self.hatching_enabled = enabled
        self.update()

    def set_hatching_parameters(self, hatch_params, strategy=None):
        """
        Set hatching parameters and optionally strategy.

        Args:
            hatch_params: HatchingParameters instance
            strategy: HatchingStrategy enum value (optional)
        """
        from hatching import HatchingParameters, HatchingStrategy

        self.hatching_params = hatch_params
        if strategy is not None:
            self.hatching_strategy = strategy
        elif self.hatching_strategy is None:
            self.hatching_strategy = HatchingStrategy.LINES

        # Regenerate hatching if in slice mode
        if self.view_mode == 'slice' and self.hatching_enabled:
            self.generate_all_hatching()
            self.update()

    def generate_all_hatching(self):
        """Generate hatching for all sliced layers."""
        if not self.sliced_layers or not self.hatching_params:
            return

        from hatching_integration import prepare_hatching_for_all_layers

        self.hatching_data = {}

        # Generate hatching for each model
        for model_idx, layer_sections in enumerate(self.sliced_layers):
            model_hatching = prepare_hatching_for_all_layers(
                layer_sections,
                self.hatching_params,
                self.hatching_strategy
            )

            # Store hatching data with (model_idx, layer_idx) keys to avoid collisions
            for layer_idx, hatch_lines in model_hatching.items():
                key = (model_idx, layer_idx)
                self.hatching_data[key] = hatch_lines

    def draw_hatching_for_layer(self, layer_index):
        """
        Render hatching lines for a specific layer.

        Args:
            layer_index: Layer index to render
        """
        if not self.hatching_enabled:
            return

        glDisable(GL_LIGHTING)
        glDisable(GL_DEPTH_TEST)

        # Draw hatching for each model at this layer index
        for model_idx in range(len(self.sliced_layers)):
            key = (model_idx, layer_index)
            if key not in self.hatching_data:
                continue

            hatch_lines = self.hatching_data[key]

            # Get the actual Z height for this model's layer
            model_sections = self.sliced_layers[model_idx]
            section = self.find_section_for_layer(model_sections, layer_index)
            if not section:
                continue

            # Use the middle Z height of the section
            layer_y = (section['z_start'] + section['z_end']) / 2

            # Draw contour lines (red, thicker)
            contour_lines = [line for line in hatch_lines if line.is_contour]
            if contour_lines:
                glColor3f(0.8, 0.1, 0.1)  # Red
                glLineWidth(2.0)
                glBegin(GL_LINES)
                for line in contour_lines:
                    # Note: segments are (x, z) but we render in 3D (x, y, z)
                    # where y is the height dimension
                    glVertex3f(line.start[0], layer_y, line.start[1])
                    glVertex3f(line.end[0], layer_y, line.end[1])
                glEnd()

            # Draw infill lines (blue, thinner)
            infill_lines = [line for line in hatch_lines if not line.is_contour]
            if infill_lines:
                glColor3f(0.1, 0.4, 0.8)  # Blue
                glLineWidth(1.0)
                glBegin(GL_LINES)
                for line in infill_lines:
                    glVertex3f(line.start[0], layer_y, line.start[1])
                    glVertex3f(line.end[0], layer_y, line.end[1])
                glEnd()

        glLineWidth(1.0)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)

    def get_hatching_statistics(self):
        """
        Get statistics about generated hatching.

        Returns:
            Dictionary with statistics or None if no hatching
        """
        if not self.hatching_data:
            return None

        from hatching_integration import get_hatching_statistics

        # Convert from {(model_idx, layer_idx): [HatchLine]} to {layer_idx: [HatchLine]}
        # by merging all models' hatching for each layer
        merged_data = {}
        for (model_idx, layer_idx), hatch_lines in self.hatching_data.items():
            if layer_idx not in merged_data:
                merged_data[layer_idx] = []
            merged_data[layer_idx].extend(hatch_lines)

        return get_hatching_statistics(merged_data)

    def export_to_obp(self, filepath):
        """
        Export sliced and hatched model to OBP format for Freemelt.

        Args:
            filepath: Path to save OBP file

        Returns:
            True if successful, False otherwise
        """
        if not self.hatching_data:
            return False

        try:
            from hatching_integration import convert_hatching_to_obp_format

            # Convert from {(model_idx, layer_idx): [HatchLine]} to {layer_idx: [HatchLine]}
            # by merging all models' hatching for each layer
            merged_data = {}
            for (model_idx, layer_idx), hatch_lines in self.hatching_data.items():
                if layer_idx not in merged_data:
                    merged_data[layer_idx] = []
                merged_data[layer_idx].extend(hatch_lines)

            # Convert hatching data to OBP format
            obp_layers = convert_hatching_to_obp_format(
                merged_data,
                self.layer_thickness
            )

            # TODO: Use obplib from Freemelt to write OBP file
            # This is a placeholder until obplib integration is complete
            import json
            with open(filepath, 'w') as f:
                json.dump(obp_layers, f, indent=2)

            return True

        except Exception as e:
            print(f"Export error: {e}")
            return False
