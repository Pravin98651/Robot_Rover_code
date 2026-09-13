#include "esp_camera.h"
#include <WiFi.h>

// =====================================================
// WIFI
// ================= WIFI =================
const char* ssid = "Gtech";
const char* password = "123456789";

// =====================================================
// AI THINKER ESP32-CAM
// =====================================================

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


WiFiServer server(80);


// =====================================================
// SEND ALL BYTES - PREVENTS PARTIAL FRAME WRITES
// =====================================================

bool sendAll(WiFiClient &client, const uint8_t *data, size_t len)
{
  size_t sent = 0;

  while (sent < len)
  {
    if (!client.connected())
      return false;

    size_t n = client.write(data + sent, len - sent);

    if (n == 0)
      return false;

    sent += n;
  }

  return true;
}


// =====================================================
// SETUP
// =====================================================

void setup()
{
  Serial.begin(115200);

  delay(500);

  Serial.println();
  Serial.println("Starting ESP32-CAM...");


  // ===================================================
  // CAMERA CONFIG
  // ===================================================

  camera_config_t config;

  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;

  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;

  config.pin_xclk = XCLK_GPIO_NUM;

  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;

  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;

  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;

  config.xclk_freq_hz = 20000000;

  // JPEG is fastest for Wi-Fi
  config.pixel_format = PIXFORMAT_JPEG;


  // ===================================================
  // MAXIMUM PRACTICAL QUALITY + SPEED
  // ===================================================

  // 640 x 480
  config.frame_size = FRAMESIZE_VGA;

  // 10 = high JPEG quality
  // Lower = clearer / larger file
  config.jpeg_quality = 10;


  // ===================================================
  // PSRAM BUFFERING
  // ===================================================

  if (psramFound())
  {
    config.fb_count = 2;

    // Always prefer newest frame
    config.grab_mode = CAMERA_GRAB_LATEST;
  }
  else
  {
    config.fb_count = 1;
  }


  // ===================================================
  // INITIALIZE CAMERA
  // ===================================================

  esp_err_t err = esp_camera_init(&config);

  if (err != ESP_OK)
  {
    Serial.print("Camera initialization failed: 0x");
    Serial.println(err, HEX);

    while (true)
    {
      delay(1000);
    }
  }

  Serial.println("Camera initialized successfully!");


  // ===================================================
  // CAMERA SENSOR SETTINGS
  // ===================================================

  sensor_t *sensor = esp_camera_sensor_get();

  sensor->set_framesize(sensor, FRAMESIZE_VGA);

  sensor->set_quality(sensor, 10);

  // Normal image
  sensor->set_brightness(sensor, 0);
  sensor->set_contrast(sensor, 1);
  sensor->set_saturation(sensor, 0);

  // Enable automatic exposure
  sensor->set_exposure_ctrl(sensor, 1);

  // Enable automatic gain
  sensor->set_gain_ctrl(sensor, 1);

  // Enable automatic white balance
  sensor->set_whitebal(sensor, 1);

  // Enable lens correction
  sensor->set_lenc(sensor, 1);


  // ===================================================
  // WIFI
  // ===================================================

  WiFi.mode(WIFI_STA);

  // Disable Wi-Fi power saving
  WiFi.setSleep(false);

  // Maximum transmission power
  WiFi.setTxPower(WIFI_POWER_19_5dBm);

  WiFi.begin(ssid, password);


  Serial.print("Connecting to WiFi");

  while (WiFi.status() != WL_CONNECTED)
  {
    delay(200);
    Serial.print(".");
  }

  Serial.println();

  Serial.println("WiFi connected!");

  Serial.print("Signal strength: ");
  Serial.print(WiFi.RSSI());
  Serial.println(" dBm");

  Serial.print("Camera IP: ");
  Serial.println(WiFi.localIP());


  // ===================================================
  // SERVER
  // ===================================================

  server.begin();

  Serial.println();
  Serial.println("================================");
  Serial.println("     ESP32-CAM LIVE READY");
  Serial.println("================================");
  Serial.println();
}


// =====================================================
// WEB PAGE
// =====================================================

void sendWebPage(WiFiClient &client)
{
  client.setNoDelay(true);

  client.print(
    "HTTP/1.1 200 OK\r\n"
    "Content-Type: text/html\r\n"
    "Cache-Control: no-cache\r\n"
    "Connection: close\r\n"
    "\r\n"

    "<!DOCTYPE html>"
    "<html>"
    "<head>"
    "<meta name='viewport' "
    "content='width=device-width,initial-scale=1'>"
    "<title>ESP32-CAM LIVE</title>"
    "</head>"

    "<body style='"
    "margin:0;"
    "padding:0;"
    "background:#000;"
    "overflow:hidden;"
    "'>"

    "<img src='/stream' "
    "style='"
    "display:block;"
    "width:100vw;"
    "height:100vh;"
    "object-fit:contain;"
    "'>"

    "</body>"
    "</html>"
  );
}


// =====================================================
// HIGH-SPEED MJPEG STREAM
// =====================================================

void streamCamera(WiFiClient &client)
{
  client.setNoDelay(true);
  client.setTimeout(2000);


  // ===================================================
  // HTTP STREAM HEADER
  // ===================================================

  client.print(
    "HTTP/1.1 200 OK\r\n"
    "Content-Type: multipart/x-mixed-replace; boundary=frame\r\n"
    "Cache-Control: no-cache, no-store, must-revalidate\r\n"
    "Pragma: no-cache\r\n"
    "Connection: keep-alive\r\n"
    "\r\n"
  );


  // ===================================================
  // CONTINUOUS VIDEO
  // ===================================================

  while (client.connected())
  {
    // Get newest available frame
    camera_fb_t *fb = esp_camera_fb_get();

    if (!fb)
    {
      continue;
    }


    // =================================================
    // FRAME HEADER
    // =================================================

    client.print("--frame\r\n");
    client.print("Content-Type: image/jpeg\r\n");
    client.print("Content-Length: ");
    client.print(fb->len);
    client.print("\r\n\r\n");


    // =================================================
    // SEND COMPLETE JPEG
    // =================================================

    bool success = sendAll(
      client,
      fb->buf,
      fb->len
    );


    client.print("\r\n");


    // =================================================
    // RELEASE BUFFER
    // =================================================

    esp_camera_fb_return(fb);


    if (!success)
    {
      break;
    }

    // NO delay
  }
}


// =====================================================
// LOOP
// =====================================================

void loop()
{
  WiFiClient client = server.available();

  if (!client)
  {
    return;
  }


  client.setNoDelay(true);

  String request = "";

  unsigned long startTime = millis();


  // ===================================================
  // READ HTTP REQUEST
  // ===================================================

  while (
    client.connected() &&
    millis() - startTime < 1000
  )
  {
    if (client.available())
    {
      char c = client.read();

      request += c;

      if (request.endsWith("\r\n\r\n"))
      {
        break;
      }
    }
  }


  // ===================================================
  // STREAM
  // ===================================================

  if (request.indexOf("GET /stream") >= 0)
  {
    streamCamera(client);
  }
  else
  {
    sendWebPage(client);
  }


  client.stop();
}