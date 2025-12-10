"""
Hatching parameters dialog for configuring hatching generation.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QDoubleSpinBox, QSpinBox, QCheckBox, QComboBox, QPushButton,
    QWidget, QFormLayout, QMessageBox
)
from PyQt6.QtCore import pyqtSignal, Qt


class HatchingDialog(QDialog):
    """Dialog for configuring hatching parameters."""

    # Signals
    parameters_changed = pyqtSignal()  # Emitted when parameters change
    generate_requested = pyqtSignal()  # Emitted when user requests generation
    export_requested = pyqtSignal()    # Emitted when user requests export

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Hatching Parameters")
        self.setMinimumWidth(400)

        # Initialize hatching parameters with defaults
        from hatching import HatchingParameters, HatchingStrategy

        self.hatch_params = HatchingParameters()
        self.hatch_strategy = HatchingStrategy.LINES

        # Build UI
        self.init_ui()

        # Set initial values
        self.update_ui_from_parameters()

    def init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)

        # Strategy selection
        strategy_group = QGroupBox("Hatching Strategy")
        strategy_layout = QFormLayout()

        self.strategy_combo = QComboBox()
        from hatching import HatchingStrategy, registry

        # Add available strategies
        for strategy in HatchingStrategy:
            if registry.is_registered(strategy):
                self.strategy_combo.addItem(strategy.value, strategy)

        self.strategy_combo.currentIndexChanged.connect(self.on_strategy_changed)
        strategy_layout.addRow("Strategy:", self.strategy_combo)

        strategy_group.setLayout(strategy_layout)
        layout.addWidget(strategy_group)

        # Basic parameters
        basic_group = QGroupBox("Basic Parameters")
        basic_layout = QFormLayout()

        self.spacing_spin = QDoubleSpinBox()
        self.spacing_spin.setRange(0.01, 10.0)
        self.spacing_spin.setValue(0.1)
        self.spacing_spin.setSingleStep(0.05)
        self.spacing_spin.setSuffix(" mm")
        self.spacing_spin.valueChanged.connect(self.on_parameter_changed)
        basic_layout.addRow("Hatch Spacing:", self.spacing_spin)

        self.angle_spin = QDoubleSpinBox()
        self.angle_spin.setRange(0, 180)
        self.angle_spin.setValue(0)
        self.angle_spin.setSingleStep(5)
        self.angle_spin.setSuffix("°")
        self.angle_spin.valueChanged.connect(self.on_parameter_changed)
        basic_layout.addRow("Hatch Angle:", self.angle_spin)

        self.rotation_spin = QDoubleSpinBox()
        self.rotation_spin.setRange(0, 180)
        self.rotation_spin.setValue(67)
        self.rotation_spin.setSingleStep(1)
        self.rotation_spin.setSuffix("°")
        self.rotation_spin.valueChanged.connect(self.on_parameter_changed)
        basic_layout.addRow("Layer Rotation:", self.rotation_spin)

        self.border_offset_spin = QDoubleSpinBox()
        self.border_offset_spin.setRange(0, 5.0)
        self.border_offset_spin.setValue(0)
        self.border_offset_spin.setSingleStep(0.05)
        self.border_offset_spin.setSuffix(" mm")
        self.border_offset_spin.valueChanged.connect(self.on_parameter_changed)
        basic_layout.addRow("Border Offset:", self.border_offset_spin)

        basic_group.setLayout(basic_layout)
        layout.addWidget(basic_group)

        # Contour parameters
        contour_group = QGroupBox("Contour Parameters")
        contour_layout = QFormLayout()

        self.enable_contours_check = QCheckBox()
        self.enable_contours_check.setChecked(True)
        self.enable_contours_check.stateChanged.connect(self.on_parameter_changed)
        contour_layout.addRow("Enable Contours:", self.enable_contours_check)

        self.contour_count_spin = QSpinBox()
        self.contour_count_spin.setRange(0, 10)
        self.contour_count_spin.setValue(1)
        self.contour_count_spin.valueChanged.connect(self.on_parameter_changed)
        contour_layout.addRow("Contour Count:", self.contour_count_spin)

        contour_group.setLayout(contour_layout)
        layout.addWidget(contour_group)

        # Process parameters
        process_group = QGroupBox("Process Parameters")
        process_layout = QFormLayout()

        self.scan_speed_spin = QDoubleSpinBox()
        self.scan_speed_spin.setRange(10, 10000)
        self.scan_speed_spin.setValue(1000)
        self.scan_speed_spin.setSingleStep(100)
        self.scan_speed_spin.setSuffix(" mm/s")
        self.scan_speed_spin.valueChanged.connect(self.on_parameter_changed)
        process_layout.addRow("Scan Speed:", self.scan_speed_spin)

        self.power_spin = QDoubleSpinBox()
        self.power_spin.setRange(0, 1.0)
        self.power_spin.setValue(1.0)
        self.power_spin.setSingleStep(0.05)
        self.power_spin.valueChanged.connect(self.on_parameter_changed)
        process_layout.addRow("Power Level:", self.power_spin)

        process_group.setLayout(process_layout)
        layout.addWidget(process_group)

        # Advanced options
        advanced_group = QGroupBox("Advanced Options")
        advanced_layout = QFormLayout()

        self.bidirectional_check = QCheckBox()
        self.bidirectional_check.setChecked(True)
        self.bidirectional_check.stateChanged.connect(self.on_parameter_changed)
        advanced_layout.addRow("Bidirectional Scan:", self.bidirectional_check)

        self.optimize_path_check = QCheckBox()
        self.optimize_path_check.setChecked(True)
        self.optimize_path_check.stateChanged.connect(self.on_parameter_changed)
        advanced_layout.addRow("Optimize Path:", self.optimize_path_check)

        advanced_group.setLayout(advanced_layout)
        layout.addWidget(advanced_group)

        # Buttons
        button_layout = QHBoxLayout()

        self.generate_btn = QPushButton("Generate Hatching")
        self.generate_btn.clicked.connect(self.on_generate_clicked)
        button_layout.addWidget(self.generate_btn)

        self.export_btn = QPushButton("Export to OBP")
        self.export_btn.clicked.connect(self.on_export_clicked)
        button_layout.addWidget(self.export_btn)

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close)
        button_layout.addWidget(self.close_btn)

        layout.addLayout(button_layout)

        # Statistics display
        self.stats_label = QLabel()
        self.stats_label.setWordWrap(True)
        self.stats_label.setStyleSheet("QLabel { background-color: #f0f0f0; padding: 10px; border-radius: 5px; }")
        layout.addWidget(self.stats_label)

    def update_ui_from_parameters(self):
        """Update UI controls from current parameters."""
        self.spacing_spin.setValue(self.hatch_params.hatch_spacing)
        self.angle_spin.setValue(self.hatch_params.hatch_angle)
        self.rotation_spin.setValue(self.hatch_params.layer_rotation)
        self.border_offset_spin.setValue(self.hatch_params.border_offset)
        self.enable_contours_check.setChecked(self.hatch_params.enable_contours)
        self.contour_count_spin.setValue(self.hatch_params.contour_count)
        self.scan_speed_spin.setValue(self.hatch_params.scan_speed)
        self.power_spin.setValue(self.hatch_params.power_level)
        self.bidirectional_check.setChecked(self.hatch_params.bidirectional)
        self.optimize_path_check.setChecked(self.hatch_params.optimize_path)

        # Set strategy combo
        for i in range(self.strategy_combo.count()):
            if self.strategy_combo.itemData(i) == self.hatch_strategy:
                self.strategy_combo.setCurrentIndex(i)
                break

    def update_parameters_from_ui(self):
        """Update parameters from UI controls."""
        from hatching import HatchingParameters

        self.hatch_params = HatchingParameters(
            hatch_spacing=self.spacing_spin.value(),
            hatch_angle=self.angle_spin.value(),
            layer_rotation=self.rotation_spin.value(),
            border_offset=self.border_offset_spin.value(),
            enable_contours=self.enable_contours_check.isChecked(),
            contour_count=self.contour_count_spin.value(),
            scan_speed=self.scan_speed_spin.value(),
            power_level=self.power_spin.value(),
            bidirectional=self.bidirectional_check.isChecked(),
            optimize_path=self.optimize_path_check.isChecked()
        )

        self.hatch_strategy = self.strategy_combo.currentData()

    def on_parameter_changed(self):
        """Handle parameter change."""
        self.update_parameters_from_ui()
        self.parameters_changed.emit()

    def on_strategy_changed(self):
        """Handle strategy change."""
        self.update_parameters_from_ui()
        self.parameters_changed.emit()

    def on_generate_clicked(self):
        """Handle generate button click."""
        self.update_parameters_from_ui()
        self.generate_requested.emit()

    def on_export_clicked(self):
        """Handle export button click."""
        self.export_requested.emit()

    def get_parameters(self):
        """Get current hatching parameters."""
        return self.hatch_params, self.hatch_strategy

    def update_statistics(self, stats):
        """
        Update statistics display.

        Args:
            stats: Dictionary with statistics from get_hatching_statistics()
        """
        if not stats:
            self.stats_label.setText("No hatching generated yet.")
            return

        # Format statistics
        text = f"""<b>Hatching Statistics:</b><br>
Total Layers: {stats['total_layers']}<br>
Total Lines: {stats['total_lines']} ({stats['contour_lines']} contours, {stats['infill_lines']} infill)<br>
Scan Length: {stats['total_scan_length_mm']:.1f} mm (contour: {stats['contour_length_mm']:.1f} mm, infill: {stats['infill_length_mm']:.1f} mm)<br>
Avg Lines/Layer: {stats['avg_lines_per_layer']:.1f}<br>
Estimated Time: {stats['estimated_time_seconds']:.1f} seconds ({stats['estimated_time_seconds']/60:.2f} minutes)
        """

        self.stats_label.setText(text)
