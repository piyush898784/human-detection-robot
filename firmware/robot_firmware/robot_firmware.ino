/**
 * Human-Following Robot Firmware
 * 
 * This firmware runs on the robot's Arduino/ESP32 microcontroller.
 * It listens for commands over the Serial interface (from a Raspberry Pi, PC, or Jetson Nano)
 * and controls two DC gear motors (via an L298N motor driver) and two servo motors (Pan/Tilt gimbal).
 * 
 * Serial Command Protocol:
 * - Simple Commands:
 *   - 'F' : Move Forward
 *   - 'B' : Move Backward
 *   - 'L' : Turn Left
 *   - 'R' : Turn Right
 *   - 'S' : Stop Motors
 * - Pan/Tilt Angles (Optional smooth tracking):
 *   - Formatted as: "Y<yaw_angle>P<pitch_angle>\n" (e.g., "Y15.4P-5.2")
 *     Where yaw_angle is between -30 and +30, and pitch_angle is between -20 and +20.
 */

#include <Servo.h>

// --- L298N Motor Driver Pins ---
#define ENA 5   // Enable A (PWM) - Left Motor Speed
#define IN1 4   // Motor A Input 1 - Left Motor Forward
#define IN2 3   // Motor A Input 2 - Left Motor Backward
#define IN3 2   // Motor B Input 1 - Right Motor Forward
#define IN4 7   // Motor B Input 2 - Right Motor Backward
#define ENB 6   // Enable B (PWM) - Right Motor Speed

// --- Servo Gimbal Pins ---
#define PAN_PIN  9   // Yaw Servo
#define TILT_PIN 10  // Pitch Servo

// --- Speed Settings ---
const int MOTOR_SPEED_DEFAULT = 150;  // Default PWM speed (0-255)
const int MOTOR_SPEED_TURN    = 130;  // Turn PWM speed (0-255)

// --- Servo Setup ---
Servo panServo;
Servo tiltServo;

int currentPanAngle  = 90;  // Mid-point (Centered)
int currentTiltAngle = 90;  // Mid-point (Centered)

// --- Communication Buffers ---
String inputBuffer = "";

void setup() {
  // Initialize Serial communication
  Serial.begin(115200);
  while (!Serial) {
    ; // Wait for serial port to connect (needed for Leonardo/Micro)
  }
  
  // Configure Motor Pins as Outputs
  pinMode(ENA, OUTPUT);
  pinMode(ENB, OUTPUT);
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);

  // Attach Servo Motors
  panServo.attach(PAN_PIN);
  tiltServo.attach(TILT_PIN);

  // Write default center positions to servos
  panServo.write(currentPanAngle);
  tiltServo.write(currentTiltAngle);

  // Ensure robot starts in stopped state
  stopRobot();
  
  Serial.println("Robot Firmware Initialized. Ready for commands...");
}

void loop() {
  // Read incoming Serial data
  while (Serial.available() > 0) {
    char inChar = (char)Serial.read();
    if (inChar == '\n' || inChar == '\r') {
      if (inputBuffer.length() > 0) {
        processCommand(inputBuffer);
        inputBuffer = ""; // Reset buffer
      }
    } else {
      inputBuffer += inChar;
    }
  }
}

/**
 * Process the incoming command string.
 */
void processCommand(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;

  // Check for simple single-character commands
  if (cmd.length() == 1) {
    char action = cmd.charAt(0);
    switch (action) {
      case 'F':
        moveForward(MOTOR_SPEED_DEFAULT);
        Serial.println("ACK: Moving Forward");
        break;
      case 'B':
        moveBackward(MOTOR_SPEED_DEFAULT);
        Serial.println("ACK: Moving Backward");
        break;
      case 'L':
        turnLeft(MOTOR_SPEED_TURN);
        Serial.println("ACK: Turning Left");
        break;
      case 'R':
        turnRight(MOTOR_SPEED_TURN);
        Serial.println("ACK: Turning Right");
        break;
      case 'S':
        stopRobot();
        Serial.println("ACK: Stopped");
        break;
      default:
        Serial.print("ERROR: Unknown single command: ");
        Serial.println(action);
        break;
    }
  } 
  // Check for joint angle servo commands (e.g., Y15.4P-5.2)
  else if (cmd.startsWith("Y") && cmd.indexOf("P") > 0) {
    int pIndex = cmd.indexOf("P");
    String yawStr = cmd.substring(1, pIndex);
    String pitchStr = cmd.substring(pIndex + 1);

    float yawVal = yawStr.toFloat();
    float pitchVal = pitchStr.toFloat();

    // Map Yaw angle (-30 to 30 degrees) to servo angles (60 to 120 degrees)
    // Positive yaw = face is to the right, robot needs to pan camera right
    int targetPan = 90 - (int)yawVal;
    int targetTilt = 90 + (int)pitchVal;

    // Constrain angles to safe ranges to avoid mechanical strain
    targetPan = constrain(targetPan, 30, 150);
    targetTilt = constrain(targetTilt, 45, 135);

    // Update servos smoothly (basic smoothing)
    updateServos(targetPan, targetTilt);

    // Simple closed-loop chassis adjustment:
    // If the face is too far left/right, turn the wheels slightly
    if (yawVal > 15) {
      turnRight(MOTOR_SPEED_TURN);
    } else if (yawVal < -15) {
      turnLeft(MOTOR_SPEED_TURN);
    } else {
      // If face is centered horizontally, check if we need to move forward or backward
      // (Normally determined by area/distance, but here we can just maintain tracking)
      stopRobot(); 
    }

    Serial.print("ACK: Servos set to Pan=");
    Serial.print(targetPan);
    Serial.print(" Tilt=");
    Serial.println(targetTilt);
  }
  // Fallback for word commands
  else {
    if (cmd == "MOVE FORWARD") {
      moveForward(MOTOR_SPEED_DEFAULT);
      Serial.println("ACK: Moving Forward");
    } else if (cmd == "MOVE BACKWARD") {
      moveBackward(MOTOR_SPEED_DEFAULT);
      Serial.println("ACK: Moving Backward");
    } else if (cmd == "MOVE LEFT" || cmd == "TURN LEFT") {
      turnLeft(MOTOR_SPEED_TURN);
      Serial.println("ACK: Turning Left");
    } else if (cmd == "MOVE RIGHT" || cmd == "TURN RIGHT") {
      turnRight(MOTOR_SPEED_TURN);
      Serial.println("ACK: Turning Right");
    } else if (cmd == "CENTERED" || cmd == "CENTER" || cmd == "STOP") {
      stopRobot();
      Serial.println("ACK: Stopped");
    } else {
      Serial.print("ERROR: Invalid command: ");
      Serial.println(cmd);
    }
  }
}

// --- Motor Control Helper Functions ---

void moveForward(int speed) {
  analogWrite(ENA, speed);
  analogWrite(ENB, speed);
  
  // Left Motor Forward
  digitalWrite(IN1, HIGH);
  digitalWrite(IN2, LOW);
  // Right Motor Forward
  digitalWrite(IN3, HIGH);
  digitalWrite(IN4, LOW);
}

void moveBackward(int speed) {
  analogWrite(ENA, speed);
  analogWrite(ENB, speed);
  
  // Left Motor Backward
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, HIGH);
  // Right Motor Backward
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, HIGH);
}

void turnLeft(int speed) {
  analogWrite(ENA, speed);
  analogWrite(ENB, speed);
  
  // Left Motor Backward (aiding sharp turn)
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, HIGH);
  // Right Motor Forward
  digitalWrite(IN3, HIGH);
  digitalWrite(IN4, LOW);
}

void turnRight(int speed) {
  analogWrite(ENA, speed);
  analogWrite(ENB, speed);
  
  // Left Motor Forward
  digitalWrite(IN1, HIGH);
  digitalWrite(IN2, LOW);
  // Right Motor Backward (aiding sharp turn)
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, HIGH);
}

void stopRobot() {
  analogWrite(ENA, 0);
  analogWrite(ENB, 0);
  
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, LOW);
}

void updateServos(int targetPan, int targetTilt) {
  // Move servos to target position
  panServo.write(targetPan);
  tiltServo.write(targetTilt);
  
  currentPanAngle = targetPan;
  currentTiltAngle = targetTilt;
}
