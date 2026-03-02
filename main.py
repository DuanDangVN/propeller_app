import sys
import csv
import os
from PySide6.QtCore import Qt, QTimer, QSize
import pyqtgraph as pg
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
    QComboBox,
    QLineEdit,
    QSizePolicy,
    QMessageBox,
    QGridLayout
)
from PySide6.QtMultimedia import QCamera, QMediaDevices, QMediaCaptureSession
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWebEngineWidgets import QWebEngineView
from scipy.stats import linregress
import serial
import serial.tools.list_ports
import numpy as np
from nidaqmx.constants import AcquisitionType
from nidaqmx import Task
from scipy.signal import butter, filtfilt
import nidaqmx.system
import json

class NIDeviceReader:
    def __init__(self, dev_name, rate, samples):
        
        self.rate = rate
        self.samples = samples
        self.task = Task()
        self.task.ai_channels.add_ai_voltage_chan(dev_name+"/ai0") 
        self.task.ai_channels.add_ai_voltage_chan(dev_name+"/ai1")  # Configure channel
        self.task.timing.cfg_samp_clk_timing(
            rate, sample_mode=AcquisitionType.FINITE, samps_per_chan=samples
        )
        #self.task.start()
        # self.task.in_stream.configure_logging(
        #     "TestData.tdms", LoggingMode.LOG_AND_READ, operation=LoggingOperation.CREATE_OR_REPLACE
        # )  # Configure logging

    def read_data(self):
        data = self.task.read(number_of_samples_per_channel=self.samples)#self.task.read(READ_ALL_AVAILABLE)
        #print(f"Available samples: {data}")
        return np.array(data[0]), np.array(data[1])

    def stop(self):
        self.task.stop()

    def close(self):
        self.task.close()
def list_dev():
    system = nidaqmx.system.System.local()
    devices = []
    default_dev = "Dev1"
    for device in system.devices:
        for j in [0,1,2,3]:
            check_device = system.devices[f"Dev{j}"]
            if check_device == device:
                default_dev = f"Dev{j}"
    devices.append(default_dev)
    for k in [0,1,2,3]:
        optional_dev = f"Dev{k}"
        devices.append(optional_dev)
    return devices, default_dev
def butter_lowpass_filter(data, cutoff, fs, order=4):
    """
    Apply a low-pass Butterworth filter.
    
    :param data: Input data (array-like)
    :param cutoff: Cutoff frequency (Hz)
    :param fs: Sampling frequency (Hz)
    :param order: Filter order
    :return: Filtered data
    """
    nyquist = 0.5 * fs  # Nyquist frequency
    normal_cutoff = cutoff / nyquist
    b, a = butter(order, normal_cutoff, btype='low', analog=False)
    filtered_data = filtfilt(b, a, data)
    return filtered_data


class MotorControl:
    def __init__(self, serial_port="COM6", baud_rate=9600):
        self.arduino = serial.Serial(serial_port, baud_rate, timeout=1)
        self.inital_rpm = 0
    
    def set_power(self, value):
        command = f"{value}\n"
        self.arduino.write(command.encode())
        
    def start_motor(self, power):
        try:
            power = int(power)
            if 10 <= power <= 95:
                command = f"{power}\n"
                self.arduino.write(command.encode())
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Devices isn't connected, connect devices then active again: {e}")
             # Reset toggle state
        
    def stop_motor(self):
        self.arduino.write(b"10\n")  # Stop motor
        
    
    def read_rpm(self):
          # Initialize with a default value
        if self.arduino.in_waiting > 0:
            line = self.arduino.readline().decode().strip()
            if line.startswith("RPM = "):  # Ensure it matches the expected format
                try:
                    rpm_value = int(line.split("=")[1].strip())
                    self.inital_rpm = rpm_value
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Devices isn't connected, connect devices then active again: {e}")
            
        return self.inital_rpm

    def close(self):
        self.arduino.close()

def list_com():
        ports = serial.tools.list_ports.comports()
        port_name = []
        port_description = []
        com_default= "COM6"
        description_default = f"Arduino Uno ({com_default})"
        port_name = []
        for port in ports:
            port_value = f"Arduino Uno ({port.device})"
            if port.description == port_value:
                com_default = port.device
                description_default = port_value
        port_name.append(com_default)
        port_description.append(description_default)

        for port in ports:
            port_name.append(port.device)
            port_description.append(port.description)
        return port_name, port_description, com_default


def configure_chart(chart, title, label_left, label_bottom):
        # Customize background
        chart.setTitle(title)
        chart.setLabel("left", label_left)
        chart.setLabel("bottom", label_bottom)
        chart.setBackground('black') 
        # Customize axis pens
        chart.getAxis('left').setPen(pg.mkPen(color='white', width=2))  # Y-axis
        chart.getAxis('bottom').setPen(pg.mkPen(color='white', width=2))  # X-axis

        # Customize axis labels
        chart.getAxis('left').setTextPen(pg.mkPen(color='white'))  # Y-axis labels
        chart.getAxis('bottom').setTextPen(pg.mkPen(color='white'))  # X-axis labels

        # Enable grid
        chart.showGrid(x=False, y=True, alpha=0.3)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Propeller Controll App")
        self.setWindowIcon(QIcon("public/icon.ico"))
        self.setIconSize(QSize(100, 100))
        self.setGeometry(100, 100, 1080, 800)
        self.setStyleSheet("""
            /* Main Window */
            QWidget {
                background-color: #ECECEC;
                font-size: 13px;
                color: #2C3E50;
            }
            QLabel {
                background-color: #CAD5D8;
                font-size: 13px;
                color: #2C3E50;
            }
            /* Toolbar (Dark Blue-Gray) */
            #toolbar_widget {
                background-color: #2C3E50;
                color: white;
                padding: 0px;
            }
            #Buttontoolbar {
                background-color: #2C3E50;
                color: white;
                border-radius: 0px;
                padding: 1px;
                margin: 0px;
                border: none;
            }
            #Buttontoolbar:hover {
                background-color: #2980B9;
            }
            #Buttontoolbar:pressed {
                background-color: #1F618D;
            }
            QPushButton {
                background-color: #3498DB;
                color: white;
                border-radius: 5px;
                padding: 0px;
                border: none;
            }
            QPushButton:hover {
                background-color: #2980B9;
            }
            QPushButton:pressed {
                background-color: #1F618D;
            }
            QLineEdit {
                background-color: white;
                border: 1px solid #BDC3C7;
                border-radius: 3px;
                padding: 5px;
            }
            QLineEdit:focus {
                border: 1px solid #3498DB;
            }
            #tab_widget {
                background-color: #CAD5D8;
                border-radius: 5px;
                padding: 10px;
            }
            
            
        """)
        # ----
        toolbar_widget = QWidget()
        toolbar_widget.setObjectName("toolbar_widget")
        #
        # Define Main layout in window
        pagelayout = QVBoxLayout()
        toolbar_layout = QHBoxLayout(toolbar_widget)
        self.stacklayout = QStackedLayout()
        # Define chilldrents layout
        tab0_layout = QHBoxLayout()
        button_tab0_layout = QVBoxLayout()
        chart_tab0_layout = QVBoxLayout()
        value_tab0_layout = QVBoxLayout()
        # -- Config tab0 layout
        tab0_layout.addLayout(button_tab0_layout, 2)
        tab0_layout.addLayout(chart_tab0_layout, 6)
        tab0_layout.addLayout(value_tab0_layout, 1)
        tab0_widget = QWidget()
        tab0_widget.setObjectName("tab_widget")
        # Define chilldrents layout Tab1
        tab1_layout = QHBoxLayout()
        col1_tab1_layout = QVBoxLayout()
        col2_tab1_layout = QVBoxLayout()
        col3_tab1_layout = QVBoxLayout()
        # -- -- Chill Clo2
        grid1_clo2_layout = QGridLayout()
        grid2_clo2_layout = QGridLayout()
        grid1_widget = QWidget()
        grid2_widget = QWidget()
        grid1_widget.setObjectName("grid_widget")
        grid2_widget.setObjectName("grid_widget")
        
        # -- Config tab1 layout
        tab1_layout.addLayout(col1_tab1_layout, 1)
        tab1_layout.addLayout(col2_tab1_layout, 4)
        tab1_layout.addLayout(col3_tab1_layout, 2)
        tab1_widget = QWidget()
        tab1_widget.setObjectName("tab_widget")
        # COnfig tab2
        tab2_layout = QHBoxLayout()
        tab2_widget = QWidget()
        tab2_widget.setObjectName("tab_widget")
        # COnfig tab3
        tab3_layout = QHBoxLayout()
        tab3_widget = QWidget()
        tab3_widget.setObjectName("tab_widget")
        # COnfig tab4
        tab4_layout = QHBoxLayout()
        tab4_widget = QWidget()
        tab4_widget.setObjectName("tab_widget")
        # Global constants
        text_input_height = 35
        btn_height = 35
        max_data_points = 5000
        
        self.port_name, self.port_description, self.port_default = list_com()
        self.com_selected = self.port_default        
        self.device_name = ["Dev1", "Dev2"] # Remove when run: temp row
        # --
        self.device_name, self.default_dev = list_dev() # remove to temp row
        self.dev_selected = self.default_dev
        self.sampling_rate = 5000  # Hz
        self.cutoff_frequency = 10
        self.number_persample = 300
        with open('public/storeage_calib.json', 'r') as file:
            data_calib = json.load(file)  # Parse the JSON file into a Python dictionary
        self.thrust_slope = data_calib["thrust_slope"]
        self.thrust_intercept = data_calib["thrust_intercept"]
        self.torque_slope = data_calib["torque_slope"]
        self.torque_intercept = data_calib["torque_intercept"]
        # Data for plotting
        self.revolution_time_data = []
        self.rpm_data = []
        self.revolution_time_counter = 0
        # Thrust
        self.max_data = 1000
        self.thrust_time_data = []
        self.thrust_data = []
        self.thrust_time_counter = 0
        self.torque_time_data = []
        self.torque_data = []
        self.torque_time_counter = 0

        # Arrange button layout and Stack layout
        pagelayout.addWidget(toolbar_widget,1)
        pagelayout.addLayout(self.stacklayout,20)

        
        # Add Tab switch button
        # Tab 0: Display 
        # Add widgets to tab 0
        self._setup_tab0(button_tab0_layout, chart_tab0_layout, value_tab0_layout, text_input_height, btn_height)
        # Add widgets to tab 1
        self._setup_tab1(col1_tab1_layout,col2_tab1_layout,grid1_clo2_layout,grid2_clo2_layout,grid1_widget,grid2_widget, text_input_height )
        # Add widgets to tab 2
        self._setup_tab2(tab2_layout)
        # Add widgets to tab 3
        self._setup_tab3(tab3_layout)
        # Add widgets to tab 4
        self._setup_tab4(tab4_layout)
        # -- Main tab0 layout
        

        # -- Main tab0 layout
        # Tab0
        display_tab_btn = QPushButton("Display")
        display_tab_btn.setObjectName("Buttontoolbar")
        display_tab_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        #display_tab_btn.setFixedHeight(btn_height)
        display_tab_btn.pressed.connect(self.activate_display_tab)
        toolbar_layout.addWidget(display_tab_btn)
        tab0_widget.setLayout(tab0_layout)
        self.stacklayout.addWidget(tab0_widget)
        # Tab 1: Seting
        setting_tab_btn = QPushButton("Settings")
        setting_tab_btn.setObjectName("Buttontoolbar")
        setting_tab_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        #setting_tab_btn.setFixedHeight(btn_height)
        setting_tab_btn.pressed.connect(self.activate_setting_tab)
        toolbar_layout.addWidget(setting_tab_btn)
        tab1_widget.setLayout(tab1_layout)
        self.stacklayout.addWidget(tab1_widget)
        # Documents
        self.label_documents = QLabel("Documents window", self)
        self.label_documents.setAlignment(Qt.AlignCenter)
        documents_tab_btn = QPushButton("Documents")
        documents_tab_btn.setObjectName("Buttontoolbar")
        documents_tab_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        #documents_tab_btn.setFixedHeight(btn_height)
        documents_tab_btn.pressed.connect(self.activate_documents_tab)
        toolbar_layout.addWidget(documents_tab_btn)
        tab2_widget.setLayout(tab2_layout)
        self.stacklayout.addWidget(tab2_widget)
        # Send data to email
        self.label_send_email = QLabel("Send Data to Email window", self)
        self.label_send_email.setAlignment(Qt.AlignCenter)
        send_email_tab_btn = QPushButton("Send Data")
        send_email_tab_btn.setObjectName("Buttontoolbar")
        send_email_tab_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        #send_email_tab_btn.setFixedHeight(btn_height)
        send_email_tab_btn.pressed.connect(self.activate_send_email_tab)
        toolbar_layout.addWidget(send_email_tab_btn)
        tab3_widget.setLayout(tab3_layout)
        self.stacklayout.addWidget(tab3_widget)
        # Information
        self.label_information = QLabel("Information window", self)
        self.label_information.setAlignment(Qt.AlignCenter)
        information_tab_btn = QPushButton("Informations")
        information_tab_btn.setObjectName("Buttontoolbar")
        information_tab_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        #information_tab_btn.setFixedHeight(btn_height)
        information_tab_btn.pressed.connect(self.activate_information_tab)
        toolbar_layout.addWidget(information_tab_btn)
        tab4_widget.setLayout(tab4_layout)
        self.stacklayout.addWidget(tab4_widget)
        # Bind to windows showing
        widget = QWidget()
        widget.setLayout(pagelayout)
        self.setCentralWidget(widget)

    def load_devices(self):
        if self.devices_running:
            try: 
                # self.device_reader.stop()
                # self.device_reader.close()
                self.motor_controller.close()
                self.load_devices_tab0.setText("Reload Devices")
                self.devices_running = False
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Devices isn't turn on: {str(e)}")
        else:
                    
            # Load devices
            
            try: 
                self.motor_controller = MotorControl(serial_port=self.com_selected)
                self.devices_running = True
                self.load_devices_tab0.setText("Deactive Devices")
                # self.timer = QTimer()
                # self.timer_motor = QTimer()
            except Exception as e:
                self.devices_running = True
                QMessageBox.critical(self, "Error", f"Devices isn't connected: {str(e)}")
    def toggle_camera(self):
        if self.camera_started:
            self.stop_camera()
        else:
            self.start_camera()
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
        self.video_button.setText("Stop Camera")
        self.camera_started = True
    def stop_camera(self):
        if self.camera:
            self.camera.stop()
            self.camera = None
            self.video_button.setText("Start Camera")
            self.camera_started = False
    
    def _setup_tab0(self, button_layout, chart_layout, value_layout, text_input_height, btn_height):
        # -- -- Load camera
        self.camera_selector = QComboBox()
        self.camera_selector.addItems([camera.description() for camera in QMediaDevices.videoInputs()])
        author_label = QLabel("Author: Trung-Duan Dang\nEmail: dangtrungduan@hcmut.edu.vn")
        author_label.setAlignment(Qt.AlignCenter)
        button_layout.addWidget(author_label,1)
        button_layout.addWidget(self.camera_selector,1)
        # Video widget
        self.video_widget = QVideoWidget()
        self.video_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        #self.video_widget.setFixedHeight(text_input_height*7)
        button_layout.addWidget(self.video_widget,10)

        # Start button
        # ====
        
        self.camera_started = False
        self.video_button = QPushButton("Start Camera")
        self.video_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        #self.video_button.setFixedHeight(text_input_height)
        self.video_button.setCheckable(True)
        self.video_button.clicked.connect(self.toggle_camera)
        button_layout.addWidget(self.video_button,1)

        # Camera and capture session
        self.camera = None
        self.capture_session = QMediaCaptureSession()
        # -- -- Load/Reload device
        self.devices_running = False
        self.load_devices_tab0 = QPushButton("Active Devices")
        self.load_devices_tab0.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        #self.load_devices_tab0.setFixedHeight(text_input_height)
        self.load_devices_tab0.setCheckable(True)
        self.load_devices_tab0.clicked.connect(self.load_devices)
        button_layout.addWidget(self.load_devices_tab0,1)
        # -- -- Label Input Power of motor
        label_input_power_tab0 = QLabel("Input Power Percent")
        label_input_power_tab0.setAlignment(Qt.AlignCenter)
        button_layout.addWidget(label_input_power_tab0)
        # -- -- Input Power of motor
        self.input_power_tab0 = QLineEdit()
        self.input_power_tab0.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        #self.input_power_tab0.setFixedHeight(text_input_height)
        self.input_power_tab0.setPlaceholderText("Enter power 10 - 95")
        button_layout.addWidget(self.input_power_tab0,1)
        # -- -- Start/stop motor button
        self.motor_running = False
        self.motor_btn_tab0 = QPushButton("Start motor")
        self.motor_btn_tab0.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.motor_btn_tab0.setCheckable(True)
        self.motor_btn_tab0.clicked.connect(self.toggle_motor)
        button_layout.addWidget(self.motor_btn_tab0,1)
        # -- -- Run button
        self.read_sensor_running = False
        self.sensor_btn_tab0 = QPushButton("Read data")
        self.sensor_btn_tab0.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.sensor_btn_tab0.setCheckable(True)
        self.sensor_btn_tab0.clicked.connect(self.toggle_reading)
        button_layout.addWidget(self.sensor_btn_tab0,1)
        # -- -- Stop button
        # stop_btn_tab0 = QPushButton("Stop reading")
        # stop_btn_tab0.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # stop_btn_tab0.clicked.connect(self.stop_reading)
        # button_layout.addWidget(stop_btn_tab0)
        # -- -- Clear data button
        clear_btn_tab0 = QPushButton("Clear data")
        clear_btn_tab0.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        clear_btn_tab0.pressed.connect(self.clear_data)
        button_layout.addWidget(clear_btn_tab0,1)
        # -- -- Offset data button
        offset_btn_tab0 = QPushButton("Offset")
        offset_btn_tab0.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        offset_btn_tab0.pressed.connect(self.offset_sensor_data)
        button_layout.addWidget(offset_btn_tab0,1)
        # -- -- Rename file ouput
        self.input_name_tab0 = QLineEdit()
        self.input_name_tab0.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        #self.input_name_tab0.setFixedHeight(text_input_height)
        self.input_name_tab0.setPlaceholderText("Enter file name")
        button_layout.addWidget(self.input_name_tab0,1)
        # -- -- Save data button
        save_btn_tab0 = QPushButton("Save to file")
        save_btn_tab0.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        save_btn_tab0.pressed.connect(self.save_sensor_data)
        button_layout.addWidget(save_btn_tab0,1)
        # -- -- Plot Chart Revolution
        self.revolution_chart = pg.PlotWidget()
        configure_chart(self.revolution_chart,"Motor Revolution Over Time","Revolution (RPM)","Time (s)")
        self.revolution_plot_curve = self.revolution_chart.plot(pen="y")  # Yellow line for plot
        chart_layout.addWidget(self.revolution_chart, 3)
        # -- -- Plot Chart Thrust
        self.thrust_chart = pg.PlotWidget()
        configure_chart(self.thrust_chart,"Thrust Over Time","Thrust (N)","Time (s)")
        self.thrust_plot_curve = self.thrust_chart.plot(pen="y")  # Yellow line for plot
        chart_layout.addWidget(self.thrust_chart, 3)
        # -- -- Plot Chart Torque
        self.torque_chart = pg.PlotWidget()
        configure_chart(self.torque_chart,"Torque Over Time","Torque (N.m)","Time (s)")
        self.torque_plot_curve = self.torque_chart.plot(pen="y")  # Yellow line for plot
        chart_layout.addWidget(self.torque_chart, 3)
        # -- -- Values Revolution
        self.revolution_value = QLabel("Revolution: ... rpm", self)
        self.revolution_value.setAlignment(Qt.AlignCenter)
        value_layout.addWidget(self.revolution_value)
        # -- -- Values Thrust
        self.thrust_value = QLabel("Thrust value: ...", self)
        self.thrust_value.setAlignment(Qt.AlignCenter)
        value_layout.addWidget(self.thrust_value)
        # -- -- Values Torque
        self.torque_value = QLabel("Torque value: ...", self)
        self.torque_value.setAlignment(Qt.AlignCenter)
        value_layout.addWidget(self.torque_value)
       # Initialize devices

    def _setup_tab1(self, col1_layout, col2_layout, grid1_layout,grid2_layout,grid1_widget,grid2_widget, text_input_height):
        # -- -- Label Select controller device
        label_com_tab1 = QLabel("Select controller device:")
        label_com_tab1.setAlignment(Qt.AlignCenter)
        col1_layout.addWidget(label_com_tab1,1)
        # -- -- Dropdown list device
        self.com_tab1 = QComboBox()
        self.com_tab1.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        #self.com_tab1.setFixedHeight(text_input_height)
        
        self.com_tab1.addItems(self.port_description)
        self.com_tab1.currentTextChanged.connect(self.handle_com_selection)
        col1_layout.addWidget(self.com_tab1,1)
        # -- -- Label Select Dataacquision device
        label_dev_tab1 = QLabel("Select Dataacquision device:")
        label_dev_tab1.setAlignment(Qt.AlignCenter)
        col1_layout.addWidget(label_dev_tab1,1)
        # -- -- Dropdown list device
        self.dev_tab1 = QComboBox()
        self.dev_tab1.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        #self.dev_tab1.setFixedHeight(text_input_height)
        self.dev_tab1.addItems(self.device_name)
        self.dev_tab1.currentTextChanged.connect(self.handle_dev_selection)
        col1_layout.addWidget(self.dev_tab1,1)
        # -- -- Label Select Dataacquision device
        label_type_get_tab1 = QLabel("Select type getData:")
        label_type_get_tab1.setAlignment(Qt.AlignCenter)
        col1_layout.addWidget(label_type_get_tab1,1)
        # -- -- Dropdown list type
        self.type_get_tab1 = QComboBox()
        self.type_get_tab1.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        #self.type_get_tab1.setFixedHeight(text_input_height)
        self.type_get_tab1.addItems(["AcquisitionType.FINITE","AcquisitionType.CONTINUOUS"])
        self.type_get_tab1.currentTextChanged.connect(self.handle_type_selection)
        col1_layout.addWidget(self.type_get_tab1,1)
        # -- -- Label Input Input Sample rate: 
        rate_label_tab1 = QLabel("Input Sample rate (Hz)")
        rate_label_tab1.setAlignment(Qt.AlignCenter)
        col1_layout.addWidget(rate_label_tab1,1)
        # -- -- Input Sample rate
        self.sample_rate_tab1 = QLineEdit()
        self.sample_rate_tab1.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding) #QSizePolicy.Fixed
        #self.sample_rate_tab1.setFixedHeight(text_input_height)
        self.sample_rate_tab1.setPlaceholderText("Input Sample rate 1 - 1000:")
        col1_layout.addWidget(self.sample_rate_tab1,1)
        # -- -- Label Input Number of Sample: 
        label_number_sample_tab1 = QLabel("Input Number of Sample")
        label_number_sample_tab1.setAlignment(Qt.AlignCenter)
        col1_layout.addWidget(label_number_sample_tab1,1)
        # -- -- Number of Sample
        self.number_sample_tab1 = QLineEdit()
        self.number_sample_tab1.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        #self.number_sample_tab1.setFixedHeight(text_input_height)
        self.number_sample_tab1.setPlaceholderText("Input Number of Sample per get")
        col1_layout.addWidget(self.number_sample_tab1,1)
        # -- -- Label Input Filter Frequency:
        label_filter_frecency_tab1 = QLabel("Input Filter Frequency:")
        label_filter_frecency_tab1.setAlignment(Qt.AlignCenter)
        col1_layout.addWidget(label_filter_frecency_tab1,1)
        # -- -- Input Filter Frequency:
        self.filter_frecency_tab1 = QLineEdit()
        self.filter_frecency_tab1.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        #self.filter_frecency_tab1.setFixedHeight(text_input_height)
        self.filter_frecency_tab1.setPlaceholderText("Input Filter Frequency")
        col1_layout.addWidget(self.filter_frecency_tab1,1)
        # -- -- Label Input Filter Frequency:
        Empty_tab1 = QLabel("")
        Empty_tab1.setAlignment(Qt.AlignCenter)
        col1_layout.addWidget(Empty_tab1, 12)

        # Calibration
        # -- -- Label Calibration Thrust:
        cablicate_task_label = QLabel("Cablication Task")
        cablicate_task_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        #cablicate_task_label.setFixedHeight(text_input_height)
        cablicate_task_label.setAlignment(Qt.AlignCenter)
        col2_layout.addWidget(cablicate_task_label,1)
        # -- -- Select Calibration Parameter:
        cablicate_parameter = QComboBox()
        cablicate_parameter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        #cablicate_parameter.setFixedHeight(text_input_height)
        cablicate_parameter.addItems(["None","Thrust", "Torque"])
        cablicate_parameter.currentTextChanged.connect(self.handle_parameter_selection)
        col2_layout.addWidget(cablicate_parameter,1)
        # -- -- -- Input Mass
        self.input_mass = QLineEdit()
        self.input_mass.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.input_mass.setFixedHeight(text_input_height)
        self.input_mass.setPlaceholderText("Input Mass Recent Applied")
        grid1_layout.addWidget(self.input_mass, 1, 1)
        # -- -- -- Get Voltage
        self.get_vol = QPushButton("Get Voltage")
        self.get_vol.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.get_vol.setFixedHeight(text_input_height)
        self.get_vol.clicked.connect(self.get_voltage_value)
        grid1_layout.addWidget(self.get_vol, 1, 2)
        # -- -- -- Show votage:
        self.mass_cablibration = []
        self.vol_cablibration = []
        self.show_voltage = QLabel("Thrust Cablication")
        self.show_voltage.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.show_voltage.setFixedHeight(text_input_height)
        self.show_voltage.setAlignment(Qt.AlignCenter)
        grid1_layout.addWidget(self.show_voltage, 1, 3)
        # -- -- -- Show storage value
        self.show_storage = QLabel("Show storage value")
        self.show_storage.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.show_storage.setFixedHeight(text_input_height)
        self.show_storage.setAlignment(Qt.AlignCenter)
        grid1_layout.addWidget(self.show_storage, 2, 1, 1, 2)
        # -- -- -- Show A B value
        self.show_slope = QLabel("Show A B value")
        self.show_slope.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.show_slope.setFixedHeight(text_input_height)
        self.show_slope.setAlignment(Qt.AlignCenter)
        grid1_layout.addWidget(self.show_slope, 2, 3)
        # -- -- -- Clear all
        self.clear_all = QPushButton("Clear all")
        self.clear_all.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.clear_all.setFixedHeight(text_input_height)
        self.clear_all.clicked.connect(self.clear_all_value)
        grid1_layout.addWidget(self.clear_all, 3, 1)
        # -- -- -- linear approximate
        self.linear_data = QPushButton("Linear approximate")
        self.linear_data.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.linear_data.setFixedHeight(text_input_height)
        self.linear_data.clicked.connect(self.linear_data_value)
        grid1_layout.addWidget(self.linear_data, 3, 2)
        # -- -- -- Set A B
        self.set_calib_value = QPushButton("Apply Calib Value")
        self.set_calib_value.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.set_calib_value.setFixedHeight(text_input_height)
        self.set_calib_value.clicked.connect(self.set_calib_slope_value)
        grid1_layout.addWidget(self.set_calib_value, 3, 3)
        # --
        grid1_widget.setLayout(grid1_layout)
        col2_layout.addWidget(grid1_widget,3)
        # -- -- plot calib data
        self.plot_widget = pg.PlotWidget()
        col2_layout.addWidget(self.plot_widget,4)
        # -- 
        Empty_tab1 = QLabel("")
        Empty_tab1.setAlignment(Qt.AlignCenter)
        col2_layout.addWidget(Empty_tab1, 3)
    def _setup_tab2(self,layout):
        self.browser = QWebEngineView()
        with open('public/documents_url.json', 'r') as file:
            urls = json.load(file)  # Parse the JSON file into a Python dictionary
        propeller_guided = urls["propeller_guided"]
  
        self.browser.setUrl(propeller_guided)
        layout.addWidget(self.browser)
    
    def _setup_tab3(self,layout):
        self.browser3 = QWebEngineView()
        with open('public/documents_url.json', 'r') as file:
            urls = json.load(file)  # Parse the JSON file into a Python dictionary
        email = urls["email"]
  
        self.browser3.setUrl(email)
        layout.addWidget(self.browser3)
    
    def _setup_tab4(self,layout):
        self.browser4 = QWebEngineView()
        with open('public/documents_url.json', 'r') as file:
            urls = json.load(file)  # Parse the JSON file into a Python dictionary
        information = "https://dhutech.com/"
  
        self.browser4.setUrl(information)
        layout.addWidget(self.browser4)
    def set_calib_slope_value(self):
        try:
            if self.parameter_selected == "Thrust":
                self.thrust_slope = self.slope
                self.thrust_intercept = self.intercept
            if self.parameter_selected == "Torque":
                self.torque_slope = self.slope
                self.torque_intercept = self.intercept
            storage_new = {"thrust_slope": self.thrust_slope, "thrust_intercept": self.thrust_intercept, "torque_slope": self.torque_slope, "torque_intercept": self.torque_intercept}
            with open('public/storeage_calib.json', "w") as file:
                json.dump(storage_new, file, indent=2) 
            QMessageBox.information(self,"Success", f"{self.parameter_selected} is calibrated: slope A = {self.slope}, intercept B = {self.intercept}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Please get Voltage, then click to Linear approximate Button: {e}")

    def plot_data_with_fit(self):
        self.plot_widget.clear()
        # Example experimental data
        x = np.array(self.vol_cablibration)
        y = np.array(self.mass_cablibration)
       
        # Perform linear fit
        
        y_fit = self.slope * x + self.intercept

        
        # Add labels and title
        self.plot_widget.setLabel('left', self.title_plot)
        self.plot_widget.setLabel('bottom', 'Voltage (V)')
        self.plot_widget.setTitle("Linear Fit to Experimental Data")
        self.plot_widget.addLegend()
        # Plot the experimental data
        self.plot_widget.plot(x, y, pen=None, symbol='o', symbolBrush='b', name="Experimental Data")

        # Plot the linear fit
        self.plot_widget.plot(x, y_fit, pen=pg.mkPen('r', width=2), name=f"Linear Fit: y = {self.slope:.2f}x + {self.intercept:.2f}")

    def linear_data_value(self):
        try:
        # Perform linear regression
            self.slope, self.intercept, r_value, p_value, std_err = linregress(self.vol_cablibration, self.mass_cablibration)
            
            self.plot_data_with_fit()
        except Exception as e:
            self.plot_widget.clear()
            QMessageBox.critical(self, "Error", f"Please get Voltage: {e}")


    def handle_parameter_selection(self, selected_text):
        QMessageBox.information(self, "Selection", f"You selected: {selected_text}")
        self.parameter_selected = selected_text

    def clear_all_value(self):
        self.mass_cablibration = []
        self.vol_cablibration = []
    def get_voltage_value(self):
        try: 
            if self.read_sensor_running:
                self.stop_reading()
            #self.read_sensor_running = True
            self.device_reader = NIDeviceReader(self.dev_selected,self.sampling_rate, self.number_persample)
            data_thrust, data_torque = self.device_reader.read_data()
            mass = float(self.input_mass.text())
            if self.parameter_selected == "Thrust":
                mean_vol = float(np.mean(data_thrust))
                self.title_plot = "Thrust (N)"
                converted_mass = mass*10*0.001
            if self.parameter_selected == "Torque":
                mean_vol = np.mean(data_torque)
                self.title_plot = "Torque (N.m)"
                converted_mass = mass*10*0.001*0.04
            self.vol_cablibration.append(mean_vol)
            self.mass_cablibration.append(converted_mass)
            self.show_voltage.setText(f"Volt: {round(mean_vol, 4)}")
            self.device_reader.stop()
            self.device_reader.close()
            self.read_sensor_running = False
        except Exception as e:
                QMessageBox.critical(self, "Error", f"Devices isn't connected, connect devices then active again: {e}")
    def activate_display_tab(self):
        self.stacklayout.setCurrentIndex(0)

    def activate_setting_tab(self):
        self.stacklayout.setCurrentIndex(1)

    def activate_documents_tab(self):
        self.stacklayout.setCurrentIndex(2)

    def activate_send_email_tab(self):
        self.stacklayout.setCurrentIndex(3)

    def activate_information_tab(self):
        self.stacklayout.setCurrentIndex(4)

    def handle_type_selection(self, selected_text):
        QMessageBox.information(self, "Selection", f"You selected: {selected_text}")
        self.type_selected = selected_text
                
    def handle_dev_selection(self, selected_text):
        QMessageBox.information(self, "Selection", f"You selected: {selected_text}")
        for i in range(len(self.device_name)):
            if self.device_name[i] == selected_text:
                self.dev_selected = self.device_name[i]
                
    def handle_com_selection(self, selected_text):
        QMessageBox.information(self, "Selection", f"You selected: {selected_text}")
        for i in range(len(self.port_description)):
            if self.port_description[i] == selected_text:
                self.com_selected = self.port_name[i]
                print("Selected port: ", self.com_selected)
     

    def toggle_motor(self):
        if self.motor_running:
            self.stop_motor()
        else:
            self.start_motor()
    def get_revolution(self):
        revolution_motor = self.motor_controller.read_rpm()
        self.revolution_value.setText(f"Revolution: {revolution_motor} rpm")
        # Update plot data
        self.revolution_time_data.append(self.revolution_time_counter)
        self.rpm_data.append(revolution_motor)
        self.revolution_time_counter += 0.1  # Increment time (100ms interval)
        # Update plot
        self.revolution_plot_curve.setData(self.revolution_time_data, self.rpm_data)
        
    def start_motor(self):
        try:
            self.motor_running = True
            self.motor_btn_tab0.setText("Stop motor")
            power = int( self.input_power_tab0.text())
            self.motor_controller.start_motor(power)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Devices isn't connected: {str(e)}")

    def stop_motor(self):
        try: 
            self.motor_running = False
            self.motor_btn_tab0.setText("Start motor")
            self.motor_controller.stop_motor()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Devices isn't connected: {str(e)}")

    def toggle_reading(self):
        if self.read_sensor_running:
            self.stop_reading()
        else:
            self.start_reading()

    def start_reading(self):
        try: 
            self.device_name, self.default_dev = list_dev() # remove to temp row
            self.dev_selected = self.default_dev
            self.device_reader = NIDeviceReader(self.dev_selected,self.sampling_rate, self.number_persample)
            self.timer = QTimer()
            self.timer_motor = QTimer()
            self.read_sensor_running = True
            self.sensor_btn_tab0.setText("Stop Reading")
            self.timer.timeout.connect(self.get_data)
            self.timer.start(100)  # Trigger read every 100 ms

            self.timer_motor.timeout.connect(self.get_revolution)
            self.timer_motor.start(100)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Devices isn't connected: {str(e)}")

    def stop_reading(self):
        try:
            self.read_sensor_running = False
            self.sensor_btn_tab0.setText("Start Reading")
            self.timer.stop()
            self.device_reader.stop()
            self.device_reader.close()
            self.timer_motor.stop()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Devices isn't connected: {str(e)}")
        #self.device_reader.close()
        

    def get_data(self):
        vol_thrust, vol_torque = self.device_reader.read_data()
        #thrust_filted = butter_lowpass_filter(data_thrust, self.cutoff_frequency,self.sampling_rate)
        mean_vol_thrust = np.mean(vol_thrust)
        mean_thrust = self.thrust_slope*mean_vol_thrust + self.thrust_intercept # -self.offset_thrust
        self.thrust_value.setText(f"Thrust: {round(mean_thrust,4)} N")
        # Update plot Thrust data
        self.thrust_time_data.append(self.thrust_time_counter)
        self.thrust_data.append(mean_thrust)
        self.thrust_time_counter += 0.1  # Increment time (100ms interval)
        self.thrust_plot_curve.setData(self.thrust_time_data, self.thrust_data)
        # Update plot Torque data
        mean_vol_torque = np.mean(vol_torque)
        mean_torque = self.torque_slope*mean_vol_torque + self.torque_intercept# - self.offset_torque
        self.torque_value.setText(f"Torque: {round(mean_torque,4)} N.m")
        # Update plot Thrust data
        self.torque_time_data.append(self.torque_time_counter)
        self.torque_data.append(mean_torque)
        self.torque_time_counter += 0.1  # Increment time (100ms interval)
        self.torque_plot_curve.setData(self.torque_time_data, self.torque_data)
        if len(self.thrust_time_data) > self.max_data:
            self.stop_reading()
            QMessageBox.information(self,"Warning", "The limit is reached: Save then Clear data!")
        

    def clear_data(self):
        # Clear Revolution data
        self.revolution_time_data = []
        self.rpm_data = []
        self.revolution_time_counter = 0
        # Thrust
        self.thrust_time_data = []
        self.thrust_data = []
        self.thrust_time_counter = 0
        # Torque
        self.torque_time_data = []
        self.torque_data = []
        self.torque_time_counter = 0
        QMessageBox.information(self,"Success", "All data is cleared!")
        

    def offset_sensor_data(self):
        try:
            self.stop_motor()
            if self.read_sensor_running:
                self.stop_reading()
            #self.read_sensor_running = True
            self.device_reader = NIDeviceReader(self.dev_selected,self.sampling_rate, self.number_persample)
            data_thrust, data_torque = self.device_reader.read_data()
            self.offset_thrust = self.thrust_slope*np.mean(data_thrust) + self.thrust_intercept
            self.offset_torque = self.torque_slope*np.mean(data_torque) + self.torque_intercept
            # ======
            self.thrust_intercept = self.thrust_intercept - self.offset_thrust
            self.torque_intercept = self.torque_intercept - self.offset_torque
            storage_new = {"thrust_slope": self.thrust_slope, "thrust_intercept": self.thrust_intercept, "torque_slope": self.torque_slope, "torque_intercept": self.torque_intercept}
            with open('public/storeage_calib.json', "w") as file:
                json.dump(storage_new, file, indent=2)
            self.device_reader.stop()
            self.device_reader.close()
            self.read_sensor_running = False
            QMessageBox.information(self,"Success", "Offseted data!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Devices isn't connected: {str(e)}")
    def save_sensor_data(self):
        
        # Get the filename from the input field
        filename = self.input_name_tab0.text().strip()
        
        # Validate the filename
        if not filename:
            QMessageBox.warning(self, "Error", "Please enter a valid file name.")
            return
        
        # Append a .csv extension if not provided
        if not filename.endswith(".csv"):
            filename += ".csv"
        # Create the /data directory if it doesn't exist
        data_dir = os.path.join(os.getcwd(), "Exported_data")
        os.makedirs(data_dir, exist_ok=True)

        # Construct the full file path
        file_path = os.path.join(data_dir, filename)
            
        try:
            # Collect data to save
            data_to_save = zip(
                self.thrust_time_data,
                self.thrust_data,
                self.torque_data,
                self.rpm_data,
                )
            
            # Write data to CSV file
            with open(file_path, "w", newline="") as csvfile:
                csvwriter = csv.writer(csvfile)
                # Write the header
                csvwriter.writerow(["Time Data (s)", "Thrust Data (N)", "Torque Data (N.m)", "Revolution Data (rpm)"])
                # Write the data rows
                for row in data_to_save:
                    csvwriter.writerow(row)
            
            QMessageBox.information(self, "Success", f"Data saved to {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save data: {str(e)}")

app = QApplication(sys.argv)

window = MainWindow()
window.show()

app.exec()