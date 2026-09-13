#include "esp_camera.h"
#include <WiFi.h>

// =====================================================
// WIFI
// =====================================================

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


// =====================================================
// HTTP SERVER
// =====================================================

WiFiServer server(80);


// =====================================================
// SEND ALL BYTES
// =====================================================

bool sendAll(
    WiFiClient& client,
    const uint8_t* data,
    size_t length
)
{
    size_t sentTotal = 0;

    while (sentTotal < length)
    {
        if (!client.connected())
        {
            return false;
        }

        size_t sent = client.write(
            data + sentTotal,
            length - sentTotal
        );

        if (sent == 0)
        {
            return false;
        }

        sentTotal += sent;
    }

    return true;
}


// =====================================================
// CAMERA INITIALIZATION
// =====================================================

bool initializeCamera()
{
    camera_config_t config = {};

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

    config.pin_xclk  = XCLK_GPIO_NUM;
    config.pin_pclk  = PCLK_GPIO_NUM;
    config.pin_vsync = VSYNC_GPIO_NUM;
    config.pin_href  = HREF_GPIO_NUM;

    config.pin_sccb_sda = SIOD_GPIO_NUM;
    config.pin_sccb_scl = SIOC_GPIO_NUM;

    config.pin_pwdn  = PWDN_GPIO_NUM;
    config.pin_reset = RESET_GPIO_NUM;

    config.xclk_freq_hz = 20000000;

    // JPEG is ideal for Wi-Fi streaming.
    config.pixel_format = PIXFORMAT_JPEG;


    // =================================================
    // CAMERA CONFIG
    // =================================================

    if (psramFound())
    {
        Serial.println("PSRAM detected.");

        // 320 x 240
        // Start with this for stable streaming.
        config.frame_size = FRAMESIZE_QVGA;

        // 12 gives a reasonable quality/size tradeoff.
        config.jpeg_quality = 12;

        // Double buffering.
        config.fb_count = 2;

        // Store buffers in PSRAM.
        config.fb_location = CAMERA_FB_IN_PSRAM;

        // Always prefer newest frame.
        config.grab_mode = CAMERA_GRAB_LATEST;
    }
    else
    {
        Serial.println("WARNING: PSRAM not detected.");

        // Very small resolution if PSRAM is unavailable.
        config.frame_size = FRAMESIZE_QQVGA;

        config.jpeg_quality = 15;

        config.fb_count = 1;

        config.fb_location = CAMERA_FB_IN_DRAM;

        config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
    }


    // =================================================
    // INITIALIZE CAMERA
    // =================================================

    Serial.println("Initializing camera...");

    esp_err_t result = esp_camera_init(&config);

    if (result != ESP_OK)
    {
        Serial.print("Camera initialization failed: 0x");
        Serial.println(result, HEX);

        return false;
    }


    // =================================================
    // SENSOR SETTINGS
    // =================================================

    sensor_t* sensor = esp_camera_sensor_get();

    if (sensor == nullptr)
    {
        Serial.println("ERROR: Camera sensor unavailable.");

        return false;
    }

    sensor->set_framesize(sensor, FRAMESIZE_QVGA);

    sensor->set_quality(sensor, 12);

    sensor->set_brightness(sensor, 0);
    sensor->set_contrast(sensor, 1);
    sensor->set_saturation(sensor, 0);

    sensor->set_exposure_ctrl(sensor, 1);
    sensor->set_gain_ctrl(sensor, 1);
    sensor->set_whitebal(sensor, 1);

    sensor->set_lenc(sensor, 1);


    Serial.println("Camera initialized successfully.");

    return true;
}


// =====================================================
// WIFI
// =====================================================

bool initializeWiFi()
{
    WiFi.mode(WIFI_STA);

    // Disable Wi-Fi sleep for lower latency.
    WiFi.setSleep(false);

    WiFi.setTxPower(WIFI_POWER_19_5dBm);

    Serial.println();
    Serial.print("Connecting to Wi-Fi: ");
    Serial.println(ssid);

    WiFi.begin(ssid, password);

    unsigned long startTime = millis();

    while (WiFi.status() != WL_CONNECTED)
    {
        delay(250);

        Serial.print(".");

        if (millis() - startTime > 20000)
        {
            Serial.println();
            Serial.println("Wi-Fi connection timeout.");

            return false;
        }
    }

    Serial.println();
    Serial.println("Wi-Fi connected.");

    Serial.print("RSSI: ");
    Serial.print(WiFi.RSSI());
    Serial.println(" dBm");

    Serial.print("ESP32-CAM IP: ");
    Serial.println(WiFi.localIP());

    return true;
}


// =====================================================
// WEB PAGE
// =====================================================

void sendWebPage(WiFiClient& client)
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

        "<title>ESP32-CAM</title>"

        "</head>"

        "<body style='"
        "margin:0;"
        "background:#000;"
        "text-align:center;"
        "'>"

        "<h2 style='color:white;'>ESP32-CAM LIVE</h2>"

        "<img src='/stream' "
        "style='"
        "max-width:100%;"
        "height:auto;"
        "'>"

        "</body>"
        "</html>"
    );
}


// =====================================================
// MJPEG STREAM
// =====================================================

void streamCamera(WiFiClient& client)
{
    client.setNoDelay(true);
    client.setTimeout(2000);


    // =================================================
    // HTTP MJPEG HEADER
    // =================================================

    client.print(
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: multipart/x-mixed-replace; boundary=frame\r\n"
        "Cache-Control: no-cache, no-store, must-revalidate\r\n"
        "Pragma: no-cache\r\n"
        "Connection: keep-alive\r\n"
        "\r\n"
    );


    // =================================================
    // CONTINUOUS STREAM
    // =================================================

    while (client.connected())
    {
        camera_fb_t* frame = esp_camera_fb_get();

        if (frame == nullptr)
        {
            Serial.println("Camera frame capture failed.");

            delay(1);

            continue;
        }


        // ---------------------------------------------
        // MJPEG FRAME HEADER
        // ---------------------------------------------

        client.print("--frame\r\n");

        client.print(
            "Content-Type: image/jpeg\r\n"
        );

        client.print("Content-Length: ");
        client.print(frame->len);

        client.print("\r\n\r\n");


        // ---------------------------------------------
        // SEND JPEG
        // ---------------------------------------------

        bool success = sendAll(
            client,
            frame->buf,
            frame->len
        );


        client.print("\r\n");


        // ---------------------------------------------
        // RETURN CAMERA BUFFER
        // ---------------------------------------------

        esp_camera_fb_return(frame);


        if (!success)
        {
            break;
        }
    }
}


// =====================================================
// SETUP
// =====================================================

void setup()
{
    Serial.begin(115200);

    delay(1000);

    Serial.println();
    Serial.println("================================");
    Serial.println("       ESP32-CAM SERVER");
    Serial.println("================================");


    // =================================================
    // CAMERA
    // =================================================

    if (!initializeCamera())
    {
        Serial.println("Camera initialization failed.");

        while (true)
        {
            delay(1000);
        }
    }


    // =================================================
    // WIFI
    // =================================================

    if (!initializeWiFi())
    {
        Serial.println("Wi-Fi initialization failed.");

        while (true)
        {
            delay(1000);
        }
    }


    // =================================================
    // SERVER
    // =================================================

    server.begin();


    Serial.println();
    Serial.println("================================");
    Serial.println("          SERVER READY");
    Serial.println("================================");

    Serial.print("Web page: http://");
    Serial.println(WiFi.localIP());

    Serial.print("Stream:   http://");
    Serial.print(WiFi.localIP());
    Serial.println("/stream");

    Serial.println("================================");
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


    // =================================================
    // READ HTTP REQUEST
    // =================================================

    String request;

    unsigned long startTime = millis();

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


    // =================================================
    // ROUTE
    // =================================================

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