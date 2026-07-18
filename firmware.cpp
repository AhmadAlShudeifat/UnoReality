#include <Arduino.h>
#include <Wire.h>
#include "esp_camera.h"
#include <ETH.h>

WiFiServer masterServer(6738);
WiFiClient client;

const int SCL_PIN = 21;
const int SDA_PIN = 22;
const int MPU = 0x68;

int on = 0;
const int hmd = 0;
const float to = 0.0;

float x = 0, y = 0, z = 0;
float qx = 0, qy = 0, qz = 0, qw = 1;

unsigned long lastTime = 0;
float dt = 0;

#define Kp 2.0f
#define Ki 0.005f

TaskHandle_t trackingHandle;
TaskHandle_t cameraHandle;
TaskHandle_t networkHandle;

struct TrackData {
  int on;
  float x, y, z;
  float qx, qy, qz, qw;
};

volatile TrackData latest;

bool init_camera() {
  camera_config_t config;
  config.mipi_csi.lane_num = 2;
  config.mipi_csi.lane_bitrate = 800000000;
  config.mipi_csi.sccb_i2c_num = 1;
  config.pin_sscb_sda = 7;
  config.pin_sscb_scl = 8;
  config.pin_pwdn = -1;
  config.pin_reset = -1;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_QVGA;
  config.jpeg_quality = 10;
  config.fb_count = 2;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  return esp_camera_init(&config) == ESP_OK;
}

void trackingTask(void*) {
  float eIx = 0, eIy = 0, eIz = 0;

  while (true) {
    Wire.beginTransmission(MPU);
    Wire.write(0x75);
    if (Wire.endTransmission(false) == 0) {
      Wire.requestFrom(MPU, 1, true);
      on = (Wire.read() == 0x68);
    } else {
      on = 0;
    }

    if (on) {
      Wire.beginTransmission(MPU);
      Wire.write(0x3B);
      Wire.endTransmission(false);
      Wire.requestFrom(MPU, 14, true);

      if (Wire.available() >= 14) {
        float ax = (int16_t)((Wire.read() << 8) | Wire.read()) / 16384.0f;
        float ay = (int16_t)((Wire.read() << 8) | Wire.read()) / 16384.0f;
        float az = (int16_t)((Wire.read() << 8) | Wire.read()) / 16384.0f;

        Wire.read(); Wire.read();

        float gx = ((int16_t)((Wire.read() << 8) | Wire.read()) / 32.8f) * (PI / 180.0f);
        float gy = ((int16_t)((Wire.read() << 8) | Wire.read()) / 32.8f) * (PI / 180.0f);
        float gz = ((int16_t)((Wire.read() << 8) | Wire.read()) / 32.8f) * (PI / 180.0f);

        float norm = 1.0f / sqrt(ax * ax + ay * ay + az * az);
        ax *= norm; ay *= norm; az *= norm;

        float vx = qx * qz - qw * qy;
        float vy = qw * qx + qy * qz;
        float vz = qw * qw - 0.5f + qz * qz;

        float ex = (ay * vz - az * vy);
        float ey = (az * vx - ax * vz);
        float ez = (ax * vy - ay * vx);

        eIx += ex * Ki;
        eIy += ey * Ki;
        eIz += ez * Ki;

        gx += Kp * ex + eIx;
        gy += Kp * ey + eIy;
        gz += Kp * ez + eIz;

        float qa = qw, qb = qx, qc = qy;

        qw += (-qb * gx - qc * gy - qz * gz) * 0.5f;
        qx += (qa * gx + qc * qz - qz * gy) * 0.5f;
        qy += (qa * gy - qb * qz + qz * gx) * 0.5f;
        qz += (qa * gz + qb * gy - qc * gx) * 0.5f;

        norm = 1.0f / sqrt(qw * qw + qx * qx + qy * qy + qz * qz);
        qw *= norm; qx *= norm; qy *= norm; qz *= norm;

        latest.on = on;
        latest.x = x;
        latest.y = y;
        latest.z = z;
        latest.qx = qx;
        latest.qy = qy;
        latest.qz = qz;
        latest.qw = qw;
      }
    }

    vTaskDelay(1);
  }
}

void cameraTask(void*) {
  while (true) {
    camera_fb_t* fb = esp_camera_fb_get();
    if (fb) {
      if (client.connected()) {
        client.write('V');
        client.write(fb->buf, fb->len);
      }
      esp_camera_fb_return(fb);
    }
    vTaskDelay(33);
  }
}

void networkTask(void*) {
  while (true) {
    if (!client || !client.connected()) {
      client = masterServer.available();
      vTaskDelay(10);
      continue;
    }

    client.print("[");
    client.print(latest.on); client.print(",");
    client.print(hmd); client.print(",");
    client.print(to, 4); client.print(",");
    client.print(latest.x, 4); client.print(",");
    client.print(latest.y, 4); client.print(",");
    client.print(latest.z, 4); client.print(",");
    client.print(latest.qx, 4); client.print(",");
    client.print(latest.qy, 4); client.print(",");
    client.print(latest.qz, 4); client.print(",");
    client.print(latest.qw, 4);
    client.println("]");

    vTaskDelay(1);
  }
}

void setup() {
  Serial.begin(2000000);
  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(400000);

  Wire.beginTransmission(MPU);
  Wire.write(0x6B);
  Wire.write(0);
  Wire.endTransmission(true);

  Wire.beginTransmission(MPU);
  Wire.write(0x1B);
  Wire.write(0x10);
  Wire.endTransmission(true);

  Wire.beginTransmission(MPU);
  Wire.write(0x1C);
  Wire.write(0);
  Wire.endTransmission(true);

  ETH.begin();
  ETH.config(IPAddress(192,168,1,50), IPAddress(192,168,1,1), IPAddress(255,255,255,0));
  masterServer.begin();

  init_camera();

  xTaskCreatePinnedToCore(trackingTask, "tracking", 10000, NULL, 3, &trackingHandle, 0);
  xTaskCreatePinnedToCore(cameraTask, "camera", 10000, NULL, 1, &cameraHandle, 1);
  xTaskCreatePinnedToCore(networkTask, "network", 10000, NULL, 2, &networkHandle, 1);
}

void loop() {
  vTaskDelay(1000);
}