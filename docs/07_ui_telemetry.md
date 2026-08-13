# 07. User Interface Design & Telemetry Protocols

This document details the visual layouts for the SSD1306 OLED onboard display and the binary structure of the SX1262 LoRa telemetry packet.

---

## 1. SSD1306 OLED Display Interface Layout ($128 \times 64$ Pixels)

The OLED screen is split into a status bar (top), active tracking/sensor telemetry fields (middle), and diagnostic readouts (bottom).

```text
+-------------------------------------------------+
| BAT: 12.2V [85%]  | WiFi: CON  | LoRa: TX [433] |  <- Line 1: Header / Status Bar
+-------------------------------------------------+
|                                                 |
|  MODE: AUTO_FOLLOW   [HOST: LOCK-ON]            |  <- Line 2-3: Core State and Target status
|  TARGET DISTANCE: 1.45 m                        |
|                                                 |
|  IMU HEADING: 184.5 deg                         |  <- Line 4-5: Sensor Readings
|  US RANGE  L: 120 cm  | R: 115 cm               |
|                                                 |
|  MOTORS   L: PWM 150  | R: PWM 152              |  <- Line 6: Actuation Speed Outputs
+-------------------------------------------------+
| STATUS: OK | SAFE FOLLOWING ZONE                |  <- Line 7: Footer Messages / Warnings
+-------------------------------------------------+
```

### Visual State Indicators
* **WiFi Status**:
  * `DIS` : Disconnected.
  * `CON` : Connected.
  * `AP`  : Access Point mode active.
* **Host Status**:
  * `LOST`    : Scanning for human face.
  * `UNKNOWN` : Person detected, but similarity threshold failed.
  * `LOCK-ON` : Registered host face verified, active tracking engaged.
* **Status Warnings**:
  * `STOP! OBSTACLE` : Ultrasonic sensor path blocked (Buzzer sounds).
  * `LOW BATTERY`    : Battery drop below $9.9\text{V}$ (RGB LED flashes Red).

---

## 2. LoRa Binary Telemetry Packet Format

To minimize transmission latency and maximize ranges, the robot utilizes a raw binary packet payload ($24\text{ bytes}$ total) instead of verbose text strings.

### Telemetry Frame Structure

| Byte Offset | Data Field | Data Type | Range / Format | Description |
| :--- | :--- | :--- | :--- | :--- |
| **0 - 3** | `Battery_Voltage` | `float32` | $0.0 - 15.0\text{V}$ | Raw battery voltage |
| **4 - 7** | `Heading_Yaw` | `float32` | $-180.0^\circ$ to $+180.0^\circ$ | Fused orientation heading from IMU |
| **8 - 11** | `Encoder_Ticks_L` | `int32` | $-2^{31}$ to $+2^{31}-1$ | Cumulative encoder ticks for left motor group |
| **12 - 15** | `Encoder_Ticks_R` | `int32` | $-2^{31}$ to $+2^{31}-1$ | Cumulative encoder ticks for right motor group |
| **16 - 17** | `US_Dist_Left` | `uint16` | $2\text{ cm} - 400\text{ cm}$ | Distance reading from left ultrasonic sensor |
| **18 - 19** | `US_Dist_Right` | `uint16` | $2\text{ cm} - 400\text{ cm}$ | Distance reading from right ultrasonic sensor |
| **20** | `Host_State` | `uint8` | Enums: `0` (Lost), `1` (Searching), `2` (Lock-On) | Vision tracking state |
| **21** | `Robot_Mode` | `uint8` | Enums: `0` (Idle), `1` (Auto-Follow), `2` (Voice-Command), `3` (Manual) | Actuation operation mode |
| **22** | `Internal_Temp` | `int8` | $-40^\circ\text{C}$ to $+125^\circ\text{C}$ | Embedded CPU temperature |
| **23** | `Error_Flags` | `uint8` | Bitmask (see below) | Diagnostic error states |

### Error Flags Bitmask Specifications (Byte 23)

| Bit Number | Error Name | Condition | Safety Action |
| :--- | :--- | :--- | :--- |
| **Bit 0** | `LOW_BATTERY` | Voltage drops below $9.9\text{V}$ | Sound buzzer, flash RGB Red |
| **Bit 1** | `IMU_LOST` | I2C communication timeout with BNO055 | Fallback to raw encoder steering, publish error |
| **Bit 2** | `WIFI_LOST` | TCP/WebSocket disconnect exceeding 2.0s | Stop motors immediately (Failsafe) |
| **Bit 3** | `ULTRASONIC_ERROR`| Ultrasonic sensor sensor failure | Engage slow-mode, avoid forward motion |
| **Bit 4** | `STALL_DETECTED` | Motors driving but encoders registering 0 | Cut motor power to avoid overheating |
| **Bit 5 - 7** | `RESERVED` | N/A | Reserved for future expansion |
