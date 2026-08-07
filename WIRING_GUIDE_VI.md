# Sơ đồ đấu dây propeller_app

## 1. NI USB-6001

| Đại lượng | Đầu dương | Đầu âm | Chế độ |
|---|---|---|---|
| Lực | AI0 | AI GND | RSE |
| Mô-men | AI1 | AI GND | RSE |
| RPM | P2.0/PFI0 | D GND | Counter `ctr0`, cạnh lên |

Với hai kênh analog, chương trình khai báo `ai0` và `ai1` với
`TerminalConfiguration.RSE`. Mass tín hiệu analog của cả hai JSY-S60 phải nối
về `AI GND` của NI USB-6001. Không dùng AI5/AI6 làm đầu âm trong cấu hình này.

### Dãy 16 lỗ digital

Giữ NI theo chiều chữ đọc thẳng, dãy lỗ nằm phía dưới và `P0.0` ngoài cùng
bên phải. Đếm từ trái sang phải:

| Lỗ đếm từ trái | Tên NI |
|---:|---|
| 1 | D GND |
| 2 | +5 V |
| 3 | D GND |
| 4 | P2.0/PFI0 |
| 5 | P1.3 |
| 6 | P1.2 |
| 7 | P1.1/PFI1 |
| 8 | P1.0 |
| 9–16 | P0.7 đến P0.0 |

Đấu cảm biến RPM:

| Chân cảm biến | Lỗ NI |
|---|---|
| VCC/+ | Lỗ 2, +5 V |
| GND/− | Lỗ 1 hoặc 3, D GND |
| OUT/Signal | Lỗ 4, P2.0/PFI0 |

Nguồn +5 V của USB-6001 chỉ dùng cho cảm biến nhỏ có dòng tiêu thụ phù hợp.
Đo xác nhận OUT nằm trong 0–5 V trước khi nối PFI0.

Nếu cảm biến có đầu ra open-collector và OUT không lên mức cao, cần xác nhận
datasheet hoặc đo bằng oscilloscope trước khi thêm điện trở kéo lên.

## 2. Arduino Uno và Hobbywing

Arduino không đọc RPM trong phiên bản này. Arduino chỉ nhận lệnh công suất từ
ứng dụng qua USB serial và điều khiển ESC:

| Chức năng | Chân Arduino |
|---|---|
| Tín hiệu PWM ESC | D11 |
| Mass tín hiệu ESC | GND |

- D2 để trống.
- AREF để trống.
- Không nối PFI0 của NI với D11.
- Khi Arduino đang được cấp nguồn qua USB, không nối thêm nguồn BEC 5 V của
  ESC vào chân 5 V Arduino nếu chưa xác định rõ cấu hình nguồn.

Sketch cần nạp:

```text
arduino/propeller_controller/propeller_controller.ino
```

Thiết lập Arduino IDE:

```text
Board: Arduino Uno
Baud rate: 9600
ESC signal: D11
```

## 3. Cấu hình phần mềm

Trong trang `Settings`, nhóm `NI RPM counter`:

```text
Counter: ctr0
Pulse terminal: PFI0
Pulses per revolution: 2 (cảm biến thực tế phát 2 xung/vòng)
Calculation window: 0.10 s
No-pulse timeout: 1.50 s
```

RPM được tính theo:

```text
RPM = frequency_hz × 60 / pulses_per_revolution
```

Ứng dụng lưu thêm `pulse_count`, `frequency_hz`, `rpm` và `rpm_status` trong
CSV/Excel.

## 4. An toàn

- Tháo cánh quạt và ngắt pin động lực trước khi thay dây hoặc nạp Arduino.
- Không đưa nguồn pin ESC, dây pha motor hoặc 24 V vào Arduino/NI.
- Nếu Arduino nóng rõ rệt, ngắt nguồn ngay và kiểm tra chập 5 V–GND hoặc hai
  nguồn 5 V đang đấu ngược vào nhau. Việc đổi code không sửa được lỗi đấu nguồn.
- Dây màu không đủ để xác định VCC/GND/OUT; phải dựa vào ký hiệu hoặc phép đo.
