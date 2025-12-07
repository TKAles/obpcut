import sys
from PyQt6 import QtWidgets, uic
from PyQt6.QtWidgets import QFileDialog
from PyQt6.QtOpenGLWidgets import QOpenGLWidget as QtOpenGLWidget
from PyQt6.QtCore import Qt

# Import our custom OpenGL widget
from opengl_widget import OpenGLWidget
from transform_dialog import TransformDialog

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        # Load the UI file
        uic.loadUi('ui/obpcut_main.ui', self)

        # Replace the default QOpenGLWidget with our custom one
        self.setup_opengl_widget()

        # Create transform dialog (hidden by default)
        self.transform_dialog = None

        # Connect signals to slots
        self.connect_signals()

        # Maximize the window
        self.showMaximized()
    
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

        # Connect transformation mode buttons
        self.pbt_movemode.toggled.connect(self.on_move_mode_toggled)
        self.pbt_rotatemode.toggled.connect(self.on_rotate_mode_toggled)
        self.pbt_scalemode.toggled.connect(self.on_scale_mode_toggled)

        # Connect tree widget selection to OpenGL widget
        self.modelTreeWidget.itemSelectionChanged.connect(self.on_model_selection_changed)

        # Connect OpenGL widget transformation changed signal
        self.openGLWidget.transformation_changed.connect(self.update_transform_dialog)
    
    def open_file(self):
        """Open a file dialog to select .step or .iges files and load them"""
        # Create file dialog
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open CAD File",
            "",
            "CAD Files (*.step *.iges);;All Files (*)"
        )

        if file_path:
            # Load the CAD model into our OpenGL widget
            print(f"Loading CAD file: {file_path}")

            # Load the model and get its index
            model_index = self.openGLWidget.load_cad_model(file_path)

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
        if checked:
            # Uncheck other modes
            self.pbt_rotatemode.setChecked(False)
            self.pbt_scalemode.setChecked(False)
            # Set OpenGL widget to move mode
            self.openGLWidget.set_transform_mode('move')
            # Show transform dialog
            self.show_transform_dialog('move')
        else:
            if not self.pbt_rotatemode.isChecked() and not self.pbt_scalemode.isChecked():
                self.openGLWidget.set_transform_mode(None)
                self.hide_transform_dialog()

    def on_rotate_mode_toggled(self, checked):
        """Handle rotate mode toggle"""
        if checked:
            # Uncheck other modes
            self.pbt_movemode.setChecked(False)
            self.pbt_scalemode.setChecked(False)
            # Set OpenGL widget to rotate mode
            self.openGLWidget.set_transform_mode('rotate')
            # Show transform dialog
            self.show_transform_dialog('rotate')
        else:
            if not self.pbt_movemode.isChecked() and not self.pbt_scalemode.isChecked():
                self.openGLWidget.set_transform_mode(None)
                self.hide_transform_dialog()

    def on_scale_mode_toggled(self, checked):
        """Handle scale mode toggle"""
        if checked:
            # Uncheck other modes
            self.pbt_movemode.setChecked(False)
            self.pbt_rotatemode.setChecked(False)
            # Set OpenGL widget to scale mode
            self.openGLWidget.set_transform_mode('scale')
            # Show transform dialog
            self.show_transform_dialog('scale')
        else:
            if not self.pbt_movemode.isChecked() and not self.pbt_rotatemode.isChecked():
                self.openGLWidget.set_transform_mode(None)
                self.hide_transform_dialog()

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

        # Update dialog with current model values
        if self.openGLWidget.selected_model_index is not None:
            model_data = self.openGLWidget.models[self.openGLWidget.selected_model_index]
            self.transform_dialog.update_from_model(model_data)

        # Set the correct tab
        self.transform_dialog.set_tab(mode)

        # Position dialog near the transform buttons
        if not self.transform_dialog.isVisible():
            # Position to the right of the main window
            main_geo = self.geometry()
            self.transform_dialog.move(main_geo.right() - 300, main_geo.top() + 100)

        self.transform_dialog.show()
        self.transform_dialog.raise_()

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

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())