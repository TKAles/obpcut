"""
Transform Dialog for manual entry of Move, Scale, and Rotate values
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QDoubleSpinBox, QCheckBox, QPushButton, QTabWidget,
    QWidget, QFrame, QButtonGroup, QRadioButton
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
import numpy as np
from constants import (
    POSITION_MIN, POSITION_MAX, SCALE_MIN, SCALE_MAX,
    ROTATION_MIN, ROTATION_MAX, TRANSFORM_DIALOG_MIN_WIDTH
)


class TransformDialog(QDialog):
    """Dialog for manual transformation entry"""

    # Signals emitted when values change
    position_changed = pyqtSignal(float, float, float)
    scale_changed = pyqtSignal(float, float, float)
    rotation_changed = pyqtSignal(float, float, float)
    align_face_requested = pyqtSignal()  # Request to enter face alignment mode

    def __init__(self, parent=None, mode='move'):
        super().__init__(parent)
        self.setWindowTitle("Transform")
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setMinimumWidth(TRANSFORM_DIALOG_MIN_WIDTH)

        # Track linked scaling state
        self.scale_linked = True
        self.updating_scale = False  # Prevent recursive updates

        # Store reference to OpenGL widget
        self.opengl_widget = None

        # Build UI
        self.setup_ui()

        # Set initial tab based on mode
        if mode == 'move':
            self.tab_widget.setCurrentIndex(0)
        elif mode == 'scale':
            self.tab_widget.setCurrentIndex(1)
        elif mode == 'rotate':
            self.tab_widget.setCurrentIndex(2)

    def setup_ui(self):
        """Build the dialog UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Create tab widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Create tabs
        self.create_move_tab()
        self.create_scale_tab()
        self.create_rotate_tab()

        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

    def create_move_tab(self):
        """Create the Move tab with absolute position controls"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)

        # Position group
        group = QGroupBox("Absolute Position (mm)")
        grid = QGridLayout(group)

        # X position
        grid.addWidget(QLabel("X:"), 0, 0)
        self.pos_x = QDoubleSpinBox()
        self.pos_x.setRange(POSITION_MIN, POSITION_MAX)
        self.pos_x.setDecimals(2)
        self.pos_x.setSuffix(" mm")
        self.pos_x.valueChanged.connect(self.on_position_changed)
        grid.addWidget(self.pos_x, 0, 1)

        # Y position
        grid.addWidget(QLabel("Y:"), 1, 0)
        self.pos_y = QDoubleSpinBox()
        self.pos_y.setRange(POSITION_MIN, POSITION_MAX)
        self.pos_y.setDecimals(2)
        self.pos_y.setSuffix(" mm")
        self.pos_y.valueChanged.connect(self.on_position_changed)
        grid.addWidget(self.pos_y, 1, 1)

        # Z position
        grid.addWidget(QLabel("Z:"), 2, 0)
        self.pos_z = QDoubleSpinBox()
        self.pos_z.setRange(POSITION_MIN, POSITION_MAX)
        self.pos_z.setDecimals(2)
        self.pos_z.setSuffix(" mm")
        self.pos_z.valueChanged.connect(self.on_position_changed)
        grid.addWidget(self.pos_z, 2, 1)

        layout.addWidget(group)

        # Center on build plate button
        center_btn = QPushButton("Center on Build Plate")
        center_btn.clicked.connect(self.center_on_build_plate)
        layout.addWidget(center_btn)

        # Drop to build plate button
        drop_btn = QPushButton("Drop to Build Plate")
        drop_btn.clicked.connect(self.drop_to_build_plate)
        layout.addWidget(drop_btn)

        layout.addStretch()

        self.tab_widget.addTab(tab, "Move")

    def create_scale_tab(self):
        """Create the Scale tab with scale factor controls"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)

        # Scale group
        group = QGroupBox("Scale Factors")
        grid = QGridLayout(group)

        # Link checkbox
        self.link_scale = QCheckBox("Link Dimensions")
        self.link_scale.setChecked(True)
        self.link_scale.toggled.connect(self.on_link_toggled)
        grid.addWidget(self.link_scale, 0, 0, 1, 2)

        # X scale
        grid.addWidget(QLabel("X:"), 1, 0)
        self.scale_x = QDoubleSpinBox()
        self.scale_x.setRange(SCALE_MIN, SCALE_MAX)
        self.scale_x.setDecimals(3)
        self.scale_x.setValue(1.0)
        self.scale_x.setSingleStep(0.1)
        self.scale_x.valueChanged.connect(lambda v: self.on_scale_changed('x', v))
        grid.addWidget(self.scale_x, 1, 1)

        # Y scale
        grid.addWidget(QLabel("Y:"), 2, 0)
        self.scale_y = QDoubleSpinBox()
        self.scale_y.setRange(SCALE_MIN, SCALE_MAX)
        self.scale_y.setDecimals(3)
        self.scale_y.setValue(1.0)
        self.scale_y.setSingleStep(0.1)
        self.scale_y.valueChanged.connect(lambda v: self.on_scale_changed('y', v))
        grid.addWidget(self.scale_y, 2, 1)

        # Z scale
        grid.addWidget(QLabel("Z:"), 3, 0)
        self.scale_z = QDoubleSpinBox()
        self.scale_z.setRange(SCALE_MIN, SCALE_MAX)
        self.scale_z.setDecimals(3)
        self.scale_z.setValue(1.0)
        self.scale_z.setSingleStep(0.1)
        self.scale_z.valueChanged.connect(lambda v: self.on_scale_changed('z', v))
        grid.addWidget(self.scale_z, 3, 1)

        layout.addWidget(group)

        # Preset buttons
        preset_layout = QHBoxLayout()

        btn_50 = QPushButton("50%")
        btn_50.clicked.connect(lambda: self.set_uniform_scale(0.5))
        preset_layout.addWidget(btn_50)

        btn_100 = QPushButton("100%")
        btn_100.clicked.connect(lambda: self.set_uniform_scale(1.0))
        preset_layout.addWidget(btn_100)

        btn_200 = QPushButton("200%")
        btn_200.clicked.connect(lambda: self.set_uniform_scale(2.0))
        preset_layout.addWidget(btn_200)

        layout.addLayout(preset_layout)
        layout.addStretch()

        self.tab_widget.addTab(tab, "Scale")

    def create_rotate_tab(self):
        """Create the Rotate tab with rotation controls"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)

        # Rotation angles group
        angles_group = QGroupBox("Rotation Angles (degrees)")
        grid = QGridLayout(angles_group)

        # X rotation
        grid.addWidget(QLabel("X:"), 0, 0)
        self.rot_x = QDoubleSpinBox()
        self.rot_x.setRange(ROTATION_MIN, ROTATION_MAX)
        self.rot_x.setDecimals(1)
        self.rot_x.setSuffix("°")
        self.rot_x.valueChanged.connect(self.on_rotation_changed)
        grid.addWidget(self.rot_x, 0, 1)

        # Y rotation
        grid.addWidget(QLabel("Y:"), 1, 0)
        self.rot_y = QDoubleSpinBox()
        self.rot_y.setRange(ROTATION_MIN, ROTATION_MAX)
        self.rot_y.setDecimals(1)
        self.rot_y.setSuffix("°")
        self.rot_y.valueChanged.connect(self.on_rotation_changed)
        grid.addWidget(self.rot_y, 1, 1)

        # Z rotation
        grid.addWidget(QLabel("Z:"), 2, 0)
        self.rot_z = QDoubleSpinBox()
        self.rot_z.setRange(ROTATION_MIN, ROTATION_MAX)
        self.rot_z.setDecimals(1)
        self.rot_z.setSuffix("°")
        self.rot_z.valueChanged.connect(self.on_rotation_changed)
        grid.addWidget(self.rot_z, 2, 1)

        layout.addWidget(angles_group)

        # Quick rotation buttons
        quick_group = QGroupBox("Quick Rotations")
        quick_layout = QGridLayout(quick_group)

        btn_x90 = QPushButton("X +90°")
        btn_x90.clicked.connect(lambda: self.add_rotation('x', 90))
        quick_layout.addWidget(btn_x90, 0, 0)

        btn_xn90 = QPushButton("X -90°")
        btn_xn90.clicked.connect(lambda: self.add_rotation('x', -90))
        quick_layout.addWidget(btn_xn90, 0, 1)

        btn_y90 = QPushButton("Y +90°")
        btn_y90.clicked.connect(lambda: self.add_rotation('y', 90))
        quick_layout.addWidget(btn_y90, 1, 0)

        btn_yn90 = QPushButton("Y -90°")
        btn_yn90.clicked.connect(lambda: self.add_rotation('y', -90))
        quick_layout.addWidget(btn_yn90, 1, 1)

        btn_z90 = QPushButton("Z +90°")
        btn_z90.clicked.connect(lambda: self.add_rotation('z', 90))
        quick_layout.addWidget(btn_z90, 2, 0)

        btn_zn90 = QPushButton("Z -90°")
        btn_zn90.clicked.connect(lambda: self.add_rotation('z', -90))
        quick_layout.addWidget(btn_zn90, 2, 1)

        layout.addWidget(quick_group)

        # Face alignment group
        align_group = QGroupBox("Align Face to Build Plate")
        align_layout = QVBoxLayout(align_group)

        align_info = QLabel("Click a face on the model to align it flat to the build plate.")
        align_info.setWordWrap(True)
        align_info.setStyleSheet("color: gray;")
        align_layout.addWidget(align_info)

        self.align_face_btn = QPushButton("Select Face to Align")
        self.align_face_btn.setCheckable(True)
        self.align_face_btn.toggled.connect(self.on_align_face_toggled)
        align_layout.addWidget(self.align_face_btn)

        layout.addWidget(align_group)

        # Reset rotation button
        reset_btn = QPushButton("Reset Rotation")
        reset_btn.clicked.connect(self.reset_rotation)
        layout.addWidget(reset_btn)

        layout.addStretch()

        self.tab_widget.addTab(tab, "Rotate")

    def set_opengl_widget(self, widget):
        """Set reference to OpenGL widget for updating values"""
        self.opengl_widget = widget

    def update_from_model(self, model_data):
        """Update dialog values from model data"""
        if not model_data:
            return

        # Block signals while updating
        self.pos_x.blockSignals(True)
        self.pos_y.blockSignals(True)
        self.pos_z.blockSignals(True)
        self.scale_x.blockSignals(True)
        self.scale_y.blockSignals(True)
        self.scale_z.blockSignals(True)
        self.rot_x.blockSignals(True)
        self.rot_y.blockSignals(True)
        self.rot_z.blockSignals(True)

        # Update position
        # Note: Internal coordinates have Y/Z swapped (OpenGL Y=visual Z, OpenGL Z=visual Y)
        position = model_data.get('position', [0, 0, 0])
        self.pos_x.setValue(position[0])
        self.pos_y.setValue(position[2])  # Display position[2] as Y
        self.pos_z.setValue(position[1])  # Display position[1] as Z

        # Update scale
        scale = model_data.get('scale', [1, 1, 1])
        self.scale_x.setValue(scale[0])
        self.scale_y.setValue(scale[2])  # Display scale[2] as Y
        self.scale_z.setValue(scale[1])  # Display scale[1] as Z

        # Update rotation
        rotation = model_data.get('rotation', [0, 0, 0])
        self.rot_x.setValue(rotation[0])
        self.rot_y.setValue(rotation[2])  # Display rotation[2] as Y
        self.rot_z.setValue(rotation[1])  # Display rotation[1] as Z

        # Unblock signals
        self.pos_x.blockSignals(False)
        self.pos_y.blockSignals(False)
        self.pos_z.blockSignals(False)
        self.scale_x.blockSignals(False)
        self.scale_y.blockSignals(False)
        self.scale_z.blockSignals(False)
        self.rot_x.blockSignals(False)
        self.rot_y.blockSignals(False)
        self.rot_z.blockSignals(False)

    def on_position_changed(self):
        """Handle position value changes"""
        # Swap Y/Z back to internal coordinates
        self.position_changed.emit(
            self.pos_x.value(),
            self.pos_z.value(),  # User's Z → internal position[1]
            self.pos_y.value()   # User's Y → internal position[2]
        )

    def on_scale_changed(self, axis, value):
        """Handle scale value changes with linked scaling"""
        if self.updating_scale:
            return

        if self.scale_linked:
            self.updating_scale = True
            self.scale_x.setValue(value)
            self.scale_y.setValue(value)
            self.scale_z.setValue(value)
            self.updating_scale = False

        # Swap Y/Z back to internal coordinates
        self.scale_changed.emit(
            self.scale_x.value(),
            self.scale_z.value(),  # User's Z → internal scale[1]
            self.scale_y.value()   # User's Y → internal scale[2]
        )

    def on_link_toggled(self, checked):
        """Handle link checkbox toggle"""
        self.scale_linked = checked

        # If linking, set all to the average
        if checked:
            avg = (self.scale_x.value() + self.scale_y.value() + self.scale_z.value()) / 3
            self.updating_scale = True
            self.scale_x.setValue(avg)
            self.scale_y.setValue(avg)
            self.scale_z.setValue(avg)
            self.updating_scale = False
            self.scale_changed.emit(avg, avg, avg)

    def set_uniform_scale(self, value):
        """Set uniform scale to a preset value"""
        self.updating_scale = True
        self.scale_x.setValue(value)
        self.scale_y.setValue(value)
        self.scale_z.setValue(value)
        self.updating_scale = False
        self.scale_changed.emit(value, value, value)

    def on_rotation_changed(self):
        """Handle rotation value changes"""
        # Swap Y/Z back to internal coordinates
        self.rotation_changed.emit(
            self.rot_x.value(),
            self.rot_z.value(),  # User's Z → internal rotation[1]
            self.rot_y.value()   # User's Y → internal rotation[2]
        )

    def add_rotation(self, axis, degrees):
        """Add rotation to a specific axis"""
        if axis == 'x':
            self.rot_x.setValue(self.rot_x.value() + degrees)
        elif axis == 'y':
            self.rot_y.setValue(self.rot_y.value() + degrees)
        elif axis == 'z':
            self.rot_z.setValue(self.rot_z.value() + degrees)

    def reset_rotation(self):
        """Reset all rotations to zero"""
        self.rot_x.setValue(0)
        self.rot_y.setValue(0)
        self.rot_z.setValue(0)

    def on_align_face_toggled(self, checked):
        """Handle align face button toggle"""
        if checked:
            self.align_face_btn.setText("Click a face on the model...")
            self.align_face_requested.emit()
        else:
            self.align_face_btn.setText("Select Face to Align")

    def cancel_face_alignment(self):
        """Cancel face alignment mode"""
        self.align_face_btn.setChecked(False)

    def center_on_build_plate(self):
        """Center model on build plate (X=0, Z=0)"""
        self.pos_x.setValue(0)
        self.pos_z.setValue(0)

    def drop_to_build_plate(self):
        """Drop model to build plate (Y=0)"""
        self.pos_y.setValue(0)

    def set_tab(self, mode):
        """Set the active tab based on transform mode"""
        if mode == 'move':
            self.tab_widget.setCurrentIndex(0)
        elif mode == 'scale':
            self.tab_widget.setCurrentIndex(1)
        elif mode == 'rotate':
            self.tab_widget.setCurrentIndex(2)
