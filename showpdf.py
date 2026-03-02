import sys
import os
import json
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl

class PDFViewer(QMainWindow):
    def __init__(self):
        super().__init__()

        # Create a QWebEngineView widget
        self.browser = QWebEngineView()
        
        with open('public/documents_url.json', 'r') as file:
            urls = json.load(file)  # Parse the JSON file into a Python dictionary
        email = urls["email"]
  
        self.browser.setUrl(email)
        

        # Load the PDF file
        #self.browser.setUrl(file_url)

        # Set up layout
        central_widget = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(self.browser)
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

        self.setWindowTitle("PDF Viewer")
        self.resize(800, 600)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    viewer = PDFViewer()
    viewer.show()
    sys.exit(app.exec())
