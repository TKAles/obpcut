"""
Application constants and configuration values.
"""

# Build plate constants (dimensions in mm)
BUILD_PLATE_RADIUS = 50.0  # 100mm diameter
BUILD_PLATE_THICKNESS = 10.0  # 10mm thick
BUILD_PLATE_SEGMENTS = 64  # Number of segments for smooth cylinder

# Grid constants (dimensions in mm)
GRID_MINOR_SPACING = 5.0  # Minor grid lines every 5mm
GRID_MAJOR_SPACING = 20.0  # Major grid lines every 20mm
GRID_OFFSET = 0.1  # Distance above build plate surface

# Grid rendering constants
GRID_MINOR_COLOR = (0.5, 0.5, 0.5, 0.15)  # Very faint minor lines
GRID_MAJOR_COLOR = (0.6, 0.6, 0.6, 0.3)  # Slightly more visible major lines
GRID_MINOR_LINE_WIDTH = 1.0
GRID_MAJOR_LINE_WIDTH = 1.5

# Camera constants
DEFAULT_CAMERA_DISTANCE = 200.0  # Initial camera distance from origin
DEFAULT_ROTATION_X = 30.0  # Isometric tilt
DEFAULT_ROTATION_Y = 45.0  # Isometric rotation
DEFAULT_ROTATION_Z = 0.0
CAMERA_ZOOM_SPEED = 10.0  # Units per scroll step
CAMERA_ROTATION_SPEED = 0.5  # Degrees per pixel
CAMERA_PAN_SPEED = 0.1  # Units per pixel

# Rendering constants
PERSPECTIVE_FOV = 45.0  # Field of view in degrees
PERSPECTIVE_NEAR = 0.1  # Near clipping plane
PERSPECTIVE_FAR = 1000.0  # Far clipping plane
BACKGROUND_COLOR = (0.7, 0.7, 0.7, 1.0)  # Light gray
FPS_TARGET = 30  # Target frames per second
FRAME_TIME_MS = 33  # ~30 FPS

# Material properties - Stainless steel
STEEL_AMBIENT = (0.25, 0.25, 0.25, 1.0)
STEEL_DIFFUSE = (0.4, 0.4, 0.4, 1.0)
STEEL_SPECULAR = (0.774597, 0.774597, 0.774597, 1.0)
STEEL_SHININESS = 76.8

# Material properties - Default model
DEFAULT_MODEL_DIFFUSE = (0.8, 0.8, 0.8, 1.0)
DEFAULT_MODEL_SPECULAR = (1.0, 1.0, 1.0, 1.0)
DEFAULT_MODEL_SHININESS = 50.0

# Lighting constants
AMBIENT_LIGHT = (0.4, 0.4, 0.4, 1.0)
KEY_LIGHT_DIFFUSE = (0.6, 0.6, 0.6, 1.0)
KEY_LIGHT_SPECULAR = (0.3, 0.3, 0.3, 1.0)
FILL_LIGHT_DIFFUSE = (0.4, 0.4, 0.4, 1.0)
FILL_LIGHT_SPECULAR = (0.1, 0.1, 0.1, 1.0)
BACK_LIGHT_DIFFUSE = (0.3, 0.3, 0.3, 1.0)

# Gizmo constants
GIZMO_ARROW_SCALE = 30.0  # Scale of transformation arrows
GIZMO_ROTATION_SCALE = 35.0  # Scale of rotation rings
GIZMO_LINE_WIDTH = 3.0  # Width of gizmo lines
GIZMO_AXIS_COLORS = {
    'x': (1.0, 0.0, 0.0),  # Red for X
    'y': (0.0, 1.0, 0.0),  # Green for Y
    'z': (0.0, 0.0, 1.0),  # Blue for Z
}
GIZMO_HOVER_BRIGHTNESS = 1.5  # Brightness multiplier when hovering

# Transformation constants
TRANSFORM_MOUSE_SENSITIVITY = 0.5  # Sensitivity for mouse-based transforms
ROTATION_SNAP_ANGLE = 15.0  # Degrees for rotation snapping (when holding modifier)
SCALE_SENSITIVITY = 0.01  # Scale change per pixel

# Slicing constants
DEFAULT_LAYER_THICKNESS = 0.2  # mm
SLICE_VIEW_SIZE = 60.0  # Show 120mm x 120mm area
SCROLLBAR_WIDTH = 20  # pixels
SCROLLBAR_MARGIN = 10  # pixels from right edge

# File dialog constants
SUPPORTED_CAD_FORMATS = "CAD Files (*.step *.iges);;All Files (*)"

# UI constants
DEFAULT_LAYER_THICKNESS_STR = "0.2"
TRANSFORM_DIALOG_MIN_WIDTH = 280
TRANSFORM_DIALOG_MARGIN_TOP = 100
TRANSFORM_DIALOG_MARGIN_RIGHT = 10

# Position limits (mm)
POSITION_MIN = -1000
POSITION_MAX = 1000

# Scale limits
SCALE_MIN = 0.01
SCALE_MAX = 100

# Rotation limits (degrees)
ROTATION_MIN = -360
ROTATION_MAX = 360
