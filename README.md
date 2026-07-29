# propeller_app

Ứng dụng desktop đo lực, mô-men và RPM, đồng thời điều khiển ESC cho bệ thử
cánh quạt. Bản đang phát triển nằm trên branch local
`ni-rpm-counter-local` và không được push lên GitHub.

## Cấu hình phần cứng

- Lực: NI USB-6001 AI2 (+) / AI6 (−), differential.
- Mô-men: NI USB-6001 AI1 (+) / AI5 (−), differential.
- RPM: cảm biến OUT vào NI P2.0/PFI0, bộ đếm `ctr0`.
- Arduino: chỉ điều khiển ESC qua D11 và nhận lệnh qua USB serial.
- Cảm biến RPM có thể dùng +5 V và D GND của NI nếu dòng tiêu thụ phù hợp.

Sơ đồ chi tiết: [WIRING_GUIDE_VI.md](WIRING_GUIDE_VI.md).

Sketch Arduino:

```text
arduino/propeller_controller/propeller_controller.ino
```

## Thu thập và xử lý

- Hai kênh analog được đọc liên tục theo block trong `QThread`.
- Counter NI được đọc cùng worker; GUI không trực tiếp gọi NI-DAQmx.
- RPM dùng số cạnh tăng thêm, số xung mỗi vòng, cửa sổ tính và timeout không
  có xung.
- Simulation tạo lực/mô-men có nhiễu và RPM thay đổi theo thời gian.
- Bộ lọc analog: không lọc, moving average, median và Butterworth low-pass.
- Có đường raw/filtered, Zero độc lập, thống kê và xuất CSV/Excel.

Mỗi dòng xuất có:

```text
timestamp, elapsed_time_s,
force_voltage_raw_v, torque_voltage_raw_v,
force_raw_n, torque_raw_nm,
force_filtered_n, torque_filtered_nm,
pulse_count, frequency_hz, rpm, rpm_status, acquisition_status
```

## Cài đặt

Khuyến nghị Python 3.11 hoặc 3.12 trên Windows 10/11:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

Máy chạy chế độ Hardware NI phải cài NI-DAQmx. Simulation không cần cắm NI.

## Sử dụng

1. Nạp sketch mới vào Arduino Uno.
2. Đấu cảm biến RPM vào NI +5 V, D GND và P2.0/PFI0.
3. Mở ứng dụng, vào `Settings`.
4. Chọn `Hardware NI`, thiết bị NI và cổng COM Arduino.
5. Trong `NI RPM counter`, chọn `ctr0`, `PFI0` và nhập đúng số xung mỗi vòng.
6. Bấm `Apply acquisition settings`.
7. Bấm `Connect Arduino` nếu cần điều khiển motor.
8. Bấm `Read data` để đọc lực, mô-men và RPM từ NI.

Không cần kết nối Arduino để đọc NI; chỉ cần Arduino khi điều khiển ESC.

## Kiểm tra

```powershell
python -m pytest -q tests
python -m py_compile main.py acquisition_worker.py processing\rpm.py
python main.py --smoke-test
```

## Đóng gói EXE

```powershell
python -m PyInstaller --noconfirm --clean propeller_app.spec
```

File một khối:

```text
dist/PropellerApp.exe
```

Máy đích vẫn phải cài NI-DAQmx để sử dụng Hardware NI.
