/**
 * ESP32-CAM WiFi Video Streamer Firmware
 * 
 * Target Board: ESP32 Wrover Module (with Camera pins mapped for AI-Thinker)
 * This firmware establishes a Wi-Fi connection, initializes the OV2640 camera sensor,
 * and hosts a persistent HTTP server streaming MJPEG frames for ROS 2 vision processing.
 */

#include "esp_camera.h"
#include <WiFi.h>

// --- Wi-Fi Credentials ---
const char* ssid = "Robot_Access_Point";
const char* password = "AutonomousFollowRobot";

// --- CAMERA PIN MAP FOR AI-THINKER BOARD ---
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

// HTTP Server instance on Port 81 for raw video streaming
WiFiServer streamServer(81);

void startCameraServer() {
  streamServer.begin();
  Serial.println("MJPEG Video Server started on port 81.");
}

void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(true);
  Serial.println();

  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  // Frame size parameters: SVGA (800x600) for ideal tracking vs latency balance
  if(psramFound()){
    config.frame_size = FRAMESIZE_SVGA;
    config.jpeg_quality = 12; // 0-63 (lower is higher quality)
    config.fb_count = 2;
  } else {
    config.frame_size = FRAMESIZE_CIF;
    config.jpeg_quality = 12;
    config.fb_count = 1;
  }

  // Camera init
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed with error 0x%x", err);
    return;
  }

  // Connect to Wi-Fi
  WiFi.begin(ssid, password);
  Serial.print("Connecting to Wi-Fi: ");
  Serial.println(ssid);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("");
  Serial.println("Wi-Fi connected.");
  Serial.print("Stream URL: http://");
  Serial.print(WiFi.localIP());
  Serial.println(":81/stream");

  startCameraServer();
}

void loop() {
  WiFiClient client = streamServer.available();
  if (client) {
    Serial.println("New client connection established.");
    
    // Send HTTP Headers for MJPEG stream
    client.println("HTTP/1.1 200 OK");
    client.println("Content-Type: multipart/x-mixed-replace; boundary=123456789000000000000987654321");
    client.println("Access-Control-Allow-Origin: *");
    client.println();

    while (client.connected()) {
      camera_fb_t * fb = esp_camera_fb_get();
      if (!fb) {
        Serial.println("Frame capture failed.");
        break;
      }

      // Send Frame Boundary headers
      client.println("--123456789000000000000987654321");
      client.println("Content-Type: image/jpeg");
      client.printf("Content-Length: %d\r\n\r\n", fb->len);

      // Stream binary frame data
      client.write(fb->buf, fb->len);
      client.println();
      
      esp_camera_fb_return(fb);
      
      // Delay to regulate frame rate to ~25fps and prevent frame drops
      delay(40);
    }
    client.stop();
    Serial.println("Client disconnected.");
  }
  delay(1);
}
