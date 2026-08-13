# 08. Bill of Materials (BOM)

This document contains the engineering Bill of Materials, estimated component costs in Indian Rupees (INR), and verified vendor suggestions for the project components.

---

## 1. System Bill of Materials

| Component Name | Description / Specifications | Qty | Unit Price (INR) | Total Price (INR) | Primary Purpose | Suggested Vendor |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **ESP32-CAM AI Thinker** | ESP32-S module + OV2640 camera board | 1 | 650 | 650 | Vision capture and video streaming over Wi-Fi | Robokits / Robomart |
| **FTDI USB-UART Adapter** | USB-to-TTL programmer with jumper select ($3.3\text{V} / 5\text{V}$) | 1 | 250 | 250 | Programming and debugging the ESP32-CAM | Amazon / Quartz Components |
| **LILYGO LoRa32 V3** | ESP32-S3 core + SX1262 LoRa + SSD1306 OLED | 1 | 2,800 | 2,800 | Actuator control, sensor polling, and LoRa transmission | Robu.in / Lilygo Store |
| **6WD Metal Chassis** | Heavy-duty steel/aluminum plate dual-deck chassis | 1 | 3,500 | 3,500 | Main robot body and mechanical frame assembly | Robu.in / Robomart |
| **12V DC Gear Motors** | Metal gearboxes with integrated quadrature encoders | 6 | 1,200 | 7,200 | Wheel drive actuation and velocity feedback | Robu.in / Robokits |
| **TB6612FNG Motor Drivers** | Dual H-bridge driver modules (MOSFET-based) | 2 | 250 | 500 | Amplifying actuator currents (up to 1.2A continuous) | Robu.in / Quartz Components |
| **HC-SR04 Sensors** | Ultrasonic distance transmitters/receivers ($40\text{ kHz}$) | 2 | 90 | 180 | Front left and front right obstacle detection | Robu.in / Amazon |
| **BNO055 Smart IMU** | 9-axis sensor + integrated ARM Cortex fusion processor | 1 | 1,500 | 1,500 | Drif-free orientation and absolute heading | Robu.in / Quartz Components |
| **Voltage Sensor Module** | Resistor voltage divider ($5:1$ step-down conversion) | 1 | 80 | 80 | Monitors 3S battery charge levels | Robu.in |
| **18650 Li-ion Cells** | 3.7V 2600mAh high-discharge rate batteries | 3 | 300 | 900 | Main system power source | Robu.in / Local Store |
| **3S 20A BMS Board** | Lithium protection board (Overcharge, short-circuit protection) | 1 | 120 | 120 | Balancing cells and battery safety | Robu.in / Amazon |
| **LM2596 Buck Converter** | DC-DC step-down buck module ($3.0\text{A}$ max output) | 1 | 100 | 100 | Regulates 12V battery power down to 5V | Robu.in / Amazon |
| **Mechanical Accessories** | Jumper wires, spacers, heat-shrink tubes, fasteners, ties | 1 | 600 | 600 | Electrical routing and hardware structural assembly | Local Store |
| **User Indicators** | Active buzzer, RGB status LED, toggle switch, power jack | 1 | 220 | 220 | System warnings, charging port, and power control | Local Store |
| **Laptop Host Node** | Core i5/i7 processor running Ubuntu 24.04 (User-provided) | 1 | - | - | Runs ROS 2 Jazzy, YOLOv11, and InsightFace | Owner |

### Total Project Cost Estimation: **₹18,500 INR**
*(Excludes developer laptop/high-level processing node).*
