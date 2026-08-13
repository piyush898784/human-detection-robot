# 06. Detailed Component Descriptions

This document details the functional specifications, working principles, power parameters, and design justifications for each component used in the robot.

---

## 1. Core Computing Nodes

### 1.1 ESP32-CAM (AI Thinker Module)
* **Purpose**: Captures and broadcasts the robot's real-time video stream over Wi-Fi.
* **Working Principle**: Captures frames from an OV2640 camera sensor, compresses them into MJPEG format, and hosts an HTTP streaming server.
* **Input Voltage**: $5.0\text{ VDC}$ via VCC pin.
* **Output**: MJPEG video stream ($800 \times 600$ resolution at $\approx 25\text{ FPS}$).
* **Communication Interface**: Wi-Fi ($802.11\text{ b/g/n}$ TCP/IP).
* **Power Consumption**: $\approx 180\text{ mA}$ (Idle), $\approx 310\text{ mA}$ (Streaming with active Wi-Fi).
* **Reason for Selection**: Low-cost, dedicated camera streaming platform that offloads video capture overhead from the main actuator controller.

### 1.2 LILYGO LoRa32 V3
* **Purpose**: Coordinates motor speed, reads sensors, drives the status OLED, and transmits long-range telemetry.
* **Working Principle**: Built on the dual-core ESP32-S3 microcontroller, it uses custom firmware to process WebSocket packets, manage real-time interrupts for encoders, compute ultrasonic ping durations, and drive the onboard SX1262 LoRa module.
* **Input Voltage**: $5.0\text{ VDC}$ via USB-C or VBUS pin.
* **Output**: SSD1306 display drive, SPI LoRa outputs, PWM motor driver signals.
* **Communication Interface**: I2C (OLED and IMU), SPI (SX1262 LoRa), USB-UART (Serial debug), Wi-Fi WebSockets (CMD_VEL receiver).
* **Power Consumption**: $\approx 120\text{ mA}$ (Idle), up to $\approx 280\text{ mA}$ during LoRa transmission at $+22\text{ dBm}$.
* **Reason for Selection**: Combines an ESP32-S3 microcontroller, LoRa transceiver, and SSD1306 OLED display on a single development board.

### 1.3 High-Level Compute Laptop (Host Node)
* **Purpose**: Runs deep learning networks, voice processing models, EKF sensor fusion, and coordinates ROS 2 nodes.
* **Working Principle**: Consumes the video feed from the ESP32-CAM, processes YOLOv11 person bounding boxes, extracts facial features using InsightFace, and applies ByteTrack tracking. It processes spoken keywords via Whisper and outputs `/cmd_vel` vectors.
* **Input Voltage**: Laptop battery / $19.5\text{ VDC}$ charger.
* **Output**: WebSocket motion command packets to the LILYGO controller.
* **Communication Interface**: Wi-Fi ($802.11\text{ ax}$ or $802.11\text{ ac}$).
* **Power Consumption**: $\approx 30\text{ W} - 90\text{ W}$ depending on CPU/GPU load.
* **Reason for Selection**: Standard developer laptop running Ubuntu 24.04 LTS provides the necessary hardware acceleration (CPU/GPU) to run YOLOv11 and InsightFace in real time without latency.

---

## 2. Sensors

### 2.1 BNO055 9-Axis Smart IMU
* **Purpose**: Measures absolute orientation, heading angles, and angular velocity.
* **Working Principle**: Integrates a 3-axis accelerometer, a 3-axis gyroscope, and a 3-axis magnetometer. An onboard 32-bit Cortex-M0 processor runs proprietary sensor fusion algorithms (Extended Kalman Filter) to output Euler angles and quaternions directly.
* **Input Voltage**: $3.3\text{ VDC}$.
* **Output**: Relative Yaw, Pitch, Roll angles, and linear acceleration vectors.
* **Communication Interface**: I2C (address $0x28$).
* **Power Consumption**: $\approx 12.3\text{ mA}$.
* **Reason for Selection**: The onboard sensor fusion processor offloads raw calibration and EKF calculations from the LILYGO controller, providing drift-free yaw angles.

### 2.2 HC-SR04 Ultrasonic Sensors (x2)
* **Purpose**: Measures front left and front right obstacle distances.
* **Working Principle**: Emits an ultrasonic burst ($40\text{ kHz}$) when triggered. It measures the time elapsed ($t$) until the echo return is detected. Distance is computed using the speed of sound: $D = \frac{t \times 0.0343}{2}\text{ cm}$.
* **Input Voltage**: $5.0\text{ VDC}$.
* **Output**: High-level pulse width proportional to object distance.
* **Communication Interface**: Digital GPIO Trigger & Echo.
* **Power Consumption**: $\approx 15\text{ mA}$ (active pinging).
* **Reason for Selection**: Simple, low-cost distance sensing that is immune to ambient lighting conditions.

### 2.3 Hall Effect Quadrature Encoders (x6)
* **Purpose**: Monitors wheel rotation speeds and directions.
* **Working Principle**: Mounted on the rear shafts of the DC motors. A magnetic disc rotates past two Hall-effect sensors, generating two square waves out of phase by $90^\circ$ (quadrature). The pulse frequency indicates speed, and the phase order determines direction.
* **Input Voltage**: $5.0\text{ VDC}$.
* **Output**: Dual-channel digital square waves.
* **Communication Interface**: Digital GPIO with External Interrupts.
* **Power Consumption**: $\approx 10\text{ mA}$ per encoder.
* **Reason for Selection**: High-resolution feedback on wheel speeds, which is essential for differential-drive odometry calculations.

---

## 3. Power & Actuation

### 3.1 TB6612FNG Dual H-Bridge Motor Drivers (x2)
* **Purpose**: Amplifies low-current control signals from the LILYGO controller to drive the high-current DC motors.
* **Working Principle**: Uses MOSFET-based H-bridges to control the direction and speed of two independent DC motors using PWM signals.
* **Input Voltage**: $V_{cc} = 2.7\text{V} - 5.5\text{V}$ (Logic), $V_{m} = 15\text{V}$ max (Motor).
* **Output**: Up to $1.2\text{ A}$ continuous per channel ($3.2\text{ A}$ peak).
* **Communication Interface**: GPIO direction inputs, PWM speed inputs.
* **Power Consumption**: Negligible logic draw ($\approx 1.5\text{ mA}$).
* **Reason for Selection**: Higher efficiency and lower heat dissipation than the older L298N driver due to its MOSFET-based design.

### 3.2 12V DC Metal Gear Motors (x6)
* **Purpose**: Drives the robot wheels.
* **Working Principle**: Electromechanical motors paired with metal reduction gearboxes ($1:30$ ratio) to convert high-speed rotational energy into high-torque motion.
* **Input Voltage**: $12.0\text{ VDC}$ nominal.
* **Output**: Rotational torque (rated speed $\approx 200\text{ RPM}$).
* **Power Consumption**: $\approx 120\text{ mA}$ (no load), up to $\approx 1.6\text{ A}$ (stall current per motor).
* **Reason for Selection**: Metal gears offer high durability, and the 6-wheel configuration provides excellent stability and traction across indoor and outdoor surfaces.
