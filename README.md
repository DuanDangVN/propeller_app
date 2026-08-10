# propeller_app

Ứng dụng desktop đo lực, mô-men và RPM, đồng thời điều khiển ESC cho bệ thử
cánh quạt. Bản đang phát triển nằm trên branch `NTA-ver`.

## Cấu hình phần cứng

- Lực: tín hiệu JSY-S60 vào NI USB-6001 AI0, mass tín hiệu vào AI GND, RSE.
- Mô-men: tín hiệu JSY-S60 vào NI USB-6001 AI1, mass tín hiệu vào AI GND, RSE.
- RPM: cảm biến 2 xung/vòng, OUT vào NI P2.0/PFI0, bộ đếm `ctr0`.
- Arduino: chỉ điều khiển ESC qua D11 và nhận lệnh qua USB serial; cổng mặc
  định là `COM10` nếu ứng dụng không tự nhận diện được Arduino Uno.
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

CSV và Excel chỉ xuất thời gian cùng ba đại lượng chính đã xử lý:

```text
Time Data (s), Thrust (N), Torque (N.m), RPM
```

File Excel chỉ có một sheet `Measurements`; dữ liệu thô, cấu hình và thống kê
vẫn được dùng trong ứng dụng nhưng không đưa vào file xuất.

Khi chạy bản EXE, cả CSV và Excel được lưu trong thư mục `Export data` nằm ngay
cạnh file EXE. Ứng dụng tự tạo thư mục này nếu chưa có. Ví dụ:

```text
NTA Propeller/
├── PropellerApp.exe
└── Export data/
    ├── test.csv
    └── test.xlsx
```

## Cấu trúc module

```text
main.py                       Điểm khởi động ứng dụng
app_runtime.py                Đường dẫn, logging và cấu hình runtime
ui/main_window.py             Giao diện và điều phối sự kiện
ui/charts.py                  Cấu hình biểu đồ
devices/ni_reader.py          Đọc NI USB-6001 và bộ đếm RPM
devices/motor_controller.py   Điều khiển Arduino/ESC
devices/simulation_reader.py  Nguồn dữ liệu mô phỏng
acquisition_worker.py         Worker đọc dữ liệu nền
processing/                   RPM, calibration, lọc và thống kê
storage/exporters.py          Xuất CSV/Excel bốn cột chính
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
5. Trong `NI RPM counter`, chọn `ctr0`, `PFI0` và giữ `Pulses per revolution = 2`.
6. Bấm `Apply acquisition settings`.
7. Bấm `Connect Arduino` nếu cần điều khiển motor.
8. Bấm `Read data` để đọc lực, mô-men và RPM từ NI.

Không cần kết nối Arduino để đọc NI; chỉ cần Arduino khi điều khiển ESC.

### Calibration

1. Chọn `Thrust` hoặc `Torque` trong `Calibration Task`.
2. Để cảm biến không tải, nhập `0` gram và bấm `Get Voltage`.
3. Đặt tải chuẩn, ví dụ tải 2 kg thì nhập `2000` gram, chờ ổn định rồi bấm
   `Get Voltage` lần nữa.
4. Lặp lại với ít nhất một tải khác nếu có, sau đó bấm
   `Linear approximate` và `Apply Calib Value`.
5. Bỏ tải và thực hiện `Zero all` trước khi đo.

`Get Voltage` tự chụp một cửa sổ analog hữu hạn khi `Read data` đang tắt. Nếu
`Read data` đang chạy, nút này dùng 0,5 giây dữ liệu mới nhất. Nếu tải thay đổi
nhưng điện áp gần như không đổi, điểm calibration sẽ không được lưu và ứng dụng
sẽ yêu cầu kiểm tra kênh, dây JSY-S60 và cực AI+/AI−.

Khi đổi từ calibration `Thrust` sang `Torque` (hoặc ngược lại), ứng dụng tự
xóa các điểm đo và kết quả linear fit tạm thời để không trộn dữ liệu hai cảm
biến. Hệ số calibration đã Apply vẫn được giữ nguyên.

Nút `View applied calibration` hiển thị hệ số A/B, điện áp Zero và công thức
Thrust/Torque mà ứng dụng đang thực sự sử dụng.

## Kiểm tra

```powershell
python -m pytest -q tests
python -m compileall -q main.py app_runtime.py devices processing storage ui
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
