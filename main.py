import sys
from typing import Optional
from PyQt6 import QtWidgets, uic
from PyQt6.QtWidgets import QFileDialog, QMessageBox, QProgressDialog
from PyQt6.QtOpenGLWidgets import QOpenGLWidget as QtOpenGLWidget
from PyQt6.QtCore import Qt

# Import our custom OpenGL widget
from opengl_widget import OpenGLWidget
from transform_dialog import TransformDialog
from workers import CADLoadWorker, SlicingWorker, HatchingWorker
from constants import DEFAULT_LAYER_THICKNESS_STR

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        # Load the UI file
        uic.loadUi('ui/obpcut_main.ui', self)

        # Replace the default QOpenGLWidget with our custom one
        self.setup_opengl_widget()

        # Create transform dialog (hidden by default)
        self.transform_dialog: Optional[TransformDialog] = None

        # Create hatching dialog (hidden by default)
        self.hatching_dialog = None

        # Worker threads for async operations
        self.cad_load_worker: Optional[CADLoadWorker] = None
        self.slicing_worker: Optional[SlicingWorker] = None
        self.hatching_worker: Optional[HatchingWorker] = None
        self.progress_dialog: Optional[QProgressDialog] = None

        # Add hatching menu
        self.add_hatching_menu()

        # Connect signals to slots
        self.connect_signals()

        # Initialize hatching with default parameters
        self.initialize_hatching()

        # Maximize the window
        self.showMaximized()
    
    def add_hatching_menu(self):
        """Add hatching menu to the menu bar."""
        from PyQt6.QtGui import QAction

        # Create Tools menu if it doesn't exist
        menubar = self.menuBar()
        tools_menu = menubar.addMenu("&Tools")

        # Add hatching parameters action
        hatching_action = QAction("&Hatching Parameters...", self)
        hatching_action.setShortcut("Ctrl+H")
        hatching_action.setStatusTip("Configure hatching parameters")
        hatching_action.triggered.connect(self.show_hatching_dialog)
        tools_menu.addAction(hatching_action)

        # Add separator
        tools_menu.addSeparator()

        # Add export action
        export_action = QAction("&Export to OBP...", self)
        export_action.setShortcut("Ctrl+E")
        export_action.setStatusTip("Export hatching to OBP file")
        export_action.triggered.connect(self.on_export_hatching)
        tools_menu.addAction(export_action)

    def setup_opengl_widget(self):
        """Replace the default OpenGL widget with our custom implementation"""
        # Find the existing openGLWidget in the UI
        old_widget = self.findChild(QtOpenGLWidget, 'openGLWidget')

        if old_widget:
            # Create new instance of our OpenGL widget
            new_opengl_widget = OpenGLWidget()

            # Get the parent layout to replace the widget properly
            parent_layout = old_widget.parent().layout()

            if parent_layout:
                # Find the index of the old widget in the layout
                index = parent_layout.indexOf(old_widget)

                # Remove the old widget from layout and delete it
                parent_layout.replaceWidget(old_widget, new_opengl_widget)
                old_widget.deleteLater()

                # Set the new widget as our openGLWidget attribute
                self.openGLWidget = new_opengl_widget

                # Make sure the new widget is properly initialized
                new_opengl_widget.show()
    
    def connect_signals(self):
        """Connect UI signals to their respective slots"""
        # Connect the open CAD file button to the open_file function
        self.pb_openCADFile.clicked.connect(self.open_file)

        # Connect the File > Open menu action to the open_file function
        self.action_openCADFile.triggered.connect(self.open_file)

        # Connect remove button
        self.pb_removeCADFile.clicked.connect(self.remove_selected_model)

        # Connect view mode buttons
        self.pb_layoutmode.toggled.connect(self.on_layout_mode_toggled)
        self.pb_slicemode.toggled.connect(self.on_slice_mode_toggled)

        # Connect layer thickness input
        self.le_layerthickness.setText(DEFAULT_LAYER_THICKNESS_STR)
        self.le_layerthickness.editingFinished.connect(self.on_layer_thickness_changed)

        # Connect transformation mode buttons
        self.pbt_movemode.toggled.connect(self.on_move_mode_toggled)
        self.pbt_rotatemode.toggled.connect(self.on_rotate_mode_toggled)
        self.pbt_scalemode.toggled.connect(self.on_scale_mode_toggled)

        # Connect tree widget selection to OpenGL widget
        self.modelTreeWidget.itemSelectionChanged.connect(self.on_model_selection_changed)

        # Connect OpenGL widget transformation changed signal
        self.openGLWidget.transformation_changed.connect(self.update_transform_dialog)

        # Connect OpenGL widget async operation signals
        self.openGLWidget.slicing_requested.connect(self.on_slicing_requested)
        self.openGLWidget.hatching_requested.connect(self.on_hatching_requested)
    
    def open_file(self):
        """Open a file dialog to select .step or .iges files and load them asynchronously"""
        from constants import SUPPORTED_CAD_FORMATS

        # Don't allow loading while another file is loading
        if self.cad_load_worker is not None and self.cad_load_worker.isRunning():
            QMessageBox.warning(self, "Loading in Progress",
                              "Please wait for the current file to finish loading.")
            return

        # Create file dialog
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open CAD File",
            "",
            SUPPORTED_CAD_FORMATS
        )

        if file_path:
            self.load_cad_file_async(file_path)

    def load_cad_file_async(self, file_path: str):
        """Load CAD file asynchronously using worker thread"""
        # Create progress dialog
        self.progress_dialog = QProgressDialog("Loading CAD file...", "Cancel", 0, 0, self)
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setAutoClose(True)
        self.progress_dialog.setAutoReset(True)
        self.progress_dialog.canceled.connect(self.cancel_loading)

        # Create and start worker thread
        self.cad_load_worker = CADLoadWorker(file_path)
        self.cad_load_worker.progress.connect(self.on_load_progress)
        self.cad_load_worker.finished.connect(lambda model: self.on_load_finished(model, file_path))
        self.cad_load_worker.error.connect(self.on_load_error)
        self.cad_load_worker.start()

        self.progress_dialog.show()

    def cancel_loading(self):
        """Cancel the current loading operation"""
        if self.cad_load_worker and self.cad_load_worker.isRunning():
            self.cad_load_worker.cancel()
            self.cad_load_worker.wait()

    def on_load_progress(self, stage: str, message: str):
        """Update progress dialog with loading progress"""
        if self.progress_dialog:
            self.progress_dialog.setLabelText(message)

    def on_load_finished(self, cad_model, file_path: str):
        """Handle CAD model loading completion"""
        if self.progress_dialog:
            self.progress_dialog.close()

        if cad_model is not None:
            # Add model to OpenGL widget
            model_index = self.openGLWidget.add_loaded_model(cad_model, file_path)

            if model_index is not None:
                # Get model data
                model_data = self.openGLWidget.models[model_index]

                # Add to tree widget
                from PyQt6.QtWidgets import QTreeWidgetItem
                item = QTreeWidgetItem(self.modelTreeWidget)
                item.setText(0, model_data['name'])
                item.setData(0, 0x0100, model_index)  # Qt.UserRole = 0x0100

                # Select the newly added item
                self.modelTreeWidget.setCurrentItem(item)

                # Update button states
                self.update_button_states()

    def on_load_error(self, error_message: str):
        """Handle CAD model loading error"""
        if self.progress_dialog:
            self.progress_dialog.close()

        QMessageBox.critical(self, "Loading Error",
                           f"Failed to load CAD file:\n{error_message}")

    def on_slicing_requested(self, models, layer_thickness):
        """Handle slicing request from OpenGL widget"""
        if not models:
            return

        # Create and show progress dialog
        self.progress_dialog = QProgressDialog("Slicing models...", "Cancel", 0, 100, self)
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setAutoClose(True)
        self.progress_dialog.setAutoReset(True)
        self.progress_dialog.canceled.connect(self.cancel_slicing)

        # Create and start worker thread
        self.slicing_worker = SlicingWorker(models, layer_thickness)
        self.slicing_worker.progress.connect(self.on_slicing_progress)
        self.slicing_worker.finished.connect(self.on_slicing_finished)
        self.slicing_worker.error.connect(self.on_slicing_error)
        self.slicing_worker.start()

    def on_slicing_progress(self, current: int, total: int, message: str):
        """Update slicing progress"""
        if self.progress_dialog:
            self.progress_dialog.setMaximum(total)
            self.progress_dialog.setValue(current)
            self.progress_dialog.setLabelText(message)

    def on_slicing_finished(self, sliced_layers):
        """Handle slicing completion"""
        if self.progress_dialog:
            self.progress_dialog.close()

        # Update OpenGL widget with sliced layers
        self.openGLWidget.set_sliced_layers(sliced_layers)

    def on_slicing_error(self, error_message: str):
        """Handle slicing error"""
        if self.progress_dialog:
            self.progress_dialog.close()

        QMessageBox.critical(self, "Slicing Error",
                           f"Failed to slice models:\n{error_message}")

    def cancel_slicing(self):
        """Cancel ongoing slicing operation"""
        if self.slicing_worker:
            self.slicing_worker.cancel()

    def on_hatching_requested(self, sliced_layers, hatching_params, hatching_strategy):
        """Handle hatching generation request from OpenGL widget"""
        if not sliced_layers or not hatching_params:
            return

        # Create and show progress dialog
        self.progress_dialog = QProgressDialog("Generating hatching...", "Cancel", 0, 100, self)
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setAutoClose(True)
        self.progress_dialog.setAutoReset(True)
        self.progress_dialog.canceled.connect(self.cancel_hatching)

        # Create and start worker thread
        self.hatching_worker = HatchingWorker(sliced_layers, hatching_params, hatching_strategy)
        self.hatching_worker.progress.connect(self.on_hatching_progress)
        self.hatching_worker.finished.connect(self.on_hatching_finished)
        self.hatching_worker.error.connect(self.on_hatching_error)
        self.hatching_worker.start()

    def on_hatching_progress(self, current: int, total: int, message: str):
        """Update hatching progress"""
        if self.progress_dialog:
            self.progress_dialog.setMaximum(total)
            self.progress_dialog.setValue(current)
            self.progress_dialog.setLabelText(message)

    def on_hatching_finished(self, hatching_data):
        """Handle hatching generation completion"""
        if self.progress_dialog:
            self.progress_dialog.close()

        # Update OpenGL widget with hatching data
        self.openGLWidget.set_hatching_data(hatching_data)

        # Update statistics in dialog if visible
        stats = self.openGLWidget.get_hatching_statistics()
        if stats and self.hatching_dialog:
            self.hatching_dialog.update_statistics(stats)
            # Show success message when explicitly requested from dialog
            QMessageBox.information(self, "Hatching Generated",
                                  f"Successfully generated hatching for {stats['total_layers']} layers.")

    def on_hatching_error(self, error_message: str):
        """Handle hatching generation error"""
        if self.progress_dialog:
            self.progress_dialog.close()

        QMessageBox.critical(self, "Hatching Error",
                           f"Failed to generate hatching:\n{error_message}")

    def cancel_hatching(self):
        """Cancel ongoing hatching operation"""
        if self.hatching_worker:
            self.hatching_worker.cancel()

    def remove_selected_model(self):
        """Remove the currently selected model"""
        selected_items = self.modelTreeWidget.selectedItems()

        if selected_items:
            item = selected_items[0]
            model_index = item.data(0, 0x0100)  # Qt.UserRole

            # Remove from OpenGL widget
            self.openGLWidget.remove_model(model_index)

            # Remove from tree widget
            index = self.modelTreeWidget.indexOfTopLevelItem(item)
            self.modelTreeWidget.takeTopLevelItem(index)

            # Update all remaining items' indices
            for i in range(self.modelTreeWidget.topLevelItemCount()):
                item = self.modelTreeWidget.topLevelItem(i)
                item.setData(0, 0x0100, i)

            # Update button states
            self.update_button_states()

    def update_button_states(self):
        """Update enabled state of buttons based on current state"""
        has_models = self.openGLWidget.models and len(self.openGLWidget.models) > 0
        has_selection = self.openGLWidget.selected_model_index is not None

        # Enable/disable buttons
        self.pb_removeCADFile.setEnabled(has_selection)
        self.pbt_movemode.setEnabled(has_selection)
        self.pbt_rotatemode.setEnabled(has_selection)
        self.pbt_scalemode.setEnabled(has_selection)

    def on_move_mode_toggled(self, checked):
        """Handle move mode toggle"""
        self._handle_transform_mode_toggle('move', checked)

    def on_rotate_mode_toggled(self, checked):
        """Handle rotate mode toggle"""
        self._handle_transform_mode_toggle('rotate', checked)

    def on_scale_mode_toggled(self, checked):
        """Handle scale mode toggle"""
        self._handle_transform_mode_toggle('scale', checked)

    def _handle_transform_mode_toggle(self, mode: str, checked: bool):
        """
        Generic handler for transform mode toggles.

        Args:
            mode: Transform mode ('move', 'rotate', or 'scale')
            checked: Whether the button is checked
        """
        # Map of modes to their buttons
        mode_buttons = {
            'move': self.pbt_movemode,
            'rotate': self.pbt_rotatemode,
            'scale': self.pbt_scalemode
        }

        if checked:
            # Uncheck other modes
            for other_mode, button in mode_buttons.items():
                if other_mode != mode:
                    button.setChecked(False)

            # Set OpenGL widget to the selected mode
            self.openGLWidget.set_transform_mode(mode)

            # Show transform dialog
            self.show_transform_dialog(mode)
        else:
            # Check if any other mode is still checked
            any_mode_checked = any(
                button.isChecked()
                for other_mode, button in mode_buttons.items()
                if other_mode != mode
            )

            if not any_mode_checked:
                self.openGLWidget.set_transform_mode(None)
                self.hide_transform_dialog()

    def on_layout_mode_toggled(self, checked):
        """Handle layout mode toggle"""
        if checked:
            # Uncheck slice mode
            self.pb_slicemode.blockSignals(True)
            self.pb_slicemode.setChecked(False)
            self.pb_slicemode.blockSignals(False)

            # Set OpenGL widget to layout mode
            self.openGLWidget.set_view_mode('layout')
        else:
            # Don't allow unchecking if slice mode isn't checked
            if not self.pb_slicemode.isChecked():
                self.pb_layoutmode.blockSignals(True)
                self.pb_layoutmode.setChecked(True)
                self.pb_layoutmode.blockSignals(False)

    def on_slice_mode_toggled(self, checked):
        """Handle slice mode toggle"""
        if checked:
            # Uncheck layout mode
            self.pb_layoutmode.blockSignals(True)
            self.pb_layoutmode.setChecked(False)
            self.pb_layoutmode.blockSignals(False)

            # Get layer thickness
            try:
                layer_thickness = float(self.le_layerthickness.text())
            except ValueError:
                layer_thickness = 0.2  # Default
            # Set OpenGL widget to slice mode
            self.openGLWidget.set_view_mode('slice', layer_thickness)
        else:
            # Don't allow unchecking if layout mode isn't checked
            if not self.pb_layoutmode.isChecked():
                self.pb_slicemode.blockSignals(True)
                self.pb_slicemode.setChecked(True)
                self.pb_slicemode.blockSignals(False)

    def on_layer_thickness_changed(self):
        """Handle layer thickness change"""
        # If in slice mode, update the slicing
        if self.pb_slicemode.isChecked():
            try:
                layer_thickness = float(self.le_layerthickness.text())
                self.openGLWidget.update_slice_thickness(layer_thickness)
            except ValueError:
                pass  # Invalid input, ignore

    def show_transform_dialog(self, mode):
        """Show the transform dialog for the given mode"""
        if self.transform_dialog is None:
            self.transform_dialog = TransformDialog(self, mode)
            self.transform_dialog.set_opengl_widget(self.openGLWidget)

            # Connect signals
            self.transform_dialog.position_changed.connect(self.on_dialog_position_changed)
            self.transform_dialog.scale_changed.connect(self.on_dialog_scale_changed)
            self.transform_dialog.rotation_changed.connect(self.on_dialog_rotation_changed)
            self.transform_dialog.align_face_requested.connect(self.on_align_face_requested)

            # Connect tab change signal to update toolbar buttons
            self.transform_dialog.tab_widget.currentChanged.connect(self.on_transform_tab_changed)

        # Update dialog with current model values
        if self.openGLWidget.selected_model_index is not None:
            model_data = self.openGLWidget.models[self.openGLWidget.selected_model_index]
            self.transform_dialog.update_from_model(model_data)

        # Set the correct tab
        self.transform_dialog.set_tab(mode)

        # Show the dialog
        self.transform_dialog.show()
        self.transform_dialog.raise_()

        # Position dialog after it's fully shown using QTimer
        # This ensures the window manager has finished positioning it
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, self.position_transform_dialog)

    def position_transform_dialog(self):
        """Position the transform dialog to the right side of the screen"""
        if self.transform_dialog is None or not self.transform_dialog.isVisible():
            return

        # Get the screen geometry
        screen = self.screen()
        screen_geo = screen.availableGeometry()

        # Get dialog size (should be calculated by now)
        dialog_width = self.transform_dialog.frameGeometry().width()
        dialog_height = self.transform_dialog.frameGeometry().height()

        # Snap to right edge of screen with small margin
        margin = 10
        x_pos = screen_geo.right() - dialog_width - margin
        y_pos = screen_geo.top() + 100  # 100 pixels from top

        self.transform_dialog.move(x_pos, y_pos)

    def hide_transform_dialog(self):
        """Hide the transform dialog"""
        if self.transform_dialog is not None:
            self.transform_dialog.hide()

    def on_dialog_position_changed(self, x, y, z):
        """Handle position change from dialog"""
        if self.openGLWidget.selected_model_index is not None:
            model_data = self.openGLWidget.models[self.openGLWidget.selected_model_index]
            model_data['position'] = [x, y, z]
            self.openGLWidget.update()

    def on_dialog_scale_changed(self, x, y, z):
        """Handle scale change from dialog"""
        if self.openGLWidget.selected_model_index is not None:
            model_data = self.openGLWidget.models[self.openGLWidget.selected_model_index]
            model_data['scale'] = [x, y, z]
            self.openGLWidget.update()

    def on_dialog_rotation_changed(self, x, y, z):
        """Handle rotation change from dialog"""
        if self.openGLWidget.selected_model_index is not None:
            model_data = self.openGLWidget.models[self.openGLWidget.selected_model_index]
            model_data['rotation'] = [x, y, z]
            self.openGLWidget.update()

    def on_align_face_requested(self):
        """Handle request to align a face to build plate"""
        # Enable face picking mode in OpenGL widget with callback
        self.openGLWidget.set_face_picking_mode(True, self.on_face_aligned)

    def on_face_aligned(self):
        """Called when face alignment is complete"""
        # Update transform dialog with new rotation values
        self.update_transform_dialog()
        # Reset the button in the dialog
        if self.transform_dialog:
            self.transform_dialog.cancel_face_alignment()

    def update_transform_dialog(self):
        """Update transform dialog with current model values"""
        if self.transform_dialog is not None and self.transform_dialog.isVisible():
            if self.openGLWidget.selected_model_index is not None:
                model_data = self.openGLWidget.models[self.openGLWidget.selected_model_index]
                self.transform_dialog.update_from_model(model_data)

    def on_transform_tab_changed(self, index):
        """Handle transform dialog tab changes to update toolbar button states"""
        # Map tab index to mode
        modes = ['move', 'scale', 'rotate']
        if 0 <= index < len(modes):
            mode = modes[index]

            # Block signals to prevent recursive toggling
            self.pbt_movemode.blockSignals(True)
            self.pbt_scalemode.blockSignals(True)
            self.pbt_rotatemode.blockSignals(True)

            # Update toolbar button states
            self.pbt_movemode.setChecked(mode == 'move')
            self.pbt_scalemode.setChecked(mode == 'scale')
            self.pbt_rotatemode.setChecked(mode == 'rotate')

            # Unblock signals
            self.pbt_movemode.blockSignals(False)
            self.pbt_scalemode.blockSignals(False)
            self.pbt_rotatemode.blockSignals(False)

            # Update OpenGL widget transform mode
            self.openGLWidget.set_transform_mode(mode)

    def on_model_selection_changed(self):
        """Handle model selection changes in the tree widget"""
        selected_items = self.modelTreeWidget.selectedItems()

        if selected_items:
            # Get the model index from the selected item
            item = selected_items[0]
            model_index = item.data(0, 0x0100)  # Qt.UserRole

            # Update the OpenGL widget selection
            self.openGLWidget.set_selected_model(model_index)
        else:
            # No selection
            self.openGLWidget.set_selected_model(None)

        # Update button states
        self.update_button_states()

    def initialize_hatching(self):
        """Initialize hatching with default parameters."""
        from hatching import HatchingParameters, HatchingStrategy

        # Set default parameters
        default_params = HatchingParameters()
        self.openGLWidget.set_hatching_parameters(default_params, HatchingStrategy.LINES)

    def show_hatching_dialog(self):
        """Show the hatching parameters dialog."""
        if self.hatching_dialog is None:
            from hatching_dialog import HatchingDialog

            self.hatching_dialog = HatchingDialog(self)

            # Connect signals
            self.hatching_dialog.parameters_changed.connect(self.on_hatching_parameters_changed)
            self.hatching_dialog.generate_requested.connect(self.on_generate_hatching)
            self.hatching_dialog.export_requested.connect(self.on_export_hatching)

        # Update dialog with current parameters if hatching is configured
        if self.openGLWidget.hatching_params:
            self.hatching_dialog.hatch_params = self.openGLWidget.hatching_params
            self.hatching_dialog.hatch_strategy = self.openGLWidget.hatching_strategy
            self.hatching_dialog.update_ui_from_parameters()

        # Show dialog
        self.hatching_dialog.show()
        self.hatching_dialog.raise_()
        self.hatching_dialog.activateWindow()

    def on_hatching_parameters_changed(self):
        """Handle hatching parameter changes."""
        if self.hatching_dialog:
            params, strategy = self.hatching_dialog.get_parameters()
            self.openGLWidget.set_hatching_parameters(params, strategy)

    def on_generate_hatching(self):
        """Generate hatching for current model."""
        if not self.openGLWidget.models:
            QMessageBox.warning(self, "No Model", "Please load a model first.")
            return

        if self.openGLWidget.view_mode != 'slice':
            QMessageBox.warning(self, "Not in Slice Mode",
                              "Please switch to slice mode before generating hatching.")
            return

        # Update parameters from dialog
        if self.hatching_dialog:
            params, strategy = self.hatching_dialog.get_parameters()
            self.openGLWidget.set_hatching_parameters(params, strategy)

        # Enable hatching and request async generation
        self.openGLWidget.enable_hatching(True)
        self.openGLWidget.request_hatching_generation()

        # Note: Success message and statistics update will happen in on_hatching_finished

    def on_export_hatching(self):
        """Export hatching to OBP file."""
        if not self.openGLWidget.hatching_data:
            QMessageBox.warning(self, "No Hatching",
                              "Please generate hatching before exporting.")
            return

        # Get save file path
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export to OBP",
            "",
            "OBP Files (*.obp);;JSON Files (*.json);;All Files (*)"
        )

        if not file_path:
            return

        # Export
        success = self.openGLWidget.export_to_obp(file_path)

        if success:
            QMessageBox.information(self, "Export Successful",
                                  f"Successfully exported to {file_path}")
        else:
            QMessageBox.critical(self, "Export Failed",
                               "Failed to export hatching data.")

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())