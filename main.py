import sys
import faulthandler
import json
import logging
import os
import shutil
import time
from datetime import datetime
from pathlib import Path

SMOKE_TEST_MODE = "--smoke-test" in sys.argv
SMOKE_TRACE_PATH = (
    Path(os.environ.get("TEMP", Path.home()))
    / "PropellerApp_smoke_trace.txt"
)


def _smoke_trace(message):
    """Write minimal startup diagnostics only during the packaged smoke test."""
    if not SMOKE_TEST_MODE:
        return
    with SMOKE_TRACE_PATH.open("a", encoding="utf-8") as trace_file:
        trace_file.write(f"{time.time():.3f} {message}\n")


if SMOKE_TEST_MODE and SMOKE_TRACE_PATH.exists():
    SMOKE_TRACE_PATH.unlink()
SMOKE_STACK_HANDLE = None
if SMOKE_TEST_MODE:
    smoke_stack_path = (
        Path(os.environ.get("TEMP", Path.home()))
        / "PropellerApp_smoke_stack.txt"
    )
    SMOKE_STACK_HANDLE = smoke_stack_path.open("w", encoding="utf-8")
    faulthandler.dump_traceback_later(
        10,
        repeat=True,
        file=SMOKE_STACK_HANDLE,
    )
_smoke_trace("stdlib imports complete")

from PySide6.QtCore import QEventLoop, QUrl, Qt, QThread, QTimer, QSize, Signal
import pyqtgraph as pg
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
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
    QGridLayout,
    QSpinBox,
)
from PySide6.QtMultimedia import QCamera, QMediaDevices, QMediaCaptureSession
from PySide6.QtMultimediaWidgets import QVideoWidget
_smoke_trace("PySide6 and pyqtgraph imports complete")
from scipy.stats import linregress
import serial
import serial.tools.list_ports
import numpy as np
_smoke_trace("SciPy, NumPy and serial imports complete")
from nidaqmx.constants import AcquisitionType, TerminalConfiguration
from nidaqmx import Task
import nidaqmx.system
_smoke_trace("nidaqmx imports complete")

from acquisition_worker import AcquisitionWorker
from processing.calibration import CalibrationCoefficients
from processing.filters import FilterSettings, SignalFilter
from processing.rpm import CounterRpmTracker, RpmReading
from processing.statistics import RunningStatistics
from storage.exporters import save_measurements_csv, save_measurements_excel
_smoke_trace("application module imports complete")


FORCE_CHANNEL = "ai2"
FORCE_NEGATIVE_INPUT = "ai6"
TORQUE_CHANNEL = "ai1"
TORQUE_NEGATIVE_INPUT = "ai5"
ANALOG_MIN_V = 0.0
ANALOG_MAX_V = 10.0
IS_FROZEN = bool(getattr(sys, "frozen", False))
SOURCE_DIR = Path(__file__).resolve().parent
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", SOURCE_DIR))
APP_DIR = Path(sys.executable).resolve().parent if IS_FROZEN else SOURCE_DIR
PUBLIC_DIR = BUNDLE_DIR / "public"
if IS_FROZEN:
    USER_DATA_DIR = (
        Path(os.environ.get("LOCALAPPDATA", Path.home())) / "PropellerApp"
    )
    EXPORT_DIR = Path.home() / "Documents" / "PropellerApp" / "Exported_data"
else:
    USER_DATA_DIR = PUBLIC_DIR
    EXPORT_DIR = APP_DIR / "Exported_data"
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
EXPORT_DIR.mkdir(parents=True, exist_ok=True)
APP_CONFIG_PATH = USER_DATA_DIR / "app_config.json"
CALIBRATION_PATH = USER_DATA_DIR / "storeage_calib.json"
for user_path in (APP_CONFIG_PATH, CALIBRATION_PATH):
    bundled_default = PUBLIC_DIR / user_path.name
    if not user_path.exists() and bundled_default.exists():
        shutil.copy2(bundled_default, user_path)
LOG_DIR = USER_DATA_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    filename=LOG_DIR / "propeller_app.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
LOGGER = logging.getLogger(__name__)
_smoke_trace("runtime paths and logging configured")


class NIDeviceReader:
    def __init__(
        self,
        dev_name,
        rate,
        samples,
        force_channel=FORCE_CHANNEL,
        torque_channel=TORQUE_CHANNEL,
        rpm_counter="ctr0",
        rpm_terminal="PFI0",
        pulses_per_revolution=1,
        rpm_calculation_window_s=0.1,
        rpm_timeout_s=1.5,
    ):
        self.rate = float(rate)
        self.samples = int(samples)
        self.task = Task()
        self.counter_task = Task()
        self.rpm_tracker = CounterRpmTracker(
            pulses_per_revolution=int(pulses_per_revolution),
            calculation_window_s=float(rpm_calculation_window_s),
            timeout_s=float(rpm_timeout_s),
        )
        try:
            # USB-6001 differential pairs are selected by adding only the
            # positive channel. NI-DAQmx maps ai2 to ai6(-) and ai1 to ai5(-).
            self.task.ai_channels.add_ai_voltage_chan(
                f"{dev_name}/{force_channel}",
                name_to_assign_to_channel="force_voltage",
                terminal_config=TerminalConfiguration.DIFF,
                min_val=ANALOG_MIN_V,
                max_val=ANALOG_MAX_V,
            )
            self.task.ai_channels.add_ai_voltage_chan(
                f"{dev_name}/{torque_channel}",
                name_to_assign_to_channel="torque_voltage",
                terminal_config=TerminalConfiguration.DIFF,
                min_val=ANALOG_MIN_V,
                max_val=ANALOG_MAX_V,
            )
            self.task.timing.cfg_samp_clk_timing(
                self.rate,
                sample_mode=AcquisitionType.CONTINUOUS,
                samps_per_chan=max(self.samples * 4, self.samples),
            )

            counter_channel = (
                self.counter_task.ci_channels.add_ci_count_edges_chan(
                    f"{dev_name}/{rpm_counter}",
                    name_to_assign_to_channel="rpm_edges",
                )
            )
            counter_channel.ci_count_edges_term = (
                f"/{dev_name}/{rpm_terminal}"
            )
            self.counter_task.start()
            initial_count = int(self.counter_task.read())
            self.rpm_tracker.reset(initial_count=initial_count)
            self.task.start()
        except Exception:
            self.close()
            raise

    def read_data(self):
        data = self.task.read(
            number_of_samples_per_channel=self.samples,
        )
        counter_value = int(self.counter_task.read())
        rpm_reading = self.rpm_tracker.update(counter_value)
        return np.array(data[0]), np.array(data[1]), rpm_reading

    def stop(self):
        for task in (self.task, self.counter_task):
            try:
                task.stop()
            except Exception:
                pass

    def close(self):
        for task in (self.task, self.counter_task):
            try:
                task.close()
            except Exception:
                pass


class SimulationReader:
    """Generate repeatable force and torque voltage blocks without NI hardware."""

    def __init__(
        self,
        _dev_name,
        rate,
        samples,
        pulses_per_revolution=1,
        **_reader_kwargs,
    ):
        self.rate = float(rate)
        self.samples = int(samples)
        self.pulses_per_revolution = int(pulses_per_revolution)
        self.sample_index = 0
        self.pulse_count = 0.0
        self.random = np.random.default_rng(20260729)

    def read_data(self):
        time_s = (
            np.arange(self.samples, dtype=np.float64) + self.sample_index
        ) / self.rate
        self.sample_index += self.samples
        force_voltage = (
            0.80
            + 0.06 * np.sin(2 * np.pi * 0.7 * time_s)
            + self.random.normal(0.0, 0.008, self.samples)
        )
        torque_voltage = (
            1.49
            + 0.04 * np.sin(2 * np.pi * 0.7 * time_s + 0.4)
            + self.random.normal(0.0, 0.006, self.samples)
        )
        block_end_s = self.sample_index / self.rate
        rpm = 1800.0 + 450.0 * np.sin(
            2 * np.pi * 0.12 * block_end_s
        )
        frequency_hz = rpm * self.pulses_per_revolution / 60.0
        self.pulse_count += (
            frequency_hz * self.samples / self.rate
        )
        rpm_reading = RpmReading(
            pulse_count=int(self.pulse_count),
            frequency_hz=float(frequency_hz),
            rpm=float(rpm),
            status="SIMULATION",
        )
        return force_voltage, torque_voltage, rpm_reading

    def stop(self):
        """Match the NI reader interface."""

    def close(self):
        """Match the NI reader interface."""


def list_dev():
    """Return currently visible NI-DAQmx devices without crashing the UI."""
    try:
        system = nidaqmx.system.System.local()
        devices = [device.name for device in system.devices]
        default_dev = devices[0] if devices else ""
        return devices, default_dev
    except Exception:
        LOGGER.exception("Unable to enumerate NI-DAQmx devices")
        return [], ""
class MotorControl:
    def __init__(
        self,
        serial_port="COM6",
        baud_rate=9600,
    ):
        self.arduino = serial.Serial(
            serial_port,
            baud_rate,
            timeout=0.1,
            write_timeout=1,
        )
    
    def set_power(self, value):
        command = f"{value}\n"
        self.arduino.write(command.encode())
        
    def start_motor(self, power):
        power = int(power)
        if not 10 <= power <= 95:
            raise ValueError("Motor power must be between 10 and 95 percent.")
        command = f"{power}\n"
        self.arduino.write(command.encode())
        
    def stop_motor(self):
        self.arduino.write(b"10\n")  # Stop motor
        
    def close(self):
        if self.arduino.is_open:
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
    """Main laboratory user interface."""

    request_acquisition_stop = Signal()

    def __init__(self):
        super().__init__()
        _smoke_trace("MainWindow initialization started")

        self.setWindowTitle("Propeller Controll App")
        self.setWindowIcon(QIcon(str(PUBLIC_DIR / "icon.ico")))
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
        with APP_CONFIG_PATH.open(
            "r",
            encoding="utf-8",
        ) as file:
            self.app_config = json.load(file)
        acquisition_config = self.app_config["acquisition"]
        filter_config = self.app_config["filter"]
        display_config = self.app_config["display"]
        rpm_config = self.app_config.setdefault("rpm", {})

        self.port_name, self.port_description, self.port_default = list_com()
        self.com_selected = self.port_default        
        self.device_name, self.default_dev = list_dev()
        _smoke_trace("NI device enumeration complete")
        self.dev_selected = self.default_dev
        self.sampling_rate = float(acquisition_config["sampling_rate_hz"])
        self.acquisition_mode = acquisition_config.get("mode", "hardware")
        self.number_persample = int(acquisition_config["block_size"])
        self.update_interval_ms = int(acquisition_config["update_interval_ms"])
        self.zero_duration_s = float(self.app_config["zero"]["duration_s"])
        self.rpm_counter = str(rpm_config.get("counter", "ctr0"))
        self.rpm_terminal = str(rpm_config.get("terminal", "PFI0"))
        self.pulses_per_revolution = int(
            rpm_config.get("pulses_per_revolution", 1)
        )
        self.rpm_calculation_window_s = float(
            rpm_config.get("calculation_window_s", 0.1)
        )
        self.rpm_timeout_s = float(rpm_config.get("timeout_s", 1.5))
        self.save_raw_data = bool(self.app_config["storage"]["save_raw"])
        self.show_raw = bool(display_config["show_raw"])
        self.show_filtered = bool(display_config["show_filtered"])
        self.filter_settings = FilterSettings(
            mode=filter_config["mode"],
            moving_average_window=int(
                filter_config["moving_average_window"]
            ),
            median_window=int(filter_config["median_window"]),
            lowpass_cutoff_hz=float(filter_config["lowpass_cutoff_hz"]),
            lowpass_order=int(filter_config["lowpass_order"]),
        )
        self.filter_settings.validate(self.sampling_rate)
        self.force_filter = SignalFilter(
            self.filter_settings,
            self.sampling_rate,
        )
        self.torque_filter = SignalFilter(
            self.filter_settings,
            self.sampling_rate,
        )
        with CALIBRATION_PATH.open(
            "r",
            encoding="utf-8",
        ) as file:
            data_calib = json.load(file)
        self.thrust_slope = data_calib["thrust_slope"]
        self.thrust_intercept = data_calib["thrust_intercept"]
        self.torque_slope = data_calib["torque_slope"]
        self.torque_intercept = data_calib["torque_intercept"]
        self.force_calibration = CalibrationCoefficients(
            self.thrust_slope,
            self.thrust_intercept,
            data_calib.get("thrust_zero_offset_v"),
        )
        self.torque_calibration = CalibrationCoefficients(
            self.torque_slope,
            self.torque_intercept,
            data_calib.get("torque_zero_offset_v"),
        )
        self.force_statistics = RunningStatistics()
        self.torque_statistics = RunningStatistics()
        self.rpm_statistics = RunningStatistics()
        self.measurement_rows = []
        self.recent_force_voltage = np.empty(0, dtype=np.float64)
        self.recent_torque_voltage = np.empty(0, dtype=np.float64)
        self.elapsed_samples = 0
        self.latest_rpm = 0.0
        self.latest_pulse_count = 0
        self.latest_frequency_hz = 0.0
        self.latest_rpm_status = "NOT_STARTED"
        self.acquisition_thread = None
        self.acquisition_worker = None
        self.motor_controller = None
        self.parameter_selected = "None"
        # Data for plotting
        self.revolution_time_data = []
        self.rpm_data = []
        self.revolution_time_counter = 0
        # Thrust
        self.max_data = int(display_config["max_plot_points"])
        self.thrust_time_data = []
        self.thrust_data = []
        self.thrust_raw_data = []
        self.thrust_time_counter = 0
        self.torque_time_data = []
        self.torque_data = []
        self.torque_raw_data = []
        self.torque_time_counter = 0

        # Arrange button layout and Stack layout
        pagelayout.addWidget(toolbar_widget,1)
        pagelayout.addLayout(self.stacklayout,20)

        
        # Add Tab switch button
        # Tab 0: Display 
        # Add widgets to tab 0
        self._setup_tab0(button_tab0_layout, chart_tab0_layout, value_tab0_layout, text_input_height, btn_height)
        # Add widgets to tab 1
        self._setup_tab1(
            col1_tab1_layout,
            col2_tab1_layout,
            col3_tab1_layout,
            grid1_clo2_layout,
            grid2_clo2_layout,
            grid1_widget,
            grid2_widget,
            text_input_height,
        )
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
        _smoke_trace("MainWindow initialization complete")

    def load_devices(self):
        if self.devices_running:
            try: 
                # self.device_reader.stop()
                # self.device_reader.close()
                self.motor_controller.close()
                self.motor_controller = None
                self.load_devices_tab0.setText("Connect Arduino")
                self.devices_running = False
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Devices isn't turn on: {str(e)}")
        else:
                    
            # Load devices
            
            try: 
                self.motor_controller = MotorControl(
                    serial_port=self.com_selected,
                )
                self.devices_running = True
                self.load_devices_tab0.setText("Disconnect Arduino")
                # self.timer = QTimer()
                # self.timer_motor = QTimer()
            except Exception as e:
                self.devices_running = False
                self.load_devices_tab0.setChecked(False)
                LOGGER.exception("Failed to open Arduino serial connection")
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
        self.load_devices_tab0 = QPushButton("Connect Arduino")
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
        zero_force_btn = QPushButton("Zero force")
        zero_force_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        zero_force_btn.pressed.connect(self.zero_force)
        button_layout.addWidget(zero_force_btn, 1)
        zero_torque_btn = QPushButton("Zero torque")
        zero_torque_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        zero_torque_btn.pressed.connect(self.zero_torque)
        button_layout.addWidget(zero_torque_btn, 1)
        offset_btn_tab0 = QPushButton("Zero all")
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
        save_btn_tab0 = QPushButton("Save CSV")
        save_btn_tab0.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        save_btn_tab0.pressed.connect(self.save_sensor_data)
        button_layout.addWidget(save_btn_tab0,1)
        save_excel_btn_tab0 = QPushButton("Save Excel")
        save_excel_btn_tab0.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding,
        )
        save_excel_btn_tab0.pressed.connect(self.save_excel_data)
        button_layout.addWidget(save_excel_btn_tab0, 1)
        # -- -- Plot Chart Revolution
        self.revolution_chart = pg.PlotWidget()
        configure_chart(self.revolution_chart,"Motor Revolution Over Time","Revolution (RPM)","Time (s)")
        self.revolution_plot_curve = self.revolution_chart.plot(
            pen=pg.mkPen("#F1C40F", width=2),
            name="RPM",
        )
        chart_layout.addWidget(self.revolution_chart, 3)
        # -- -- Plot Chart Thrust
        self.thrust_chart = pg.PlotWidget()
        configure_chart(self.thrust_chart,"Thrust Over Time","Thrust (N)","Time (s)")
        self.thrust_chart.addLegend()
        self.thrust_raw_plot_curve = self.thrust_chart.plot(
            pen=pg.mkPen("#95A5A6", width=1),
            name="Raw",
        )
        self.thrust_plot_curve = self.thrust_chart.plot(
            pen=pg.mkPen("#F1C40F", width=2),
            name="Filtered",
        )
        chart_layout.addWidget(self.thrust_chart, 3)
        # -- -- Plot Chart Torque
        self.torque_chart = pg.PlotWidget()
        configure_chart(self.torque_chart,"Torque Over Time","Torque (N.m)","Time (s)")
        self.torque_chart.addLegend()
        self.torque_raw_plot_curve = self.torque_chart.plot(
            pen=pg.mkPen("#95A5A6", width=1),
            name="Raw",
        )
        self.torque_plot_curve = self.torque_chart.plot(
            pen=pg.mkPen("#00BCD4", width=2),
            name="Filtered",
        )
        chart_layout.addWidget(self.torque_chart, 3)
        # -- -- Values Revolution
        self.revolution_value = QLabel("Revolution: ... rpm", self)
        self.revolution_value.setAlignment(Qt.AlignCenter)
        value_layout.addWidget(self.revolution_value)
        self.revolution_stats = QLabel("Avg: 0\nMin: 0\nMax: 0", self)
        self.revolution_stats.setAlignment(Qt.AlignCenter)
        value_layout.addWidget(self.revolution_stats)
        # -- -- Values Thrust
        self.thrust_value = QLabel("Thrust value: ...", self)
        self.thrust_value.setAlignment(Qt.AlignCenter)
        value_layout.addWidget(self.thrust_value)
        self.thrust_stats = QLabel("Avg: 0\nMin: 0\nMax: 0", self)
        self.thrust_stats.setAlignment(Qt.AlignCenter)
        value_layout.addWidget(self.thrust_stats)
        # -- -- Values Torque
        self.torque_value = QLabel("Torque value: ...", self)
        self.torque_value.setAlignment(Qt.AlignCenter)
        value_layout.addWidget(self.torque_value)
        self.torque_stats = QLabel("Avg: 0\nMin: 0\nMax: 0", self)
        self.torque_stats.setAlignment(Qt.AlignCenter)
        value_layout.addWidget(self.torque_stats)
        self.update_curve_visibility()
       # Initialize devices

    def _setup_tab1(
        self,
        col1_layout,
        col2_layout,
        col3_layout,
        grid1_layout,
        grid2_layout,
        grid1_widget,
        grid2_widget,
        text_input_height,
    ):
        mode_label = QLabel("Acquisition mode:")
        mode_label.setAlignment(Qt.AlignCenter)
        col1_layout.addWidget(mode_label, 1)
        self.acquisition_mode_combo = QComboBox()
        self.acquisition_mode_combo.addItem("Hardware NI", "hardware")
        self.acquisition_mode_combo.addItem("Simulation", "simulation")
        mode_index = self.acquisition_mode_combo.findData(
            self.acquisition_mode
        )
        self.acquisition_mode_combo.setCurrentIndex(max(0, mode_index))
        col1_layout.addWidget(self.acquisition_mode_combo, 1)

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
        self.refresh_ni_button = QPushButton("Scan NI devices")
        self.refresh_ni_button.clicked.connect(self.refresh_ni_devices)
        col1_layout.addWidget(self.refresh_ni_button, 1)
        acquisition_mode_label = QLabel(
            "Acquisition: continuous blocks in QThread"
        )
        acquisition_mode_label.setAlignment(Qt.AlignCenter)
        acquisition_mode_label.setWordWrap(True)
        col1_layout.addWidget(acquisition_mode_label, 1)
        # -- -- Label Input Input Sample rate: 
        rate_label_tab1 = QLabel("Input Sample rate (Hz)")
        rate_label_tab1.setAlignment(Qt.AlignCenter)
        col1_layout.addWidget(rate_label_tab1,1)
        # -- -- Input Sample rate
        self.sample_rate_tab1 = QLineEdit()
        self.sample_rate_tab1.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding) #QSizePolicy.Fixed
        self.sample_rate_tab1.setText(f"{self.sampling_rate:g}")
        self.sample_rate_tab1.setPlaceholderText("Input Sample rate 1 - 10000:")
        col1_layout.addWidget(self.sample_rate_tab1,1)
        # -- -- Label Input Number of Sample: 
        label_number_sample_tab1 = QLabel("Input Number of Sample")
        label_number_sample_tab1.setAlignment(Qt.AlignCenter)
        col1_layout.addWidget(label_number_sample_tab1,1)
        # -- -- Number of Sample
        self.number_sample_tab1 = QLineEdit()
        self.number_sample_tab1.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.number_sample_tab1.setText(str(self.number_persample))
        self.number_sample_tab1.setPlaceholderText("Input Number of Sample per get")
        col1_layout.addWidget(self.number_sample_tab1,1)
        self.apply_settings_btn = QPushButton("Apply acquisition settings")
        self.apply_settings_btn.clicked.connect(self.apply_processing_settings)
        col1_layout.addWidget(self.apply_settings_btn, 1)
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

        rpm_group = QGroupBox("NI RPM counter")
        rpm_form = QFormLayout(rpm_group)
        self.rpm_counter_label = QLabel("ctr0 (USB-6001)")
        rpm_form.addRow("Counter", self.rpm_counter_label)

        self.rpm_terminal_combo = QComboBox()
        self.rpm_terminal_combo.addItems(["PFI0", "PFI1"])
        terminal_index = self.rpm_terminal_combo.findText(
            self.rpm_terminal
        )
        self.rpm_terminal_combo.setCurrentIndex(max(0, terminal_index))
        rpm_form.addRow("Pulse terminal", self.rpm_terminal_combo)

        self.pulses_per_revolution_spin = QSpinBox()
        self.pulses_per_revolution_spin.setRange(1, 10000)
        self.pulses_per_revolution_spin.setValue(
            self.pulses_per_revolution
        )
        rpm_form.addRow(
            "Pulses per revolution",
            self.pulses_per_revolution_spin,
        )

        self.rpm_window_spin = QDoubleSpinBox()
        self.rpm_window_spin.setRange(0.05, 10.0)
        self.rpm_window_spin.setSingleStep(0.05)
        self.rpm_window_spin.setDecimals(2)
        self.rpm_window_spin.setValue(self.rpm_calculation_window_s)
        rpm_form.addRow("Calculation window (s)", self.rpm_window_spin)

        self.rpm_timeout_spin = QDoubleSpinBox()
        self.rpm_timeout_spin.setRange(0.1, 30.0)
        self.rpm_timeout_spin.setSingleStep(0.1)
        self.rpm_timeout_spin.setDecimals(2)
        self.rpm_timeout_spin.setValue(self.rpm_timeout_s)
        rpm_form.addRow("No-pulse timeout (s)", self.rpm_timeout_spin)

        rpm_note = QLabel(
            "RPM signal: NI P2.0/PFI0. Arduino COM is used only "
            "for ESC control on D11."
        )
        rpm_note.setWordWrap(True)
        rpm_form.addRow(rpm_note)
        col3_layout.addWidget(rpm_group)

        filter_group = QGroupBox("Advanced signal processing")
        filter_form = QFormLayout(filter_group)
        self.filter_mode_combo = QComboBox()
        self.filter_mode_combo.addItem("No filter", "none")
        self.filter_mode_combo.addItem("Moving average", "moving_average")
        self.filter_mode_combo.addItem("Median", "median")
        self.filter_mode_combo.addItem("Butterworth low-pass", "butterworth")
        mode_index = self.filter_mode_combo.findData(self.filter_settings.mode)
        self.filter_mode_combo.setCurrentIndex(max(0, mode_index))
        filter_form.addRow("Filter mode", self.filter_mode_combo)

        self.moving_average_spin = QSpinBox()
        self.moving_average_spin.setRange(1, 999)
        self.moving_average_spin.setValue(
            self.filter_settings.moving_average_window
        )
        filter_form.addRow("Moving-average window", self.moving_average_spin)

        self.median_window_spin = QSpinBox()
        self.median_window_spin.setRange(1, 999)
        self.median_window_spin.setSingleStep(2)
        self.median_window_spin.setValue(self.filter_settings.median_window)
        filter_form.addRow("Median window (odd)", self.median_window_spin)

        self.lowpass_cutoff_spin = QDoubleSpinBox()
        self.lowpass_cutoff_spin.setRange(0.01, 9999.0)
        self.lowpass_cutoff_spin.setDecimals(2)
        self.lowpass_cutoff_spin.setValue(
            self.filter_settings.lowpass_cutoff_hz
        )
        filter_form.addRow("Low-pass cutoff (Hz)", self.lowpass_cutoff_spin)

        self.lowpass_order_spin = QSpinBox()
        self.lowpass_order_spin.setRange(1, 12)
        self.lowpass_order_spin.setValue(self.filter_settings.lowpass_order)
        filter_form.addRow("Low-pass order", self.lowpass_order_spin)

        self.show_raw_checkbox = QCheckBox("Show raw signal")
        self.show_raw_checkbox.setChecked(self.show_raw)
        self.show_raw_checkbox.toggled.connect(self.update_curve_visibility)
        filter_form.addRow(self.show_raw_checkbox)

        self.show_filtered_checkbox = QCheckBox("Show filtered signal")
        self.show_filtered_checkbox.setChecked(self.show_filtered)
        self.show_filtered_checkbox.toggled.connect(
            self.update_curve_visibility
        )
        filter_form.addRow(self.show_filtered_checkbox)

        self.save_raw_checkbox = QCheckBox("Save raw data")
        self.save_raw_checkbox.setChecked(self.save_raw_data)
        filter_form.addRow(self.save_raw_checkbox)

        apply_filter_button = QPushButton("Apply filter")
        apply_filter_button.clicked.connect(self.apply_processing_settings)
        filter_form.addRow(apply_filter_button)

        self.processing_status_label = QLabel(
            "Streaming block filter is active."
        )
        self.processing_status_label.setWordWrap(True)
        filter_form.addRow(self.processing_status_label)
        col3_layout.addWidget(filter_group)
        col3_layout.addStretch(1)

    def update_curve_visibility(self):
        """Apply the raw/filtered visibility selection to both analog charts."""
        show_raw_widget = getattr(self, "show_raw_checkbox", None)
        show_filtered_widget = getattr(self, "show_filtered_checkbox", None)
        self.show_raw = (
            show_raw_widget.isChecked()
            if show_raw_widget is not None
            else self.show_raw
        )
        self.show_filtered = (
            show_filtered_widget.isChecked()
            if show_filtered_widget is not None
            else self.show_filtered
        )
        if hasattr(self, "thrust_raw_plot_curve"):
            self.thrust_raw_plot_curve.setVisible(self.show_raw)
            self.torque_raw_plot_curve.setVisible(self.show_raw)
            self.thrust_plot_curve.setVisible(self.show_filtered)
            self.torque_plot_curve.setVisible(self.show_filtered)

    def apply_processing_settings(self):
        """Validate, apply and persist acquisition/filter settings."""
        if self.read_sensor_running:
            QMessageBox.warning(
                self,
                "Acquisition running",
                "Stop reading before changing acquisition or filter settings.",
            )
            return
        try:
            sampling_rate = float(self.sample_rate_tab1.text())
            block_size = int(self.number_sample_tab1.text())
            if not 1 <= sampling_rate <= 10000:
                raise ValueError(
                    "Sampling rate must be from 1 to 10000 Hz for two "
                    "USB-6001 analog channels."
                )
            if not 1 <= block_size <= 10000:
                raise ValueError("Block size must be from 1 to 10000.")
            pulses_per_revolution = (
                self.pulses_per_revolution_spin.value()
            )
            rpm_calculation_window_s = self.rpm_window_spin.value()
            rpm_timeout_s = self.rpm_timeout_spin.value()
            if rpm_timeout_s < rpm_calculation_window_s:
                raise ValueError(
                    "RPM timeout must be greater than or equal to the "
                    "RPM calculation window."
                )
            settings = FilterSettings(
                mode=str(self.filter_mode_combo.currentData()),
                moving_average_window=self.moving_average_spin.value(),
                median_window=self.median_window_spin.value(),
                lowpass_cutoff_hz=self.lowpass_cutoff_spin.value(),
                lowpass_order=self.lowpass_order_spin.value(),
            )
            settings.validate(sampling_rate)
            self.sampling_rate = sampling_rate
            self.number_persample = block_size
            self.rpm_counter = "ctr0"
            self.rpm_terminal = self.rpm_terminal_combo.currentText()
            self.pulses_per_revolution = pulses_per_revolution
            self.rpm_calculation_window_s = rpm_calculation_window_s
            self.rpm_timeout_s = rpm_timeout_s
            self.acquisition_mode = str(
                self.acquisition_mode_combo.currentData()
            )
            self.filter_settings = settings
            self.force_filter = SignalFilter(settings, sampling_rate)
            self.torque_filter = SignalFilter(settings, sampling_rate)
            self.save_raw_data = self.save_raw_checkbox.isChecked()
            self.update_curve_visibility()

            acquisition_config = self.app_config["acquisition"]
            acquisition_config["mode"] = self.acquisition_mode
            acquisition_config["sampling_rate_hz"] = sampling_rate
            acquisition_config["block_size"] = block_size
            self.app_config["rpm"] = {
                "counter": self.rpm_counter,
                "terminal": self.rpm_terminal,
                "pulses_per_revolution": self.pulses_per_revolution,
                "calculation_window_s": self.rpm_calculation_window_s,
                "timeout_s": self.rpm_timeout_s,
            }
            self.app_config["filter"] = {
                "mode": settings.mode,
                "moving_average_window": settings.moving_average_window,
                "median_window": settings.median_window,
                "lowpass_cutoff_hz": settings.lowpass_cutoff_hz,
                "lowpass_order": settings.lowpass_order,
            }
            self.app_config["display"]["show_raw"] = self.show_raw
            self.app_config["display"]["show_filtered"] = self.show_filtered
            self.app_config["storage"]["save_raw"] = self.save_raw_data
            with APP_CONFIG_PATH.open(
                "w",
                encoding="utf-8",
            ) as file:
                json.dump(self.app_config, file, indent=2)
            self.processing_status_label.setText(
                f"Applied: {settings.mode}, {sampling_rate:g} Hz, "
                f"{block_size} samples/block; RPM {self.rpm_counter}/"
                f"{self.rpm_terminal}, {self.pulses_per_revolution} "
                "pulse/rev."
            )
            LOGGER.info(
                "Applied acquisition/filter settings: %s",
                self.app_config,
            )
        except (TypeError, ValueError) as exc:
            QMessageBox.critical(self, "Invalid settings", str(exc))

    def _save_calibration(self):
        """Persist calibration and independent zero offsets."""
        storage_new = {
            "thrust_slope": self.force_calibration.slope,
            "thrust_intercept": self.force_calibration.intercept,
            "thrust_zero_offset_v": self.force_calibration.zero_offset_v,
            "torque_slope": self.torque_calibration.slope,
            "torque_intercept": self.torque_calibration.intercept,
            "torque_zero_offset_v": self.torque_calibration.zero_offset_v,
        }
        with CALIBRATION_PATH.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(storage_new, file, indent=2)

    def _add_external_link_tab(self, layout, title, description, target):
        """Create a lightweight tab that opens content with Windows."""
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignCenter)
        description_label = QLabel(description)
        description_label.setAlignment(Qt.AlignCenter)
        description_label.setWordWrap(True)
        open_button = QPushButton("Open")
        open_button.clicked.connect(
            lambda _checked=False, url=target: QDesktopServices.openUrl(url)
        )
        panel_layout.addStretch(1)
        panel_layout.addWidget(title_label)
        panel_layout.addWidget(description_label)
        panel_layout.addWidget(open_button)
        panel_layout.addStretch(1)
        layout.addWidget(panel)

    def _setup_tab2(self, layout):
        guide_path = PUBLIC_DIR / "propeller_guided.pdf"
        self._add_external_link_tab(
            layout,
            "Propeller guide",
            "Open the bundled guide with the default PDF reader.",
            QUrl.fromLocalFile(str(guide_path)),
        )

    def _setup_tab3(self, layout):
        with (PUBLIC_DIR / "documents_url.json").open(
            "r",
            encoding="utf-8",
        ) as file:
            urls = json.load(file)
        email = urls["email"]
        self._add_external_link_tab(
            layout,
            "Email",
            "Open Gmail in the default web browser.",
            QUrl(email),
        )

    def _setup_tab4(self, layout):
        with (PUBLIC_DIR / "documents_url.json").open(
            "r",
            encoding="utf-8",
        ) as file:
            urls = json.load(file)
        self._add_external_link_tab(
            layout,
            "Information",
            "Open the information page in the default web browser.",
            QUrl(urls["dhutech"]),
        )
    def set_calib_slope_value(self):
        try:
            if self.parameter_selected == "Thrust":
                self.thrust_slope = self.slope
                self.thrust_intercept = self.intercept
                self.force_calibration = CalibrationCoefficients(
                    self.thrust_slope,
                    self.thrust_intercept,
                )
            if self.parameter_selected == "Torque":
                self.torque_slope = self.slope
                self.torque_intercept = self.intercept
                self.torque_calibration = CalibrationCoefficients(
                    self.torque_slope,
                    self.torque_intercept,
                )
            self._save_calibration()
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
        self.parameter_selected = selected_text

    def clear_all_value(self):
        self.mass_cablibration = []
        self.vol_cablibration = []

    def get_voltage_value(self):
        """Capture the latest background-read voltage for calibration."""
        try:
            if not self.read_sensor_running:
                raise RuntimeError(
                    "Start NI data reading, wait for a stable signal, "
                    "then capture the voltage."
                )
            mass = float(self.input_mass.text())
            if self.parameter_selected == "Thrust":
                if self.recent_force_voltage.size == 0:
                    raise RuntimeError("No force voltage has been received.")
                mean_vol = float(np.mean(self.recent_force_voltage))
                self.title_plot = "Thrust (N)"
                converted_mass = mass * 9.80665 * 0.001
            elif self.parameter_selected == "Torque":
                if self.recent_torque_voltage.size == 0:
                    raise RuntimeError("No torque voltage has been received.")
                mean_vol = float(np.mean(self.recent_torque_voltage))
                self.title_plot = "Torque (N.m)"
                converted_mass = mass * 9.80665 * 0.001 * 0.04
            else:
                raise ValueError("Select Thrust or Torque first.")
            self.vol_cablibration.append(mean_vol)
            self.mass_cablibration.append(converted_mass)
            self.show_voltage.setText(f"Volt: {round(mean_vol, 4)}")
        except Exception as e:
            QMessageBox.critical(self, "Calibration error", str(e))
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
        self.type_selected = selected_text

    def refresh_ni_devices(self):
        """Rescan NI-DAQmx and update the device selector."""
        devices, default_device = list_dev()
        self.device_name = devices
        self.dev_tab1.blockSignals(True)
        self.dev_tab1.clear()
        self.dev_tab1.addItems(devices)
        self.dev_tab1.blockSignals(False)
        self.dev_selected = default_device
        if devices:
            QMessageBox.information(
                self,
                "NI devices",
                "Detected: " + ", ".join(devices),
            )
        else:
            QMessageBox.warning(
                self,
                "NI devices",
                "No NI-DAQmx device was detected. Check USB cable, "
                "NI-DAQmx driver and NI MAX.",
            )

    def handle_dev_selection(self, selected_text):
        for i in range(len(self.device_name)):
            if self.device_name[i] == selected_text:
                self.dev_selected = self.device_name[i]
                
    def handle_com_selection(self, selected_text):
        for i in range(len(self.port_description)):
            if self.port_description[i] == selected_text:
                self.com_selected = self.port_name[i]
                print("Selected port: ", self.com_selected)
     

    def toggle_motor(self):
        if self.motor_running:
            self.stop_motor()
        else:
            self.start_motor()
    def update_revolution(
        self,
        reading: RpmReading,
        elapsed_s: float,
    ) -> None:
        """Update RPM values and plot from the NI counter block result."""
        self.latest_rpm = max(0.0, float(reading.rpm))
        self.latest_pulse_count = max(0, int(reading.pulse_count))
        self.latest_frequency_hz = max(
            0.0,
            float(reading.frequency_hz),
        )
        self.latest_rpm_status = str(reading.status)
        self.revolution_value.setText(
            f"Revolution: {self.latest_rpm:.1f} rpm\n"
            f"{self.latest_frequency_hz:.2f} Hz · "
            f"{self.latest_rpm_status}"
        )
        self.rpm_statistics.update(
            np.asarray([self.latest_rpm], dtype=np.float64)
        )
        self.revolution_time_data.append(elapsed_s)
        self.rpm_data.append(self.latest_rpm)
        self.revolution_time_data = self.revolution_time_data[-self.max_data:]
        self.rpm_data = self.rpm_data[-self.max_data:]
        self.revolution_plot_curve.setData(self.revolution_time_data, self.rpm_data)
        stats = self.rpm_statistics.as_dict()
        self.revolution_stats.setText(
            f"Avg: {stats['mean']:.1f}\n"
            f"Min: {stats['min']:.1f}\n"
            f"Max: {stats['max']:.1f}"
        )

    def start_motor(self):
        try:
            if self.motor_controller is None:
                raise RuntimeError("Connect Arduino before starting the motor.")
            power = int( self.input_power_tab0.text())
            self.motor_controller.start_motor(power)
            self.motor_running = True
            self.motor_btn_tab0.setText("Stop motor")
            self.motor_btn_tab0.setChecked(True)
        except Exception as e:
            self.motor_running = False
            self.motor_btn_tab0.setText("Start motor")
            self.motor_btn_tab0.setChecked(False)
            QMessageBox.critical(self, "Error", f"Devices isn't connected: {str(e)}")

    def stop_motor(self):
        try:
            self.motor_running = False
            self.motor_btn_tab0.setText("Start motor")
            self.motor_btn_tab0.setChecked(False)
            if self.motor_controller is None:
                return
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
            if self.acquisition_mode == "hardware" and not self.dev_selected:
                raise RuntimeError(
                    "No NI device is selected. Connect the USB-6001 and "
                    "click Scan NI devices."
                )
            if self.acquisition_thread is not None:
                raise RuntimeError("The NI acquisition worker is already active.")
            self.force_filter.reset()
            self.torque_filter.reset()

            self.acquisition_thread = QThread(self)
            reader_factory = (
                SimulationReader
                if self.acquisition_mode == "simulation"
                else NIDeviceReader
            )
            device_name = self.dev_selected or "Simulation"
            self.acquisition_worker = AcquisitionWorker(
                reader_factory,
                device_name,
                self.sampling_rate,
                self.number_persample,
                self.update_interval_ms,
                reader_kwargs={
                    "rpm_counter": self.rpm_counter,
                    "rpm_terminal": self.rpm_terminal,
                    "pulses_per_revolution": (
                        self.pulses_per_revolution
                    ),
                    "rpm_calculation_window_s": (
                        self.rpm_calculation_window_s
                    ),
                    "rpm_timeout_s": self.rpm_timeout_s,
                },
            )
            self.acquisition_worker.moveToThread(self.acquisition_thread)
            self.acquisition_thread.started.connect(
                self.acquisition_worker.start
            )
            self.request_acquisition_stop.connect(
                self.acquisition_worker.stop
            )
            self.acquisition_worker.block_ready.connect(self.get_data)
            self.acquisition_worker.error.connect(
                self._on_acquisition_error
            )
            self.acquisition_worker.finished.connect(
                self.acquisition_worker.deleteLater
            )
            self.acquisition_thread.finished.connect(
                self._on_acquisition_thread_finished
            )
            self.acquisition_thread.finished.connect(
                self.acquisition_thread.deleteLater
            )

            self.read_sensor_running = True
            self.sensor_btn_tab0.setText("Stop Reading")
            self.sensor_btn_tab0.setChecked(True)
            self.acquisition_thread.start()
            LOGGER.info(
                "Acquisition started: mode=%s device=%s rate=%s block=%s "
                "rpm=%s/%s ppr=%s",
                self.acquisition_mode,
                device_name,
                self.sampling_rate,
                self.number_persample,
                self.rpm_counter,
                self.rpm_terminal,
                self.pulses_per_revolution,
            )
        except Exception as e:
            LOGGER.exception("Failed to start NI acquisition")
            self.read_sensor_running = False
            self.sensor_btn_tab0.setChecked(False)
            QMessageBox.critical(self, "Error", f"Devices isn't connected: {str(e)}")

    def stop_reading(self):
        """Stop timers, request worker shutdown and release the NI task."""
        self.read_sensor_running = False
        self.sensor_btn_tab0.setText("Read data")
        self.sensor_btn_tab0.setChecked(False)
        thread = self.acquisition_thread
        worker = self.acquisition_worker
        stop_loop = None
        stop_timeout = None
        if thread is not None and thread.isRunning():
            stop_loop = QEventLoop(self)
            stop_timeout = QTimer(self)
            stop_timeout.setSingleShot(True)
            thread.finished.connect(stop_loop.quit)
            stop_timeout.timeout.connect(stop_loop.quit)
            stop_timeout.start(3000)
            if worker is not None:
                self.request_acquisition_stop.emit()
            stop_loop.exec()
            if thread.isRunning():
                LOGGER.error("NI acquisition thread did not stop within 3 seconds")
                thread.requestInterruption()
                thread.quit()
        elif worker is not None:
            self.request_acquisition_stop.emit()
        if worker is not None:
            try:
                self.request_acquisition_stop.disconnect(worker.stop)
            except (RuntimeError, TypeError, SystemError):
                pass
        self.acquisition_worker = None
        self.acquisition_thread = None
        LOGGER.info("NI acquisition stopped")

    def _on_acquisition_error(self, message):
        """Report a worker error without leaving the UI in a running state."""
        LOGGER.error("NI acquisition error: %s", message)
        self.read_sensor_running = False
        self.sensor_btn_tab0.setText("Read data")
        self.sensor_btn_tab0.setChecked(False)
        QMessageBox.critical(self, "NI acquisition error", message)

    def _on_acquisition_thread_finished(self):
        """Clear worker references after an asynchronous failure or stop."""
        self.read_sensor_running = False
        self.sensor_btn_tab0.setText("Read data")
        self.sensor_btn_tab0.setChecked(False)
        self.acquisition_worker = None
        self.acquisition_thread = None

    def get_data(self, vol_thrust, vol_torque, rpm_reading):
        """Process and store one synchronized NI analog/counter block."""
        force_voltage = np.asarray(vol_thrust, dtype=np.float64)
        torque_voltage = np.asarray(vol_torque, dtype=np.float64)
        sample_count = min(force_voltage.size, torque_voltage.size)
        if sample_count == 0:
            return
        force_voltage = force_voltage[:sample_count]
        torque_voltage = torque_voltage[:sample_count]

        force_raw = np.asarray(
            self.force_calibration.convert(force_voltage),
            dtype=np.float64,
        )
        torque_raw = np.asarray(
            self.torque_calibration.convert(torque_voltage),
            dtype=np.float64,
        )
        force_filtered = self.force_filter.process(force_raw)
        torque_filtered = self.torque_filter.process(torque_raw)
        self.force_statistics.update(force_filtered)
        self.torque_statistics.update(torque_filtered)

        history_count = max(
            int(self.sampling_rate * max(2.0, self.zero_duration_s)),
            self.number_persample,
        )
        self.recent_force_voltage = np.concatenate(
            (self.recent_force_voltage, force_voltage)
        )[-history_count:]
        self.recent_torque_voltage = np.concatenate(
            (self.recent_torque_voltage, torque_voltage)
        )[-history_count:]

        mean_force_raw = float(np.mean(force_raw))
        mean_force_filtered = float(np.mean(force_filtered))
        mean_torque_raw = float(np.mean(torque_raw))
        mean_torque_filtered = float(np.mean(torque_filtered))
        elapsed_s = (self.elapsed_samples + sample_count) / self.sampling_rate
        self.update_revolution(rpm_reading, elapsed_s)
        self.thrust_time_data.append(elapsed_s)
        self.torque_time_data.append(elapsed_s)
        self.thrust_raw_data.append(mean_force_raw)
        self.thrust_data.append(mean_force_filtered)
        self.torque_raw_data.append(mean_torque_raw)
        self.torque_data.append(mean_torque_filtered)

        self.thrust_time_data = self.thrust_time_data[-self.max_data:]
        self.torque_time_data = self.torque_time_data[-self.max_data:]
        self.thrust_raw_data = self.thrust_raw_data[-self.max_data:]
        self.thrust_data = self.thrust_data[-self.max_data:]
        self.torque_raw_data = self.torque_raw_data[-self.max_data:]
        self.torque_data = self.torque_data[-self.max_data:]
        self.thrust_raw_plot_curve.setData(
            self.thrust_time_data,
            self.thrust_raw_data,
        )
        self.thrust_plot_curve.setData(
            self.thrust_time_data,
            self.thrust_data,
        )
        self.torque_raw_plot_curve.setData(
            self.torque_time_data,
            self.torque_raw_data,
        )
        self.torque_plot_curve.setData(
            self.torque_time_data,
            self.torque_data,
        )

        self.thrust_value.setText(
            f"Thrust: {mean_force_filtered:.4f} N\n"
            f"Raw: {mean_force_raw:.4f} N"
        )
        self.torque_value.setText(
            f"Torque: {mean_torque_filtered:.4f} N.m\n"
            f"Raw: {mean_torque_raw:.4f} N.m"
        )
        force_stats = self.force_statistics.as_dict()
        torque_stats = self.torque_statistics.as_dict()
        self.thrust_stats.setText(
            f"Avg: {force_stats['mean']:.4f}\n"
            f"Min: {force_stats['min']:.4f}\n"
            f"Max: {force_stats['max']:.4f}"
        )
        self.torque_stats.setText(
            f"Avg: {torque_stats['mean']:.4f}\n"
            f"Min: {torque_stats['min']:.4f}\n"
            f"Max: {torque_stats['max']:.4f}"
        )

        block_end_timestamp = time.time()
        for index in range(sample_count):
            sample_elapsed = (
                self.elapsed_samples + index
            ) / self.sampling_rate
            timestamp = datetime.fromtimestamp(
                block_end_timestamp
                - (sample_count - index - 1) / self.sampling_rate
            ).astimezone().isoformat(timespec="milliseconds")
            self.measurement_rows.append(
                {
                    "timestamp": timestamp,
                    "elapsed_time_s": sample_elapsed,
                    "force_voltage_raw_v": float(force_voltage[index]),
                    "torque_voltage_raw_v": float(torque_voltage[index]),
                    "force_raw_n": float(force_raw[index]),
                    "torque_raw_nm": float(torque_raw[index]),
                    "force_filtered_n": float(force_filtered[index]),
                    "torque_filtered_nm": float(torque_filtered[index]),
                    "pulse_count": self.latest_pulse_count,
                    "frequency_hz": self.latest_frequency_hz,
                    "rpm": self.latest_rpm,
                    "rpm_status": self.latest_rpm_status,
                    "acquisition_status": "OK",
                }
            )
        self.elapsed_samples += sample_count

    def clear_data(self):
        """Clear plots, exports, filter state and accumulated statistics."""
        self.revolution_time_data = []
        self.rpm_data = []
        self.revolution_time_counter = 0
        self.thrust_time_data = []
        self.thrust_data = []
        self.thrust_raw_data = []
        self.thrust_time_counter = 0
        self.torque_time_data = []
        self.torque_data = []
        self.torque_raw_data = []
        self.torque_time_counter = 0
        self.measurement_rows = []
        self.recent_force_voltage = np.empty(0, dtype=np.float64)
        self.recent_torque_voltage = np.empty(0, dtype=np.float64)
        self.elapsed_samples = 0
        self.latest_rpm = 0.0
        self.latest_pulse_count = 0
        self.latest_frequency_hz = 0.0
        self.latest_rpm_status = "NOT_STARTED"
        self.force_filter.reset()
        self.torque_filter.reset()
        self.force_statistics.reset()
        self.torque_statistics.reset()
        self.rpm_statistics.reset()
        self.revolution_plot_curve.clear()
        self.thrust_raw_plot_curve.clear()
        self.thrust_plot_curve.clear()
        self.torque_raw_plot_curve.clear()
        self.torque_plot_curve.clear()
        self.revolution_value.setText("Revolution: 0.0 rpm")
        self.revolution_stats.setText("Avg: 0\nMin: 0\nMax: 0")
        QMessageBox.information(self,"Success", "All data is cleared!")

    def offset_sensor_data(self):
        """Zero both analog channels using the latest stable window."""
        self._zero_channels(zero_force=True, zero_torque=True)

    def zero_force(self):
        """Zero only the force channel."""
        self._zero_channels(zero_force=True, zero_torque=False)

    def zero_torque(self):
        """Zero only the torque channel."""
        self._zero_channels(zero_force=False, zero_torque=True)

    def _zero_channels(self, zero_force, zero_torque):
        """Apply independent tare offsets without modifying calibration."""
        try:
            if self.motor_running and self.motor_controller is not None:
                self.stop_motor()
            required = max(1, int(self.zero_duration_s * self.sampling_rate))
            if zero_force and self.recent_force_voltage.size < required:
                raise RuntimeError(
                    f"Read data for at least {self.zero_duration_s:.1f} s "
                    "before Zero force."
                )
            if zero_torque and self.recent_torque_voltage.size < required:
                raise RuntimeError(
                    f"Read data for at least {self.zero_duration_s:.1f} s "
                    "before Zero torque."
                )
            messages = []
            if zero_force:
                force_zero_v = float(
                    np.mean(self.recent_force_voltage[-required:])
                )
                self.force_calibration = self.force_calibration.with_zero(
                    force_zero_v
                )
                messages.append(f"Force zero: {force_zero_v:.6f} V")
            if zero_torque:
                torque_zero_v = float(
                    np.mean(self.recent_torque_voltage[-required:])
                )
                self.torque_calibration = self.torque_calibration.with_zero(
                    torque_zero_v
                )
                messages.append(f"Torque zero: {torque_zero_v:.6f} V")
            self.force_filter.reset()
            self.torque_filter.reset()
            self._save_calibration()
            QMessageBox.information(
                self,
                "Zero complete",
                "\n".join(messages)
                + "\nCalibration slope/intercept were not changed.",
            )
        except Exception as e:
            QMessageBox.critical(self, "Zero error", str(e))

    def save_sensor_data(self):
        """Save measurements to CSV."""
        self._save_measurements("csv")

    def save_excel_data(self):
        """Save measurements and metadata to a multi-sheet Excel workbook."""
        self._save_measurements("xlsx")

    def _save_measurements(self, extension):
        """Save collected rows to CSV or Excel."""
        filename = Path(self.input_name_tab0.text().strip()).name
        if not filename:
            QMessageBox.warning(self, "Error", "Please enter a valid file name.")
            return
        filename = f"{Path(filename).stem}.{extension}"
        data_dir = EXPORT_DIR
        data_dir.mkdir(exist_ok=True)
        file_path = data_dir / filename
        try:
            save_raw = self.save_raw_checkbox.isChecked()
            if extension == "csv":
                save_measurements_csv(
                    file_path,
                    self.measurement_rows,
                    save_raw,
                )
            else:
                save_measurements_excel(
                    file_path,
                    self.measurement_rows,
                    save_raw,
                    self.app_config,
                    [
                        {
                            "channel": "Force",
                            "slope": self.force_calibration.slope,
                            "intercept": self.force_calibration.intercept,
                            "zero_offset_v": (
                                self.force_calibration.zero_offset_v
                            ),
                        },
                        {
                            "channel": "Torque",
                            "slope": self.torque_calibration.slope,
                            "intercept": self.torque_calibration.intercept,
                            "zero_offset_v": (
                                self.torque_calibration.zero_offset_v
                            ),
                        },
                    ],
                    [
                        {"channel": "Force", **self.force_statistics.as_dict()},
                        {"channel": "Torque", **self.torque_statistics.as_dict()},
                        {"channel": "RPM", **self.rpm_statistics.as_dict()},
                    ],
                )
            QMessageBox.information(self, "Success", f"Data saved to {file_path}")
        except Exception as e:
            LOGGER.exception("Failed to save measurement data")
            QMessageBox.critical(self, "Error", f"Failed to save data: {str(e)}")

    def closeEvent(self, event):
        """Stop motor, NI, serial and camera safely before closing."""
        try:
            if self.motor_controller is not None:
                try:
                    self.motor_controller.stop_motor()
                except Exception:
                    LOGGER.exception("Failed to send safe motor stop")
            if self.read_sensor_running or self.acquisition_thread is not None:
                self.stop_reading()
            if self.camera is not None:
                self.stop_camera()
            if self.motor_controller is not None:
                self.motor_controller.close()
                self.motor_controller = None
        finally:
            event.accept()

def main():
    _smoke_trace("main entered")
    app = QApplication(sys.argv)
    _smoke_trace("QApplication created")
    window = MainWindow()
    _smoke_trace("MainWindow created")
    if "--smoke-test" in sys.argv:
        window.acquisition_mode = "simulation"

        def finish_smoke_test():
            window.stop_reading()
            required_columns = {
                "pulse_count",
                "frequency_hz",
                "rpm",
                "rpm_status",
            }
            last_row = (
                window.measurement_rows[-1]
                if window.measurement_rows
                else {}
            )
            succeeded = (
                len(window.measurement_rows) > 0
                and window.acquisition_thread is None
                and required_columns.issubset(last_row)
                and float(last_row.get("rpm", 0.0)) > 0.0
            )
            _smoke_trace(
                f"smoke finished succeeded={succeeded} "
                f"rows={len(window.measurement_rows)}"
            )
            window.close()
            app.exit(0 if succeeded else 1)

        QTimer.singleShot(0, window.start_reading)
        QTimer.singleShot(700, finish_smoke_test)
        return app.exec()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
