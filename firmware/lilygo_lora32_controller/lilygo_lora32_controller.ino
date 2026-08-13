/**
 * LILYGO LoRa32 V3 Actuation and Sensor Controller Firmware
 * 
 * Target Board: LILYGO T-Lite / T3-S3 LoRa32 V3 (ESP32-S3 Core)
 * Peripherals: 
 *   - Onboard SSD1306 OLED (I2C SDA=18, SCL=17)
 *   - SX1262 LoRa (SPI NSS=8, SCK=9, MOSI=10, MISO=11, RST=5, BUSY=13, DIO1=14)
 *   - External BNO055 IMU (I2C SDA=18, SCL=17)
 *   - Dual TB6612FNG Motor Drivers & DC Encoders
 *   - Dual HC-SR04 Ultrasonic Sensors
 *   - Resistor Battery Divider (ADC 4)
 */

#include <Wire.h>
#include <SPI.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Adafruit_BNO055.h>
#include <RadioLib.h>
#include <WiFi.h>
#include <WebSocketsServer.h>
#include <ArduinoJson.h>

// --- Pin Allocations ---
#define ENA 1
#define IN1 2
#define IN2 3
#define ENB 6
#define IN3 7
#define IN4 10 // Shared or distinct direction pins (TB6612 #2 uses IN3/IN4)
// Let's align with the GPIO assignment table:
// Left: ENA=1, IN1=2, IN2=3. Right: ENB=6, IN3=7, IN4=10 (or pin maps)
#define IN4_DIR 21 // Direction 2 for Right

#define BAT_ADC 4
#define BUZZER 46

// Encoders (Quadrature Phase Interrupt Pins)
#define ENC_L_A 41
#define ENC_L_B 42
#define ENC_R_A 39
#define ENC_R_B 40

// Ultrasonic Sensors
#define TRIG_L 12
#define ECHO_L 47
#define TRIG_R 15
#define ECHO_R 16

// LILYGO SX1262 LoRa Pins
#define LORA_NSS  8
#define LORA_SCK  9
#define LORA_MOSI 10
#define LORA_MISO 11
#define LORA_RST  5
#define LORA_BUSY 13
#define LORA_DIO1 14

// --- OLED & IMU Instantiations ---
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET -1
Adafruit_SSD1306 oled(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);
Adafruit_BNO055 bno = Adafruit_BNO055(55, 0x28);

// --- LoRa Transceiver Instantiation ---
// SX1262 pin mapping
Module module(LORA_NSS, LORA_DIO1, LORA_RST, LORA_BUSY);
SX1262 lora = &module;

// --- Wi-Fi & WebSockets ---
const char* ssid = "Robot_Access_Point";
const char* password = "AutonomousFollowRobot";
WebSocketsServer webSocket = WebSocketsServer(80);

// --- State Variables ---
volatile int32_t leftEncoderTicks = 0;
volatile int32_t rightEncoderTicks = 0;

float batteryVoltage = 12.0;
float currentYaw = 0.0;
int rangeL = 100;
int rangeR = 100;

int motorSpeedL = 0;
int motorSpeedR = 0;
String trackingStatus = "LOST";
String robotMode = "AUTO_FOLLOW";
uint8_t errorCode = 0;

// --- Encoder Interrupt Service Routines ---
void IRAM_ATTR leftEncoderISR() {
  if (digitalRead(ENC_L_B) == HIGH) leftEncoderTicks++;
  else leftEncoderTicks--;
}

void IRAM_ATTR rightEncoderISR() {
  if (digitalRead(ENC_R_B) == HIGH) rightEncoderTicks++;
  else rightEncoderTicks--;
}

void setup() {
  Serial.begin(115200);
  Wire.begin(18, 17); // Custom SDA, SCL for LILYGO board

  // Pin Modes
  pinMode(ENA, OUTPUT);
  pinMode(ENB, OUTPUT);
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4_DIR, OUTPUT);
  pinMode(BUZZER, OUTPUT);

  pinMode(TRIG_L, OUTPUT);
  pinMode(ECHO_L, INPUT);
  pinMode(TRIG_R, OUTPUT);
  pinMode(ECHO_R, INPUT);

  pinMode(ENC_L_A, INPUT_PULLUP);
  pinMode(ENC_L_B, INPUT_PULLUP);
  pinMode(ENC_R_A, INPUT_PULLUP);
  pinMode(ENC_R_B, INPUT_PULLUP);

  // Attach Interrupts for Encoders
  attachInterrupt(digitalPinToInterrupt(ENC_L_A), leftEncoderISR, RISING);
  attachInterrupt(digitalPinToInterrupt(ENC_R_A), rightEncoderISR, RISING);

  // OLED Init
  if (oled.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    oled.clearDisplay();
    oled.setTextSize(1);
    oled.setTextColor(WHITE);
    oled.setCursor(0, 0);
    oled.println("System Booting...");
    oled.display();
  }

  // IMU Init
  if (!bno.begin()) {
    Serial.println("BNO055 Init Failed.");
    errorCode |= (1 << 1); // Set bit 1
  }

  // Initialize LoRa
  SPI.begin(LORA_SCK, LORA_MISO, LORA_MOSI, LORA_NSS);
  int state = lora.begin(433.0); // Configure frequency to 433 MHz
  if (state == RADIOLIB_ERR_NONE) {
    lora.setOutputPower(22); // High-gain output power (22 dBm)
  } else {
    Serial.println("LoRa Initialization Failed.");
  }

  // Configure WiFi Access Point
  WiFi.softAP(ssid, password);
  Serial.println("WiFi AP started.");
  Serial.print("AP IP Address: ");
  Serial.println(WiFi.softAPIP());

  // WebSocket Event Handler
  webSocket.begin();
  webSocket.onEvent(webSocketEvent);
}

void loop() {
  webSocket.loop();
  
  // Read local hardware parameters
  readSensors();
  
  // Process Safety Checks
  processSafetyOverrides();

  // Run UI updates and LoRa Telemetry transmissions every 200ms
  static uint32_t lastTaskTime = 0;
  if (millis() - lastTaskTime > 200) {
    updateOLED();
    transmitTelemetry();
    lastTaskTime = millis();
  }
}

/**
 * Poll Local Sensors
 */
void readSensors() {
  // Read HC-SR04 distances
  rangeL = triggerUltrasonic(TRIG_L, ECHO_L);
  rangeR = triggerUltrasonic(TRIG_R, ECHO_R);

  // Read BNO055 heading data
  sensors_event_t event;
  bno.getEvent(&event);
  currentYaw = event.orientation.x; // Absolute Yaw angle (0-360 deg)

  // Read Battery charge levels via Resistor Divider on ADC 4
  int adcVal = analogRead(BAT_ADC);
  batteryVoltage = (adcVal / 4095.0) * 3.3 * 4.0; // 4:1 voltage divider ratio
}

int triggerUltrasonic(int trigPin, int echoPin) {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);
  long duration = pulseIn(echoPin, HIGH, 30000); // 30ms timeout limit
  if (duration == 0) return 400; // Return max range if out of limit
  return duration * 0.0343 / 2.0;
}

/**
 * Safety Override
 */
void processSafetyOverrides() {
  if (rangeL < 30 || rangeR < 30) {
    // Collision warning threshold triggered
    analogWrite(ENA, 0);
    analogWrite(ENB, 0);
    digitalWrite(BUZZER, HIGH);
    trackingStatus = "OBSTACLE!";
  } else {
    digitalWrite(BUZZER, LOW);
  }
}

/**
 * WebSocket Command Processing
 */
void webSocketEvent(uint8_t num, WStype_t type, uint8_t * payload, size_t length) {
  if (type == WStype_TEXT) {
    StaticJsonDocument<200> doc;
    DeserializationError error = deserializeJson(doc, payload);
    if (!error) {
      float linear_x = doc["x_vel"];
      float angular_z = doc["yaw_vel"];
      trackingStatus = doc["status"] | "LOST";
      
      // Calculate speeds based on Twist commands
      motorSpeedL = (linear_x - angular_z) * 255.0;
      motorSpeedR = (linear_x + angular_z) * 255.0;

      // Constrain speeds to PWM range
      motorSpeedL = constrain(motorSpeedL, -255, 255);
      motorSpeedR = constrain(motorSpeedR, -255, 255);

      driveMotors(motorSpeedL, motorSpeedR);
    }
  }
}

void driveMotors(int speedL, int speedR) {
  if (rangeL < 30 || rangeR < 30) return; // Prevent actuation if safety triggered

  // Left Motors Drive
  if (speedL >= 0) {
    digitalWrite(IN1, HIGH);
    digitalWrite(IN2, LOW);
    analogWrite(ENA, speedL);
  } else {
    digitalWrite(IN1, LOW);
    digitalWrite(IN2, HIGH);
    analogWrite(ENA, abs(speedL));
  }

  // Right Motors Drive
  if (speedR >= 0) {
    digitalWrite(IN3, HIGH);
    digitalWrite(IN4_DIR, LOW);
    analogWrite(ENB, speedR);
  } else {
    digitalWrite(IN3, LOW);
    digitalWrite(IN4_DIR, HIGH);
    analogWrite(ENB, abs(speedR));
  }
}

/**
 * UI Refresh
 */
void updateOLED() {
  oled.clearDisplay();
  oled.setCursor(0, 0);
  oled.printf("BAT: %2.1fV WiFi: AP\n", batteryVoltage);
  oled.println("---------------------");
  oled.printf("MODE: %s\n", robotMode.c_str());
  oled.printf("STATUS: %s\n", trackingStatus.c_str());
  oled.printf("HEADING: %3.1f deg\n", currentYaw);
  oled.printf("US DIST L:%3d R:%3d\n", rangeL, rangeR);
  oled.printf("MOTORS L:%3d R:%3d\n", motorSpeedL, motorSpeedR);
  oled.display();
}

/**
 * Telemetry Transmission over LoRa (Binary Packet Format)
 */
void transmitTelemetry() {
  // Create binary payload matching the 24-byte telemetry structure
  uint8_t payload[24];
  
  float heading = currentYaw;
  int32_t encL = leftEncoderTicks;
  int32_t encR = rightEncoderTicks;
  uint16_t distL = (uint16_t)rangeL;
  uint16_t distR = (uint16_t)rangeR;
  uint8_t hostState = (trackingStatus == "LOCK-ON") ? 2 : ((trackingStatus == "SEARCHING") ? 1 : 0);
  uint8_t mode = 1; // Auto-follow code
  int8_t temp = 35; // Default reference temperature
  
  memcpy(&payload[0], &batteryVoltage, 4);
  memcpy(&payload[4], &heading, 4);
  memcpy(&payload[8], &encL, 4);
  memcpy(&payload[12], &encR, 4);
  memcpy(&payload[16], &distL, 2);
  memcpy(&payload[18], &distR, 2);
  payload[20] = hostState;
  payload[21] = mode;
  payload[22] = temp;
  payload[23] = errorCode;

  lora.transmit(payload, 24);
}
