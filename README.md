# Autonomous Human-Following and Instruction-Following Robot

[![ROS 2](https://img.shields.io/badge/ROS2-Jazzy-blue.svg)](https://docs.ros.org/en/jazzy/)
[![Ubuntu](https://img.shields.io/badge/Ubuntu-24.04-orange.svg)](https://ubuntu.com/)
[![LoRa](https://img.shields.io/badge/LoRa-SX1262-red.svg)](https://www.semtech.com/products/wireless-rf/lora-core/sx1262)
[![YOLOv11](https://img.shields.io/badge/Vision-YOLOv11-green.svg)](https://github.com/ultralytics/ultralytics)

A professional, industry-grade final year engineering project. This system implements an autonomous, six-wheeled mobile robot that identifies, tracks, and follows a registered host using computer vision, while ignoring other people and avoiding obstacles in its path. It supports voice-command navigation, displays status parameters on an onboard SSD1306 OLED screen, publishes sensor data to a ROS 2 workspace over Wi-Fi, and transmits long-range telemetry over LoRa.

---

## 📂 Documentation Directory

For deep-dive reviews of individual sub-systems, refer to the following engineering documents inside the [docs/](file:///docs) directory:

1. **[01. Project Overview](file:///docs/01_project_overview.md)**: Introduction, problem statement, objectives, applications, and future scope.
2. **[02. System & Hardware Architecture](file:///docs/02_system_architecture.md)**: Logical system layers, communication protocols, and hardware interconnection block diagrams.
3. **[03. Software Architecture & ROS 2 Graph](file:///docs/03_software_architecture.md)**: Details of ROS 2 nodes, published/subscribed topics, custom messages, services, and action definitions.
4. **[04. Workflows & Control Algorithms](file:///docs/04_workflows_algorithms.md)**: Flowcharts for robot startup, host tracking, InsightFace face recognition, YOLOv11 object detection, obstacle overrides, and EKF sensor fusion navigation.
5. **[05. Electrical Schematic & Wiring Architecture](file:///docs/05_electrical_wiring.md)**: Physical schematic layouts, colored wiring guides, power distribution trees, and GPIO pin mapping tables.
6. **[06. Detailed Component Descriptions](file:///docs/06_component_description.md)**: Purpose, working principles, voltage/power levels, and design selections for all components.
7. **[07. User Interface Design & Telemetry](file:///docs/07_ui_telemetry.md)**: OLED SSD1306 screen interface layouts and SX1262 LoRa binary packet offset specifications.
8. **[08. Bill of Materials](file:///docs/08_bill_of_materials.md)**: Quantities, estimated component pricing in Indian Rupees (INR), and suggested local vendors.
9. **[09. Engineering Design Notes](file:///docs/09_design_notes.md)**: Trade-off analyses and design rationales for our hardware and software selections.

---

## 🛠️ Complete System Architecture

The robot splits workloads across three physical processing layers connected via Wi-Fi TCP/IP, WebSockets, and SPI/I2C buses:

```mermaid
graph TD
    %% Compute Nodes
    subgraph Layer 1: Vision (ESP32-CAM)
        CAM[ESP32-CAM AI Thinker]
    end

    subgraph Layer 2: AI Processing (Laptop - ROS 2 Jazzy)
        YOLO[YOLOv11 BBox Extraction]
        FR[InsightFace Host Recognition]
        MP[Motion Planner & PID Control]
    end

    subgraph Layer 3: Actuation (LILYGO LoRa32)
        LILY[LILYGO LoRa32 Controller]
        Driver[2x TB6612FNG Drivers]
        Motors[6x DC Metal Gear Motors]
        OLED[SSD1306 OLED Display]
        LoRa[SX1262 Transceiver]
    end

    %% Communication
    CAM -->|MJPEG Stream over Wi-Fi| YOLO
    YOLO --> FR
    FR -->|State Error| MP
    MP -->|x_vel & yaw_vel JSON over WebSocket| LILY
    
    LILY -->|PWM Controls| Driver
    Driver --> Motors
    LILY -->|I2C| OLED
    LILY -->|SPI| LoRa
    
    LoRa -->|FSK Packet Telemetry| Base[LoRa Telemetry Base Station]
```

---

## 📂 Repository Folder Structure

```text
face-detection-project/
│
├── docs/                             # Engineering Documentation
│   ├── 01_project_overview.md        # Overview & Objectives
│   ├── 02_system_architecture.md      # Block Diagrams
│   ├── 03_software_architecture.md    # ROS 2 Graph & Topic specs
│   ├── 04_workflows_algorithms.md     # Flowcharts & Math Equations
│   ├── 05_electrical_wiring.md        # Electrical Schematic & GPIO Table
│   ├── 06_component_description.md    # Part-by-part specs & principles
│   ├── 07_ui_telemetry.md             # OLED Interface & LoRa Packet frame
│   ├── 08_bill_of_materials.md        # Detailed project BOM (INR)
│   └── 09_design_notes.md             # Design trade-offs & rationales
│
├── firmware/                         # Microcontroller Arduino IDE Projects
│   ├── esp32_cam_stream/
│   │   └── esp32_cam_stream.ino      # ESP32-CAM HTTP Video Streaming code
│   └── lilygo_lora32_controller/
│       └── lilygo_lora32_controller.ino # LILYGO main actuator, sensor, and LoRa code
│
├── ros2_ws/                          # ROS 2 Jazzy Workspace
│   └── src/
│       ├── robot_vision/             # Vision processing package
│       │   ├── package.xml
│       │   ├── setup.py
│       │   └── robot_vision/
│       │       ├── camera_node.py    # Pulls stream & publishes raw Image
│       │       └── person_detection_node.py # Runs YOLO + InsightFace recognition
│       └── robot_control/            # Control and Navigation package
│           ├── package.xml
│           ├── setup.py
│           └── robot_control/
│               └── motion_planner_node.py # Calculates PID speed vectors & sends JSON
│
└── README.md                         # Main repository portal
```

---

## 🚀 Installation & Setup

### Prerequisite Libraries
Ensure your host machine runs **Ubuntu 24.04 LTS** with **ROS 2 Jazzy** installed. Install Python libraries:
```bash
pip install opencv-python mediapipe numpy insightface ultralytics websocket-client cv-bridge
```

### 1. Build the ROS 2 Workspace
```bash
# Clone the repository and navigate to workspace
cd face-detection-project/ros2_ws
colcon build --packages-select robot_vision robot_control
source install/setup.bash
```

### 2. Flashing Microcontrollers
* **ESP32-CAM**: Open [esp32_cam_stream.ino](file:///firmware/esp32_cam_stream/esp32_cam_stream.ino) in the Arduino IDE. Select the `ESP32 Wrover Module` board, map Wi-Fi credentials, and flash via FTDI programmer.
* **LILYGO LoRa32**: Open [lilygo_lora32_controller.ino](file:///firmware/lilygo_lora32_controller/lilygo_lora32_controller.ino) in the Arduino IDE. Select the `ESP32S3 Dev Module` board, install required libraries (`Adafruit_BNO055`, `Adafruit_SSD1306`, `RadioLib`, `ArduinoJson`, `WebSockets`), and upload.

---

## 🏃 Running the Robot

1. **Power up** the robot chassis. ESP32-CAM and LILYGO will automatically establish a Wi-Fi Access Point network (`Robot_Access_Point`).
2. **Connect** your Ubuntu Laptop to `Robot_Access_Point`.
3. Launch the ROS 2 Nodes in separate terminals:
```bash
# Terminal 1: Run Camera Node
ros2 run robot_vision camera_node

# Terminal 2: Run Host Identification Node
ros2 run robot_vision person_detection_node

# Terminal 3: Run Motion Control Planner
ros2 run robot_control motion_planner_node
```

---

## 👤 Project Developers

* **Priyam Patel** - *Lead Robotics and Embedded Systems Engineer* - [GitHub Profile](https://github.com/prpa23ece-ctrl)
* ECE Department, Final Year Project Team.
