#pragma once

void aprisSerialStatus() {
  StaticJsonDocument<384> status;
  status["T"] = FEEDBACK_BASE_INFO;
  status["L"] = speedGetA;
  status["R"] = speedGetB;
  status["estop"] = motorEmergencyStopActive;
  status["odl"] = en_odom_l;
  status["odr"] = en_odom_r;
  status["v"] = static_cast<int>(loadVoltage_V * 100);
  status["ip"] = WiFi.localIP().toString();
  serializeJson(status, Serial);
  Serial.println();
}

void aprisSerialError(const char *detail) {
  StaticJsonDocument<160> error;
  error["error"] = detail;
  serializeJson(error, Serial);
  Serial.println();
}

void aprisSerialCommandHandler() {
  const int command = jsonCmdReceive["T"] | -1;
  switch (command) {
    case CMD_EMERGENCY_STOP:
      setMotorEmergencyStop();
      break;
    case CMD_RESET_EMERGENCY:
      resetMotorEmergencyStop();
      break;
    case CMD_BASE_FEEDBACK:
      aprisSerialStatus();
      break;
    case CMD_WIFI_ON_BOOT:
      setMotorEmergencyStop();
      configWifiModeOnBoot(jsonCmdReceive["cmd"] | 0);
      break;
    case CMD_SET_AP:
      setMotorEmergencyStop();
      wifiModeAP(jsonCmdReceive["ssid"] | "UGV", jsonCmdReceive["password"] | "12345678");
      break;
    case CMD_SET_STA:
      setMotorEmergencyStop();
      wifiModeSTA(jsonCmdReceive["ssid"] | "", jsonCmdReceive["password"] | "");
      break;
    case CMD_WIFI_APSTA:
      setMotorEmergencyStop();
      wifiModeAPSTA(
        jsonCmdReceive["ap_ssid"] | "UGV",
        jsonCmdReceive["ap_password"] | "12345678",
        jsonCmdReceive["sta_ssid"] | "",
        jsonCmdReceive["sta_password"] | ""
      );
      break;
    case CMD_WIFI_INFO:
      wifiStatusFeedback();
      break;
    case CMD_WIFI_CONFIG_CREATE_BY_STATUS:
      setMotorEmergencyStop();
      createWifiConfigFileByStatus();
      break;
    case CMD_WIFI_CONFIG_CREATE_BY_INPUT:
      setMotorEmergencyStop();
      createWifiConfigFileByInput(
        jsonCmdReceive["mode"] | 1,
        jsonCmdReceive["ap_ssid"] | "UGV",
        jsonCmdReceive["ap_password"] | "12345678",
        jsonCmdReceive["sta_ssid"] | "",
        jsonCmdReceive["sta_password"] | ""
      );
      break;
    case CMD_WIFI_STOP:
      setMotorEmergencyStop();
      wifiStop();
      break;
    case CMD_REBOOT:
      setMotorEmergencyStop();
      delay(100);
      esp_restart();
      break;
    default:
      aprisSerialError("unsupported_command");
      break;
  }
}

void serialCtrl() {
  static String receivedData;
  while (Serial.available() > 0) {
    const char receivedChar = Serial.read();
    if (receivedChar == '\n') {
      DeserializationError error = deserializeJson(jsonCmdReceive, receivedData);
      if (error == DeserializationError::Ok) {
        aprisSerialCommandHandler();
      } else {
        aprisSerialError("invalid_json");
      }
      jsonCmdReceive.clear();
      receivedData = "";
    } else if (receivedData.length() < 512) {
      receivedData += receivedChar;
    } else {
      receivedData = "";
      aprisSerialError("command_too_long");
    }
  }
}
