#pragma once

#include <sys/time.h>

#if APRIS_ROVER_ENABLED

namespace AprisRover {

constexpr char FIRMWARE_VERSION[] = "0.97-apris-ws-dev";
constexpr char BUILD_ID[] = "ugv02-smooth-apris-v1";
constexpr char HARDWARE_REVISION[] = "waveshare-ugv02-esp32";
constexpr float MAX_LINEAR_SPEED_MPS = 0.08f;
constexpr float MAX_ANGULAR_SPEED_RAD_S = 0.70f;
constexpr float MAX_DISTANCE_M = 0.50f;
constexpr float MAX_ANGLE_RAD = 3.141593f;
constexpr uint32_t MAX_MOTION_DURATION_MS = 10000;
constexpr uint32_t MAX_LEASE_MS = 1000;
constexpr uint32_t TELEMETRY_INTERVAL_MS = 200;
constexpr uint32_t RECONNECT_INTERVAL_MS = 2000;
constexpr uint32_t NTP_RETRY_INTERVAL_MS = 10000;
constexpr uint64_t MIN_VALID_EPOCH_MS = 1700000000000ULL;
constexpr size_t MOTION_HISTORY_SIZE = 8;

WebSocketsClient socket;
String authorizationHeader;
String bootId;
String connectionEpoch;
int64_t roverSequence = -1;
int64_t lastServerSequence = -1;
uint32_t heartbeatIntervalMs = 500;
uint32_t lastHeartbeatAt = 0;
uint32_t lastTelemetryAt = 0;
uint32_t lastNtpAttemptAt = 0;
bool welcomed = false;
bool clockHealthy = false;

double poseX = 0;
double poseY = 0;
double poseYaw = 0;
double previousOdomLeft = 0;
double previousOdomRight = 0;

bool velocityActive = false;
uint32_t velocityLeaseDeadline = 0;

struct Motion {
  bool active = false;
  String id;
  String kind;
  double target = 0;
  double maximumLinearSpeed = 0;
  double maximumAngularSpeed = 0;
  uint32_t maximumDuration = 0;
  uint32_t lease = 0;
  String runId;
  String effectId;
  String requestId;
  double startLeft = 0;
  double startRight = 0;
  uint32_t leaseDeadline = 0;
  uint32_t durationDeadline = 0;
};

struct MotionRecord {
  bool valid = false;
  String id;
  String kind;
  double target = 0;
  double maximumLinearSpeed = 0;
  double maximumAngularSpeed = 0;
  uint32_t maximumDuration = 0;
  uint32_t lease = 0;
  String runId;
  String effectId;
  String requestId;
  String status;
  String reason;
  double progress = 0;
};

Motion motion;
MotionRecord motionHistory[MOTION_HISTORY_SIZE];
size_t nextMotionHistoryIndex = 0;

uint64_t epochMillis() {
  timeval now;
  gettimeofday(&now, nullptr);
  return static_cast<uint64_t>(now.tv_sec) * 1000ULL
    + static_cast<uint64_t>(now.tv_usec) / 1000ULL;
}

bool deadlineReached(uint32_t now, uint32_t deadline) {
  return static_cast<int32_t>(now - deadline) >= 0;
}

void sendDocument(JsonDocument &document) {
  if (!welcomed || !socket.isConnected()) return;
  String payload;
  serializeJson(document, payload);
  socket.sendTXT(payload);
}

void addSessionFields(JsonDocument &document, const char *type) {
  document["v"] = 1;
  document["type"] = type;
  document["rover_id"] = APRIS_ROVER_ID;
  document["boot_id"] = bootId;
  document["connection_epoch"] = connectionEpoch;
  document["seq"] = ++roverSequence;
}

void sendHello() {
  StaticJsonDocument<768> document;
  document["v"] = 1;
  document["type"] = "rover_hello";
  JsonArray versions = document.createNestedArray("protocol_versions");
  versions.add(1);
  document["rover_id"] = APRIS_ROVER_ID;
  document["boot_id"] = bootId;
  document["firmware_version"] = FIRMWARE_VERSION;
  document["build_id"] = BUILD_ID;
  document["hardware_revision"] = HARDWARE_REVISION;
  JsonObject capabilities = document.createNestedObject("capabilities");
  capabilities["bounded_motion"] = true;
  capabilities["velocity_control"] = true;
  capabilities["encoders"] = true;
  capabilities["imu"] = false;
  capabilities["battery"] = false;
  JsonObject limits = document.createNestedObject("safety_limits");
  limits["max_linear_speed_mps"] = MAX_LINEAR_SPEED_MPS;
  limits["max_angular_speed_rad_s"] = MAX_ANGULAR_SPEED_RAD_S;
  limits["max_distance_m"] = MAX_DISTANCE_M;
  limits["max_angle_rad"] = MAX_ANGLE_RAD;
  limits["max_motion_duration_ms"] = MAX_MOTION_DURATION_MS;
  limits["max_lease_ms"] = MAX_LEASE_MS;
  String payload;
  serializeJson(document, payload);
  socket.sendTXT(payload);
}

void sendAck(
  const String &commandId,
  bool accepted,
  const char *code = nullptr,
  const char *detail = ""
) {
  StaticJsonDocument<640> document;
  addSessionFields(document, "command_ack");
  document["command_id"] = commandId;
  document["status"] = accepted ? "accepted" : "rejected";
  if (accepted) {
    document["code"] = nullptr;
  } else {
    document["code"] = code == nullptr ? "command_rejected" : code;
  }
  document["detail"] = detail;
  sendDocument(document);
}

void sendEvent(const char *event, const char *detail) {
  StaticJsonDocument<640> document;
  addSessionFields(document, "rover_event");
  document["event"] = event;
  document["detail"] = detail;
  sendDocument(document);
}

void sendMotionStatus(
  const String &motionId,
  const char *status,
  double progress,
  const char *reason,
  bool stopped
) {
  StaticJsonDocument<768> document;
  addSessionFields(document, "motion_status");
  document["motion_id"] = motionId;
  document["status"] = status;
  document["progress"] = progress;
  if (reason == nullptr || strlen(reason) == 0) {
    document["reason"] = nullptr;
  } else {
    document["reason"] = reason;
  }
  document["motor_stopped"] = stopped;
  sendDocument(document);
}

void refreshMotorWatchdog() {
  heartbeatStopFlag = false;
  lastCmdRecvTime = millis();
}

void stopMotor() {
  setGoalSpeed(0, 0);
  outputA = 0;
  outputB = 0;
  switchEmergencyStop();
  velocityActive = false;
  heartbeatStopFlag = true;
}

double motionTravel() {
  const double left = en_odom_l - motion.startLeft;
  const double right = en_odom_r - motion.startRight;
  if (motion.kind == "linear") return (left + right) / 2.0;
  return (right - left) / TRACK_WIDTH;
}

double motionProgress() {
  const double target = fabs(motion.target);
  if (target <= 1e-9) return 0.0;
  const double progress = fabs(motionTravel()) / target;
  return progress > 1.0 ? 1.0 : progress;
}

void copyMotionIdentity(MotionRecord &record) {
  record.valid = true;
  record.id = motion.id;
  record.kind = motion.kind;
  record.target = motion.target;
  record.maximumLinearSpeed = motion.maximumLinearSpeed;
  record.maximumAngularSpeed = motion.maximumAngularSpeed;
  record.maximumDuration = motion.maximumDuration;
  record.lease = motion.lease;
  record.runId = motion.runId;
  record.effectId = motion.effectId;
  record.requestId = motion.requestId;
}

MotionRecord *findMotionRecord(const String &motionId) {
  for (size_t index = 0; index < MOTION_HISTORY_SIZE; ++index) {
    if (motionHistory[index].valid && motionHistory[index].id == motionId) {
      return &motionHistory[index];
    }
  }
  return nullptr;
}

bool sameMotionRequest(const MotionRecord &record, JsonDocument &document) {
  const String kind = document["kind"] | "";
  const double target = kind == "linear"
    ? document["distance_m"].as<double>()
    : document["angle_rad"].as<double>();
  return record.kind == kind
    && fabs(record.target - target) <= 1e-6
    && fabs(record.maximumLinearSpeed - document["max_linear_speed_mps"].as<double>()) <= 1e-6
    && fabs(record.maximumAngularSpeed - document["max_angular_speed_rad_s"].as<double>()) <= 1e-6
    && record.maximumDuration == document["max_duration_ms"].as<uint32_t>()
    && record.lease == document["lease_ms"].as<uint32_t>()
    && record.runId == String(document["run_id"] | "")
    && record.effectId == String(document["effect_id"] | "")
    && record.requestId == String(document["request_id"] | "");
}

bool sameActiveMotionRequest(JsonDocument &document) {
  MotionRecord active;
  copyMotionIdentity(active);
  return sameMotionRequest(active, document);
}

void rememberTerminal(const char *status, const char *reason, double progress) {
  MotionRecord &record = motionHistory[nextMotionHistoryIndex];
  copyMotionIdentity(record);
  record.status = status;
  record.reason = reason == nullptr ? "" : reason;
  record.progress = progress;
  nextMotionHistoryIndex = (nextMotionHistoryIndex + 1) % MOTION_HISTORY_SIZE;
}

void sendRecordedMotion(const MotionRecord &record) {
  sendMotionStatus(
    record.id,
    record.status.c_str(),
    record.progress,
    record.reason.length() == 0 ? nullptr : record.reason.c_str(),
    true
  );
}

void terminateMotion(const char *status, const char *reason, bool transmit = true) {
  if (!motion.active) return;
  const String id = motion.id;
  const double progress = motionProgress();
  stopMotor();
  rememberTerminal(status, reason, progress);
  motion.active = false;
  if (transmit) sendMotionStatus(id, status, progress, reason, true);
}

void sendHeartbeat() {
  StaticJsonDocument<768> document;
  addSessionFields(document, "heartbeat");
  document["sent_at_ms"] = epochMillis();
  document["clock_offset_ms"] = 0.0;
  document["clock_uncertainty_ms"] = clockHealthy ? 50.0 : 10000.0;
  document["motor_state"] = motorEmergencyStopActive ? "fault"
    : (motion.active || velocityActive ? "moving" : "stopped");
  document["estop_latched"] = motorEmergencyStopActive;
  if (motion.active) {
    document["active_motion_id"] = motion.id;
  } else {
    document["active_motion_id"] = nullptr;
  }
  sendDocument(document);
}

void updatePose() {
  const double deltaLeft = en_odom_l - previousOdomLeft;
  const double deltaRight = en_odom_r - previousOdomRight;
  previousOdomLeft = en_odom_l;
  previousOdomRight = en_odom_r;
  const double distance = (deltaLeft + deltaRight) / 2.0;
  const double deltaYaw = (deltaRight - deltaLeft) / TRACK_WIDTH;
  const double midpointYaw = poseYaw + deltaYaw / 2.0;
  poseX += distance * cos(midpointYaw);
  poseY += distance * sin(midpointYaw);
  poseYaw = atan2(sin(poseYaw + deltaYaw), cos(poseYaw + deltaYaw));
}

void sendTelemetry() {
  updatePose();
  StaticJsonDocument<896> document;
  addSessionFields(document, "telemetry");
  document["measured_at_ms"] = epochMillis();
  document["linear_velocity_mps"] = (speedGetA + speedGetB) / 2.0;
  document["angular_velocity_rad_s"] = (speedGetB - speedGetA) / TRACK_WIDTH;
  document["odometry_x_m"] = poseX;
  document["odometry_y_m"] = poseY;
  document["odometry_yaw_rad"] = poseYaw;
  document["battery_percent"] = nullptr;
  document["motor_state"] = motorEmergencyStopActive ? "fault"
    : (motion.active || velocityActive ? "moving" : "stopped");
  JsonArray faults = document.createNestedArray("fault_codes");
  if (!clockHealthy) faults.add("clock_unsynchronized");
  if (motorEmergencyStopActive) faults.add("estop_latched");
  sendDocument(document);
}

void reject(const String &commandId, const char *code, const char *detail) {
  sendAck(commandId, false, code, detail);
}

bool validateEnvelope(JsonDocument &document, const String &type, String &commandId) {
  commandId = document["command_id"] | "";
  if (document["v"].as<int>() != 1
      || type.length() == 0
      || commandId.length() == 0
      || !document["seq"].is<int64_t>()
      || !document["issued_at_ms"].is<uint64_t>()
      || !document["ttl_ms"].is<uint32_t>()) {
    if (commandId.length() > 0) {
      reject(commandId, "invalid_command_envelope", "required command fields are invalid");
    } else {
      sendEvent("invalid_server_message", "command envelope is missing command_id");
    }
    return false;
  }
  const String epoch = document["connection_epoch"] | "";
  const int64_t sequence = document["seq"].as<int64_t>();
  if (epoch != connectionEpoch) {
    reject(commandId, "stale_connection_epoch", "connection epoch does not match");
    return false;
  }
  if (sequence <= lastServerSequence) {
    reject(commandId, "non_increasing_server_sequence", "server sequence must increase");
    return false;
  }
  lastServerSequence = sequence;
  if (!clockHealthy) {
    if (type == "stop" || type == "estop" || type == "cancel_motion") return true;
    reject(commandId, "clock_unsynchronized", "firmware clock is not synchronized");
    return false;
  }
  const uint64_t issuedAt = document["issued_at_ms"].as<uint64_t>();
  const uint32_t ttl = document["ttl_ms"].as<uint32_t>();
  const uint64_t now = epochMillis();
  if (ttl < 50 || ttl > 2000 || now > issuedAt + ttl || issuedAt > now + 100) {
    reject(commandId, "command_expired", "command freshness window is invalid");
    return false;
  }
  return true;
}

void startMotion(JsonDocument &document, const String &commandId) {
  const String id = document["motion_id"] | "";
  const String kind = document["kind"] | "";
  const double target = kind == "linear"
    ? document["distance_m"].as<double>()
    : document["angle_rad"].as<double>();
  if (id.length() == 0 || (kind != "linear" && kind != "rotate") || fabs(target) < 1e-9) {
    reject(commandId, "invalid_motion", "motion target is invalid");
    return;
  }
  if (motion.active && id == motion.id) {
    if (!sameActiveMotionRequest(document)) {
      reject(commandId, "motion_id_conflict", "motion id was used with another target");
      return;
    }
    sendAck(commandId, true);
    sendMotionStatus(id, "running", motionProgress(), nullptr, false);
    return;
  }
  MotionRecord *known = findMotionRecord(id);
  if (known != nullptr) {
    if (!sameMotionRequest(*known, document)) {
      reject(commandId, "motion_id_conflict", "motion id was used with another target");
      return;
    }
    sendAck(commandId, true);
    sendRecordedMotion(*known);
    return;
  }
  if (motorEmergencyStopActive) {
    reject(commandId, "estop_latched", "emergency stop is latched");
    return;
  }
  if (motion.active || velocityActive) {
    reject(commandId, "control_mode_busy", "another motion mode is active");
    return;
  }
  const double maximumLinear = document["max_linear_speed_mps"].as<double>();
  const double maximumAngular = document["max_angular_speed_rad_s"].as<double>();
  const uint32_t maximumDuration = document["max_duration_ms"].as<uint32_t>();
  const uint32_t lease = document["lease_ms"].as<uint32_t>();
  const double targetLimit = kind == "linear" ? MAX_DISTANCE_M : MAX_ANGLE_RAD;
  if (fabs(target) > targetLimit
      || maximumLinear <= 0 || maximumLinear > MAX_LINEAR_SPEED_MPS
      || maximumAngular <= 0 || maximumAngular > MAX_ANGULAR_SPEED_RAD_S
      || maximumDuration < 100 || maximumDuration > MAX_MOTION_DURATION_MS
      || lease < 100 || lease > MAX_LEASE_MS) {
    reject(commandId, "firmware_limit_exceeded", "motion exceeds firmware safety limits");
    return;
  }

  motion.active = true;
  motion.id = id;
  motion.kind = kind;
  motion.target = target;
  motion.maximumLinearSpeed = maximumLinear;
  motion.maximumAngularSpeed = maximumAngular;
  motion.maximumDuration = maximumDuration;
  motion.lease = lease;
  motion.runId = String(document["run_id"] | "");
  motion.effectId = String(document["effect_id"] | "");
  motion.requestId = String(document["request_id"] | "");
  motion.startLeft = en_odom_l;
  motion.startRight = en_odom_r;
  motion.leaseDeadline = millis() + lease;
  motion.durationDeadline = millis() + maximumDuration;
  refreshMotorWatchdog();
  if (kind == "linear") {
    rosCtrl(target > 0 ? maximumLinear : -maximumLinear, 0);
  } else {
    rosCtrl(0, target > 0 ? maximumAngular : -maximumAngular);
  }
  sendAck(commandId, true);
  sendMotionStatus(id, "running", 0.0, nullptr, false);
}

void renewMotionLease(JsonDocument &document, const String &commandId) {
  const String id = document["motion_id"] | "";
  const uint32_t lease = document["lease_ms"].as<uint32_t>();
  if (!motion.active || id != motion.id) {
    MotionRecord *known = findMotionRecord(id);
    if (known == nullptr) {
      reject(commandId, "unknown_motion_id", "motion id is unknown");
    } else {
      reject(commandId, "motion_already_terminal", "motion is already terminal");
      sendRecordedMotion(*known);
    }
    return;
  }
  if (lease < 100 || lease > MAX_LEASE_MS) {
    reject(commandId, "firmware_limit_exceeded", "lease exceeds firmware limit");
    return;
  }
  motion.leaseDeadline = millis() + lease;
  refreshMotorWatchdog();
  sendAck(commandId, true);
}

void cancelMotion(JsonDocument &document, const String &commandId) {
  const String id = document["motion_id"] | "";
  if (motion.active && id == motion.id) {
    sendAck(commandId, true);
    const String reason = document["reason"] | "server_cancelled";
    terminateMotion("cancelled", reason.c_str());
    return;
  }
  MotionRecord *known = findMotionRecord(id);
  if (known != nullptr) {
    sendAck(commandId, true);
    sendRecordedMotion(*known);
    return;
  }
  reject(commandId, "unknown_motion_id", "motion id is unknown");
}

void setVelocity(JsonDocument &document, const String &commandId) {
  const double linear = document["linear_velocity_mps"].as<double>();
  const double angular = document["angular_velocity_rad_s"].as<double>();
  const uint32_t lease = document["lease_ms"].as<uint32_t>();
  if (motorEmergencyStopActive) {
    reject(commandId, "estop_latched", "emergency stop is latched");
    return;
  }
  if (motion.active) {
    reject(commandId, "control_mode_busy", "bounded motion is active");
    return;
  }
  if (fabs(linear) > MAX_LINEAR_SPEED_MPS
      || fabs(angular) > MAX_ANGULAR_SPEED_RAD_S
      || lease < 100 || lease > MAX_LEASE_MS) {
    reject(commandId, "firmware_limit_exceeded", "velocity exceeds firmware limits");
    return;
  }
  rosCtrl(linear, angular);
  velocityActive = fabs(linear) > 1e-6 || fabs(angular) > 1e-6;
  velocityLeaseDeadline = millis() + lease;
  refreshMotorWatchdog();
  sendAck(commandId, true);
}

void handleCommand(JsonDocument &document) {
  const String type = document["type"] | "";
  String commandId;
  if (!validateEnvelope(document, type, commandId)) return;
  if (type == "start_motion") {
    startMotion(document, commandId);
  } else if (type == "renew_motion_lease") {
    renewMotionLease(document, commandId);
  } else if (type == "cancel_motion") {
    cancelMotion(document, commandId);
  } else if (type == "set_velocity") {
    setVelocity(document, commandId);
  } else if (type == "stop") {
    sendAck(commandId, true);
    if (motion.active) terminateMotion("cancelled", "server_stop");
    else stopMotor();
  } else if (type == "estop") {
    if (motion.active) terminateMotion("cancelled", "estop");
    setMotorEmergencyStop();
    velocityActive = false;
    sendAck(commandId, true);
    sendEvent("estop_latched", "motor emergency stop latched");
  } else if (type == "clear_estop") {
    resetMotorEmergencyStop();
    sendAck(commandId, true);
    sendEvent("estop_cleared", "motion remains stopped");
  } else {
    reject(commandId, "unknown_command", "unsupported command type");
  }
}

void handleText(uint8_t *payload, size_t length) {
  StaticJsonDocument<2048> document;
  DeserializationError error = deserializeJson(document, payload, length);
  if (error) {
    sendEvent("invalid_server_message", error.c_str());
    return;
  }
  const String type = document["type"] | "";
  if (!welcomed) {
    if (type != "rover_welcome") {
      stopMotor();
      socket.disconnect();
      return;
    }
    const String roverId = document["rover_id"] | "";
    const String receivedBootId = document["boot_id"] | "";
    const String epoch = document["connection_epoch"] | "";
    if (roverId != APRIS_ROVER_ID || receivedBootId != bootId || epoch.length() == 0) {
      stopMotor();
      socket.disconnect();
      return;
    }
    connectionEpoch = epoch;
    heartbeatIntervalMs = constrain(document["heartbeat_interval_ms"].as<uint32_t>(), 100, 10000);
    roverSequence = -1;
    lastServerSequence = -1;
    welcomed = true;
    lastHeartbeatAt = 0;
    lastTelemetryAt = 0;
    sendEvent("rover_ready", "APRIS Rover protocol v1 active");
    return;
  }
  if (type == "rover_error") {
    stopMotor();
    socket.disconnect();
    return;
  }
  handleCommand(document);
}

void socketEvent(WStype_t type, uint8_t *payload, size_t length) {
  switch (type) {
    case WStype_CONNECTED:
      welcomed = false;
      connectionEpoch = "";
      roverSequence = -1;
      lastServerSequence = -1;
      sendHello();
      break;
    case WStype_TEXT:
      handleText(payload, length);
      break;
    case WStype_DISCONNECTED:
    case WStype_ERROR:
      if (motion.active) terminateMotion("cancelled", "websocket_disconnected", false);
      stopMotor();
      welcomed = false;
      connectionEpoch = "";
      break;
    default:
      break;
  }
}

void controlMotion(uint32_t now) {
  if (velocityActive && deadlineReached(now, velocityLeaseDeadline)) {
    stopMotor();
    sendEvent("velocity_lease_expired", "motor stopped");
  }
  if (!motion.active) return;
  if (deadlineReached(now, motion.durationDeadline)) {
    terminateMotion("failed", "max_duration_expired");
    return;
  }
  if (deadlineReached(now, motion.leaseDeadline)) {
    terminateMotion("cancelled", "motion_lease_expired");
    return;
  }
  refreshMotorWatchdog();
  const double target = fabs(motion.target);
  if (target > 1e-9 && fabs(motionTravel()) >= target) {
    terminateMotion("completed", nullptr);
  }
}

void updateClock(uint32_t now) {
  clockHealthy = epochMillis() >= MIN_VALID_EPOCH_MS;
  if (!clockHealthy && (lastNtpAttemptAt == 0 || now - lastNtpAttemptAt >= NTP_RETRY_INTERVAL_MS)) {
    configTime(0, 0, "pool.ntp.org", "time.cloudflare.com");
    lastNtpAttemptAt = now;
  }
}

void begin() {
  const uint64_t chipId = ESP.getEfuseMac();
  bootId = String(static_cast<uint32_t>(chipId >> 32), HEX)
    + String(static_cast<uint32_t>(chipId), HEX)
    + "-" + String(esp_random(), HEX);
  previousOdomLeft = en_odom_l;
  previousOdomRight = en_odom_r;
  authorizationHeader = "Authorization: Bearer ";
  authorizationHeader += APRIS_ROVER_TOKEN;
  authorizationHeader += "\r\n";
  socket.setExtraHeaders(authorizationHeader.c_str());
  socket.onEvent(socketEvent);
  socket.setReconnectInterval(RECONNECT_INTERVAL_MS);
  socket.enableHeartbeat(15000, 3000, 2);
  configTime(0, 0, "pool.ntp.org", "time.cloudflare.com");
  lastNtpAttemptAt = millis();
  socket.begin(APRIS_SERVER_HOST, APRIS_SERVER_PORT, APRIS_SERVER_PATH);
}

void loop() {
  const uint32_t now = millis();
  updateClock(now);
  socket.loop();
  controlMotion(now);
  if (!welcomed) return;
  if (lastHeartbeatAt == 0 || now - lastHeartbeatAt >= heartbeatIntervalMs) {
    lastHeartbeatAt = now;
    sendHeartbeat();
  }
  if (lastTelemetryAt == 0 || now - lastTelemetryAt >= TELEMETRY_INTERVAL_MS) {
    lastTelemetryAt = now;
    sendTelemetry();
  }
}

}  // namespace AprisRover

void initAprisRover() {
  AprisRover::begin();
}

void aprisRoverLoop() {
  AprisRover::loop();
}

#else

void initAprisRover() {}
void aprisRoverLoop() {}

#endif
