# 02. System & Hardware Architecture

This document presents the high-level physical and logical organization of the Autonomous Human-Following Robot, detailing communication protocols and physical electrical interconnections.

---

## 1. Logical System Architecture

The robot comprises three computing layers interacting over standard communication protocols:
1. **Perception (Vision Node)**: Runs on the ESP32-CAM to capture and transmit high-definition MJPEG video streams.
2. **AI Reasoning (ROS 2 Host)**: Computes vision models, speaker intent, EKF localization, and publishes velocity vectors.
3. **Execution & Telemetry (Embedded Controller)**: Decodes movement vectors, regulates wheel speeds, reads sensors, and sends long-range diagnostics.

```mermaid
graph TD
    %% Compute Nodes
    subgraph Layer 1: Vision Node
        CAM[ESP32-CAM AI Thinker]
    end

    subgraph Layer 2: AI Processing Node
        subgraph Laptop - Ubuntu 24.04 & ROS 2 Jazzy
            YOLO[YOLOv11 Detector]
            FR[InsightFace Recognition]
            BT[ByteTrack Tracker]
            MP[Motion Planner Node]
        end
    end

    subgraph Layer 3: Actuation & Embedded Control
        subgraph LILYGO LoRa32 V3 Board
            ESP[ESP32 S3 Core]
            SX[SX1262 LoRa Chip]
            OLED[SSD1306 OLED Display]
        end
        
        Drivers[2x TB6612FNG Dual Drivers]
        Motors[6x DC Metal Gear Motors]
        Enc[6x Wheel Encoders]
        IMU[BNO055 9-Axis IMU]
        US[2x HC-SR04 Ultrasonic Sensors]
        Bat[Battery Voltage Sensor]
    end

    %% Communication Interconnections
    CAM -->|MJPEG Video Stream over Wi-Fi TCP/IP| YOLO
    YOLO -->|Bounding Box & Frames| FR
    FR -->|Face Encodings & Labels| BT
    BT -->|Target State Vectors| MP
    
    MP -->|CMD_VEL JSON over Wi-Fi WebSockets| ESP
    
    ESP -->|Dual PWM & Direction Signals| Drivers
    Drivers -->|12V H-Bridge Power Rails| Motors
    
    Motors -->|Physical Rotation| Enc
    Enc -->|Hall Effect Pulse Interrupts| ESP
    
    IMU -->|Raw Acceleration, Gyro, Mag via I2C| ESP
    US -->|Trigger & Echo Pulses| ESP
    Bat -->|Analog Voltage Level via ADC| ESP
    
    ESP -->|I2C Data Bus| OLED
    ESP -->|SPI Data Bus| SX
    
    SX -->|SX1262 LoRa FSK Telemetry Packet| Gate[Ground Telemetry Station]
```

---

## 2. Hardware Architecture Interconnections

The block diagram below describes physical hardware connections, power distribution pathways, control channels, and communication interfaces.

```mermaid
graph TD
    %% Power Source
    subgraph Power Supply
        Pack[3S 18650 Battery Pack 11.1V - 12.6V]
        BMS[3S Lithium Battery Protection Board]
        Switch{Main Toggle Switch}
        Reg[LM2596 Buck Regulator]
    end

    %% Actuation Layer
    subgraph Actuation
        TB1[TB6612FNG Driver A]
        TB2[TB6612FNG Driver B]
        MotorsL[Left Side Motors 3x]
        MotorsR[Right Side Motors 3x]
    end

    %% Controllers
    subgraph Processing Nodes
        LILY[LILYGO LoRa32 V3 Embedded Controller]
        ECAM[ESP32-CAM Vision Module]
    end

    %% Sensors
    subgraph Sensor Suite
        BNO[BNO055 9-Axis IMU]
        SR1[Left Ultrasonic Sensor]
        SR2[Right Ultrasonic Sensor]
        EncL[Left Wheel Encoder]
        EncR[Right Wheel Encoder]
        VSen[Battery Voltage Divider]
    end

    %% Wiring Paths - Power
    Pack ===|Heavy Gauge Wire| BMS
    BMS ===|Protected Power| Switch
    Switch ===|11.1V - 12.6V V_Motor| TB1
    Switch ===|11.1V - 12.6V V_Motor| TB2
    Switch ===|Raw Battery Input| Reg
    Reg ===|Regulated 5V Bus| LILY
    Reg ===|Regulated 5V Bus| ECAM
    Reg ===|Regulated 5V Bus| BNO
    Reg ===|Regulated 5V Bus| SR1
    Reg ===|Regulated 5V Bus| SR2
    
    %% Wiring Paths - Ground
    GND[Common Ground Rail]
    BMS --- GND
    Reg --- GND
    LILY --- GND
    ECAM --- GND
    TB1 --- GND
    TB2 --- GND
    BNO --- GND
    SR1 --- GND
    SR2 --- GND
    EncL --- GND
    EncR --- GND
    VSen --- GND

    %% Wiring Paths - Control & Logic
    LILY -->|PWM & GPIO Control| TB1
    LILY -->|PWM & GPIO Control| TB2
    TB1 -->|High-Current Output| MotorsL
    TB2 -->|High-Current Output| MotorsR
    
    %% Sensors to Controller
    BNO -->|I2C Bus: SDA, SCL| LILY
    SR1 -->|GPIO Trigger & Echo| LILY
    SR2 -->|GPIO Trigger & Echo| LILY
    EncL -->|GPIO Ext Interrupts| LILY
    EncR -->|GPIO Ext Interrupts| LILY
    Switch -->|Resistor Divider| VSen -->|Analog Input ADC| LILY
```

---

## 3. Communication Channel Interface Specs

* **Vision Node $\rightarrow$ AI Laptop (Wi-Fi 802.11 b/g/n)**: Establishes an HTTP server on the ESP32-CAM. The laptop initiates a persistent TCP client connection to fetch an MJPEG stream at `http://<esp32_ip>:81/stream`.
* **AI Laptop $\rightarrow$ Embedded Controller (Wi-Fi WebSockets)**: The LILYGO runs a WebSocket Server. The ROS 2 Laptop connects as a client and streams JSON packets containing `x_vel`, `yaw_vel`, and `mode` at a rate of 20Hz.
* **Embedded Controller $\rightarrow$ Actuators (TB6612FNG - Hardware PWM)**: Drives two motor channels using differential phase configurations and PWM speed triggers.
* **Sensors $\rightarrow$ Embedded Controller**:
  * **BNO055 IMU**: Fast-mode I2C ($400\text{ kHz}$) using hardware registers.
  * **Ultrasonic HC-SR04**: Digital pulse capture.
  * **Encoders**: Dual-channel quadrature interrupt pins to measure directional wheel rotation.
  * **OLED**: SSD1306 driven over shared I2C bus ($400\text{ kHz}$).
  * **LoRa**: Transmits RF telemetry packets using the SX1262 LoRa transceiver over SPI at $433\text{ MHz}$ / $868\text{ MHz}$.
