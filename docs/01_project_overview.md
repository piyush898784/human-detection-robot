# 01. Project Overview

## 1. Introduction
Autonomous mobile robots have transitioned from structured industrial environments to unstructured human-centric spaces. A critical capability for helper, service, and security robots is **autonomous human-following**. Traditional following systems rely on active tracking technologies such as infrared beacons, ultra-wideband (UWB) transmitters, or wearable GPS units. While functional, these systems require the user to carry external hardware, suffer from signal occlusion, and cannot distinguish between different people.

This project introduces a comprehensive, multi-layered architecture for an **Autonomous Human-Following and Instruction-Following Robot** that leverages edge computer vision, decentralized processing, real-time wireless telemetry, and sensor fusion. 

By combining:
* **ESP32-CAM** for low-cost, distributed video streaming.
* **ROS 2 (Jazzy Jalisco)** running on a laptop for advanced AI vision tasks (YOLOv11, InsightFace, ByteTrack) and motion planning.
* **LILYGO LoRa32 V3** for low-level motor drive, real-time obstacle avoidance, and long-range LoRa telemetry.

The robot is capable of identifying a specific human host, navigating toward them, accepting spoken and predefined commands, avoiding obstacles, and publishing telemetry data securely.

---

## 2. Problem Statement
Existing human-following robots suffer from several engineering challenges:
1. **Target Ambiguity**: Simple computer vision models easily lose track of the target when another person crosses the field of view (occlusion and ID switching).
2. **Computational Bottlenecks**: Performing deep learning-based object detection, face recognition, and motion planning directly on embedded microcontrollers is impossible due to memory and clock speed constraints.
3. **Short-Range Communication**: Standard Wi-Fi and Bluetooth connections suffer from high signal attenuation, limiting remote telemetry monitoring to a few meters indoors.
4. **Odometry Drift**: Relying solely on wheel encoders for localization leads to cumulative positional errors due to wheel slippage, especially in 6-wheeled differential chassis designs.

---

## 3. Project Objectives
The core objectives of this project are:
* **Host Verification & Tracking**: Implement real-time YOLOv11 person detection integrated with InsightFace face recognition to track and follow *only* the registered host, ignoring unauthorized bystanders.
* **Instruction Interpretation**: Integrate a local Whisper-based speech-to-text engine to decode voice instructions and execute movement directives.
* **Decentralized Multi-Computing**: Partition the computing tasks into three tiers: Perception (ESP32-CAM), Logic & AI (ROS 2 Laptop), and Actuation (LILYGO LoRa32).
* **Sensor Fusion Localization**: Fuse wheel encoders and a 9-axis BNO055 IMU using an Extended Kalman Filter (EKF) to maintain accurate spatial positioning.
* **Safety & Obstacle Avoidance**: Integrate dual HC-SR04 ultrasonic sensors to enforce safe following distances and override motor commands to prevent collisions.
* **Long-Range Telemetry**: Transmit hardware health, localization coordinates, and battery parameters over LoRa to a ground monitoring station.

---

## 4. Technical Applications
* **Eldercare & Assistive Robotics**: Act as a hands-free shopping assistant, medical trolley, or companion robot following elderly or disabled users.
* **Industrial Warehousing**: Follow warehouse personnel to transport tools, packages, or materials dynamically without fixed rails.
* **Military & Border Surveillance**: Accompany soldiers as an autonomous mule, carrying heavy equipment or scouting hazardous terrain while transmitting telemetry over LoRa back to base.
* **Smart Agriculture**: Follow farmers in fields, carrying harvested produce or monitoring crop health via camera sensors.

---

## 5. System Advantages
* **Host Lock-On**: The robot does not follow the nearest human; it specifically recognizes and targets the host's face.
* **High Modularity**: Replacing the vision node or upgrading the AI model does not require changing the motor control logic or electrical wiring.
* **Long-Range Diagnostics**: LoRa communication allows ground stations to receive GPS-like coordinates and warning flags even if the local Wi-Fi connection drops.
* **All-Terrain Stability**: The 6-wheel metal chassis distributes load and provides high traction across indoor carpets, thresholds, and outdoor dirt paths.

---

## 6. Future Scope
* **Indoor SLAM**: Integrate a 2D LiDAR to build grid maps and perform path planning using the ROS 2 Navigation Stack (Nav2).
* **Edge AI Acceleration**: Replace the laptop with a dedicated on-board Edge-AI accelerator (e.g., NVIDIA Jetson Orin Nano) to make the robot fully self-contained.
* **Gesture Control**: Incorporate MediaPipe Pose estimation to allow the host to control the robot via hand gestures (e.g., Stop, Come Closer, Go Away).

---

## 7. Expected Outcomes
Upon successful integration, the robot will achieve:
1. Smooth tracking of the host at distances between **0.8 meters and 3.0 meters**.
2. Stop response within **100 milliseconds** of detecting an obstacle within a 20 cm path.
3. Telemetry range exceeding **500 meters** in non-line-of-sight urban environments.
4. Smooth rotational adjustment of $\pm 5^\circ$ accuracy based on IMU heading data.
5. Real-time status display of IP address, battery voltage, and track-state on the onboard OLED display.
