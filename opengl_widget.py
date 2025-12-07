from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtGui import QOpenGLContext, QSurfaceFormat, QPainter, QFont, QColor, QFontMetrics
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from OpenGL.GL import *
from OpenGL.GLU import *
import sys
import numpy as np
from cad_loader import load_cad_file, CADModel

class OpenGLWidget(QOpenGLWidget):
    # Signal emitted when model transformation changes via gizmo
    transformation_changed = pyqtSignal()
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
        
    def initializeGL(self):
        """Initialize OpenGL context and settings"""
        # Set up OpenGL context
        self.makeCurrent()
        
        # Enable depth testing
        glEnable(GL_DEPTH_TEST)

        # Disable face culling to see both sides of faces
        glDisable(GL_CULL_FACE)
        
        # Set clear color to 10% gray background
        glClearColor(0.1, 0.1, 0.1, 1.0)
        
        # Set up lighting (basic)
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        
        # Set light properties
        light_position = [1.0, 1.0, 1.0, 0.0]
        glLightfv(GL_LIGHT0, GL_POSITION, light_position)
        
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

        # Move camera back based on zoom level
        glTranslatef(0.0, 0.0, -self.camera_distance)

        # Apply pan (in camera space, before rotation)
        glTranslatef(self.pan_x, self.pan_y, 0.0)

        # Apply rotations around the build plate center
        glRotatef(self.rotation_x, 1.0, 0.0, 0.0)
        glRotatef(self.rotation_y, 0.0, 1.0, 0.0)
        glRotatef(self.rotation_z, 0.0, 0.0, 1.0)

        # Always draw the build plate first
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
        thickness = 10.0  # 10mm thick
        segments = 64  # Number of segments for smooth cylinder

        glPushMatrix()

        # Position the build plate at the bottom
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
        # Center it in X and Z, but place bottom at Y=0 (top of build plate)
        if model_bounds:
            min_x, min_y, min_z, max_x, max_y, max_z = model_bounds
            # Center in X and Z, but align bottom (min_y) to Y=0
            glTranslatef(-model_center[0], -min_y, -model_center[2])
        else:
            # Fallback if no bounds
            glTranslatef(-model_center[0], -model_center[1], -model_center[2])

        # Enable lighting for proper shading
        glEnable(GL_LIGHTING)

        # Set material properties based on selection state
        if is_selected:
            # Blue color for selected model
            glMaterialfv(GL_FRONT_AND_BACK, GL_AMBIENT, [0.2, 0.3, 0.5, 1.0])
            glMaterialfv(GL_FRONT_AND_BACK, GL_DIFFUSE, [0.3, 0.5, 0.9, 1.0])
            glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [0.4, 0.5, 0.7, 1.0])
            glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 30.0)
        else:
            # Default gray color for unselected models
            glMaterialfv(GL_FRONT_AND_BACK, GL_AMBIENT, [0.3, 0.3, 0.3, 1.0])
            glMaterialfv(GL_FRONT_AND_BACK, GL_DIFFUSE, [0.6, 0.6, 0.65, 1.0])
            glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [0.3, 0.3, 0.3, 1.0])
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
        """Load and prepare CAD model for rendering"""
        print(f"Loading CAD model from: {file_path}")

        # Load the CAD file and extract mesh data
        model = load_cad_file(file_path)

        if model:
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

            print(f"Model loaded successfully: {filename}")
            print(f"Model bounds: {model.bounds}")

            self.update()  # Trigger repaint

            # Return the index of the newly added model
            return len(self.models) - 1
        else:
            print("Failed to load CAD model")
            return None

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
                # Normal camera controls
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
        glClearColor(0.1, 0.1, 0.1, 1.0)

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
        glClearColor(0.1, 0.1, 0.1, 1.0)

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
            glTranslatef(-model_center[0], -min_y, -model_center[2])

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