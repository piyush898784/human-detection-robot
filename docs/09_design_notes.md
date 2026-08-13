# 09. Engineering Design Notes & Rationales

This document details the engineering trade-offs, design rationales, and architectural decisions made during the development of the Autonomous Human-Following Robot.

---

## 1. Separation of ESP32-CAM (Vision) and LILYGO (Embedded Controller)

### The Challenge
A single microcontroller cannot simultaneously capture a video feed, encode it, maintain a Wi-Fi TCP server, poll a high-frequency IMU, read quadrature wheel encoder ticks (which trigger external hardware interrupts at up to $1\text{ kHz}$), and execute real-time PWM motor driving without dropping frames or missing sensor updates.

### The Solution
We separate the system into a dedicated **Perception Node** and an **Actuation/Sensor Node**:
* **ESP32-CAM**: Functions as a dedicated, low-cost video streaming server. It is completely isolated from motor transients and interrupt calls.
* **LILYGO LoRa32 V3**: Functions as the primary actuation controller. Its dual-core ESP32-S3 processor handles real-time motor control and sensor loops, keeping the control cycle latency under 20ms.

---

## 2. Why ROS 2 (Jazzy Jalisco)?

Instead of relying on a custom, monolithic Python script on a laptop, we selected ROS 2 for the high-level control system:
* **Asynchronous Nodes**: The person detection, face recognition, object classification, and voice recognition modules run as independent ROS 2 nodes. If one node fails (e.g., the voice node crashes), the other nodes continue to run, preventing complete system failures.
* **Lifecycle Management**: ROS 2 provides robust tools to manage node states, monitor message latency, and profile processor usage.
* **DDS Middleware**: Enables secure, low-latency, and reliable network communication between nodes over standard Wi-Fi networks.

---

## 3. Why Fusing Wheel Encoders and the BNO055 IMU?

### The Challenge of Odometry Drift
Standard wheel odometry calculates the robot's change in position based on the number of wheel rotations:
$$d = \frac{\pi \times D \times \text{ticks}}{\text{ticks\_per\_rev}}$$

However, in a 6-wheel chassis, skid-steering requires some wheels to slide laterally during turns. This causes severe wheel slippage, resulting in cumulative errors (drift) in the calculated heading angle ($\theta$).

### The Solution
We fuse the sensors using an Extended Kalman Filter (EKF):
* **Wheel Encoders**: Provide high-resolution measurements of linear speed ($v_x$).
* **BNO055 Smart IMU**: Provides orientation heading ($\theta$) using its onboard fusion processor, which integrates accelerometer, gyroscope, and magnetometer data.
* **The Result**: The EKF corrects wheel slippage errors by updating the robot's orientation based on the drift-free heading data from the IMU.

---

## 4. Selection of LoRa (SX1262) for Telemetry

While the robot uses Wi-Fi to receive motion commands from the local laptop, Wi-Fi is not suitable for long-range remote monitoring:
* **Range Constraints**: Wi-Fi signal strength drops significantly beyond 30 meters in indoor environments due to walls and interference.
* **Failsafe Telemetry**: By transmitting telemetry packets over LoRa at $433\text{ MHz}$ or $868\text{ MHz}$, the ground station can monitor the robot's coordinates, battery levels, and safety flags up to several hundred meters away, even if the primary Wi-Fi connection is lost.

---

## 5. TB6612FNG vs. Traditional L298N Motor Driver

The older L298N motor driver is commonly used in hobbyist projects, but it is not suitable for an efficient mobile robot:
1. **Voltage Drop**: The L298N uses Bipolar Junction Transistors (BJTs), which cause an internal voltage drop of $1.5\text{V} - 2.0\text{V}$ between the battery and the motors. This voltage is lost as heat.
2. **Efficiency**: The TB6612FNG uses MOSFET-based H-bridges with an internal resistance of only $0.5\ \Omega$. This results in negligible voltage drop, less heat generation, and longer battery life.
3. **Form Factor**: The TB6612FNG is much smaller and lighter than the L298N, which is critical for compact robot chassis designs.

---

## 6. Rationale for a 6-Wheel Chassis

We selected a 6-wheel chassis over a 2-wheel or 4-wheel configuration for the following reasons:
* **High Traction**: 6-wheel drive distributes weight across six contact points, providing high traction on slippery surfaces.
* **No Tipping**: Unlike 2-wheel robots that rely on caster wheels and can tip forward during sudden braking, a 6-wheel chassis is inherently stable and keeps the camera gimbal level.
* **Climbing Ability**: The center wheels act as a pivot point, allowing the robot to climb over minor carpet transitions, thresholds, and cable covers.
