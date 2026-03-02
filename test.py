from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget, QLabel, QPushButton, QComboBox
)
from PySide6.QtMultimedia import QCamera, QMediaDevices, QMediaCaptureSession
from PySide6.QtMultimediaWidgets import QVideoWidget


class CameraApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Camera Selector")
        self.setGeometry(100, 100, 800, 600)

        # Central widget
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        # Layout
        self.layout = QVBoxLayout(self.central_widget)

        # Camera selection dropdown
        self.camera_selector = QComboBox()
        self.camera_selector.addItems([camera.description() for camera in QMediaDevices.videoInputs()])
        self.layout.addWidget(QLabel("Select Camera:"))
        self.layout.addWidget(self.camera_selector)

        # Video widget
        self.video_widget = QVideoWidget()
        self.layout.addWidget(self.video_widget)

        # Start button
        self.start_button = QPushButton("Start Camera")
        self.start_button.clicked.connect(self.start_camera)
        self.layout.addWidget(self.start_button)

        # Stop button
        self.stop_button = QPushButton("Stop Camera")
        self.stop_button.clicked.connect(self.stop_camera)
        self.stop_button.setEnabled(False)
        self.layout.addWidget(self.stop_button)

        # Camera and capture session
        self.camera = None
        self.capture_session = QMediaCaptureSession()

    def start_camera(self):
        # Stop any existing camera
        if self.camera:
            self.camera.stop()

        # Get selected camera
        selected_camera_index = self.camera_selector.currentIndex()
        video_input = QMediaDevices.videoInputs()[selected_camera_index]

        # Initialize and start camera
        self.camera = QCamera(video_input)
        self.capture_session.setCamera(self.camera)
        self.capture_session.setVideoOutput(self.video_widget)
        self.camera.start()

        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)

    def stop_camera(self):
        if self.camera:
            self.camera.stop()
            self.camera = None

        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)


if __name__ == "__main__":
    app = QApplication([])
    camera_app = CameraApp()
    camera_app.show()
    app.exec()
