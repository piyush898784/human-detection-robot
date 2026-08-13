# 04. System Workflows & Control Algorithms

This document describes the operational workflows, algorithms, mathematical equations, and decision state machines that run the Autonomous Human-Following Robot.

---

## 1. Global System Workflow

This flowchart outlines the execution path from cold boot to the continuous tracking and telemetry loop.

```mermaid
flowchart TD
    Start([Power On]) --> InitHW[Initialize Lilygo GPIOs, I2C, SPI, Serial]
    InitHW --> ConnWifi[Connect Lilygo & ESP32-CAM to Local Wi-Fi Router]
    ConnWifi --> StartROS[Launch ROS 2 Host Launchfile on Laptop]
    
    StartROS --> FrameGrab[ESP32-CAM HTTP Server Captures & Streams MJPEG]
    FrameGrab --> DevYOLO[YOLOv11 Person Detection Node Runs Inference]
    
    DevYOLO --> CheckDet{Person Found?}
    CheckDet -- No --> SweepState[Rotate Robot Chassis to Scan Environment]
    SweepState --> FrameGrab
    
    CheckDet -- Yes --> FaceRec[Extract Bounding Box & Run InsightFace Model]
    FaceRec --> HostCheck{Is Host Face Recognized?}
    
    HostCheck -- No --> IgnorePerson[Label Target 'Unknown' & Ignore]
    IgnorePerson --> FrameGrab
    
    HostCheck -- Yes --> Track[Run ByteTrack Tracking Loop on Bounding Box]
    
    Track --> Sensors[LILYGO Polls IMU, Encoders, & Ultrasonics]
    Sensors --> ObstCheck{Ultrasonic Distance < 30cm?}
    
    ObstCheck -- Yes --> StopEngage[Safety Override: Stop & Reverse Motors]
    StopEngage --> OLEDUpdate[Update SSD1306 Display State]
    
    ObstCheck -- No --> LocFuse[Fuse Encoder Ticks + BNO055 Yaw via Kalman Filter]
    LocFuse --> SpeedProfile[Compute CMD_VEL using Linear/Angular PID Loops]
    SpeedProfile --> TXSerial[Send Drive JSON Packets to LILYGO over WebSocket]
    TXSerial --> DriveMotors[TB6612FNG Actuates DC Motors]
    DriveMotors --> OLEDUpdate
    
    OLEDUpdate --> LoRaTX[Transmit Telemetry Packet via SX1262 LoRa]
    LoRaTX --> FrameGrab
```

---

## 2. Human-Following Algorithm

The following control loop ensures the robot maintains a safe distance and orientation relative to the host.

```mermaid
flowchart TD
    Input[Get Host Bounding Box: Center X, Center Y, Width, Height] --> AngErr[Calculate Horizontal Pixel Error: Err_x = BBox_CenterX - Frame_CenterX]
    AngErr --> AreaCalc[Calculate Bounding Box Area: Area = Width * Height]
    
    AreaCalc --> TargetPID[Run Area PID Controller to compute Target Linear Velocity v]
    TargetPID --> AngPID[Run Angle PID Controller to compute Target Angular Velocity w]
    
    AngPID --> Limiter[Constrain v to -0.5 to +0.8 m/s, Constrain w to -1.0 to +1.0 rad/s]
    Limiter --> Output[Publish twist msg: linear.x = v, angular.z = w]
```

### Mathematical Formulations

1. **Angular Error Tracking (Yaw)**:
   $$e_{\theta}(t) = x_{\text{bbox\_center}} - x_{\text{frame\_center}}$$
   $$\omega(t) = K_{p,\theta} \, e_{\theta}(t) + K_{i,\theta} \int e_{\theta}(t) \, dt + K_{d,\theta} \frac{de_{\theta}(t)}{dt}$$

2. **Distance Error Tracking (Linear Vel)**:
   $$e_{d}(t) = A_{\text{target\_area}} - A_{\text{current\_area}}$$
   $$v(t) = K_{p,d} \, e_{d}(t) + K_{i,d} \int e_{d}(t) \, dt + K_{d,d} \frac{de_{d}(t)}{dt}$$

---

## 3. Face Recognition Workflow (InsightFace)

The host identification process uses a deep convolutional feature extractor to extract a highly discriminating vector representation of the face.

```mermaid
flowchart TD
    ImgIn[Read Face Sub-Image from BBox] --> Align[Perform Face Alignment using 5-point landmarks]
    Align --> FeedBackbone[Pass Image to ResNet-50 InsightFace Backbone]
    FeedBackbone --> Embedding[Generate 512-Dimensional Feature Vector V_curr]
    
    Embedding --> DBCompare[Retrieve Registered Host Embedding V_host from local DB]
    DBCompare --> SimCalc[Calculate Cosine Similarity: S = V_curr . V_host / ||V_curr|| * ||V_host||]
    
    SimCalc --> SimCheck{Similarity S > 0.65?}
    SimCheck -- Yes --> Auth[Host Authenticated: Lock-On & Track]
    SimCheck -- No --> AuthFail[Reject: Tag Person as Unknown]
```

---

## 4. Object Detection Workflow (YOLOv11)

To detect obstacles and classify surrounding objects, the raw image frame is sent to a YOLOv11 pipeline.

```mermaid
flowchart TD
    Frame[Raw RGB Image Frame] --> YOLO[Run YOLOv11 Nano Inference]
    YOLO --> BBoxes[Extract Bounding Boxes, Class IDs, and Confidences]
    
    BBoxes --> Filter{Class ID in Obstacle Classes? e.g. Chair, Table, Box}
    Filter -- Yes --> CalcDist[Estimate Distance based on Ground Projection Camera Calibration]
    CalcDist --> MapUpdate[Add Obstacle coordinates to Local Costmap]
    Filter -- No --> Ignore[Discard Detections]
```

---

## 5. Obstacle Avoidance Workflow

A physical safety loop runs on the LILYGO controller, polling the HC-SR04 ultrasonic sensors at 50Hz to override any commands received from the laptop in case of immediate collision.

```mermaid
flowchart TD
    Ping[Send 10us Trigger Pulse to HC-SR04] --> Echo[Measure Echo Pulse Duration t]
    Echo --> Dist[Calculate Distance: D = t * 0.034 / 2 cm]
    
    Dist --> Threshold{Distance < 30 cm?}
    Threshold -- Yes --> Interr[Engage Safety Interrupt: Override Motor Commands]
    Interr --> Reverse[Move Backward at low speed for 500ms, then STOP]
    
    Threshold -- No --> KeepCMD[Forward Incoming ROS 2 cmd_vel directly to Motor Drivers]
```

---

## 6. Sensor Fusion Navigation Workflow

To prevent wheel slippage errors on the 6-wheel metal chassis, encoder data is fused with inertial sensors.

```mermaid
graph TD
    Enc[Wheel Encoders] -->|Raw Ticks| OdomCalc[Calculate Encoder Wheel Odometry]
    IMU[BNO055 IMU] -->|Angular Velocities & Acceleration| IMUCalc[Calculate Orientation Heading]
    
    OdomCalc --> EKF[Extended Kalman Filter Node - robot_localization]
    IMUCalc --> EKF
    
    EKF -->|Fused State Estimation| PathCorrection[Adjust Motor Commands to Compensate for Slip]
```

### EKF State Model
The EKF estimates the robot's pose vector:
$$X = \begin{bmatrix} x & y & \theta & v_x & v_y & \omega \end{bmatrix}^T$$

* **Prediction Step**: Utilizes kinematic model driven by wheel encoder velocities.
* **Correction Step**: Minimizes error in $\theta$ and $\omega$ using high-accuracy IMU magnetometer and gyroscope output, keeping spatial tracking accurate.
