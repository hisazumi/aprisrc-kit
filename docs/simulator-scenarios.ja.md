# Simulator scenarios, fault injection, and logs

[English](simulator-scenarios.md)

Simulatorは、実機がない場合の画面確認だけでなく、同じ入力と異常を繰り返して安全制御とサービスを検証するための標準コンポーネントである。開発用の操作はDevelopment Lab (`/lab`) の`Simulator Tools`に集約する。Service App (`/app`) とOperator Console (`/console`) には表示しない。

## Scenario files

再現可能な入力は`apps/server/scenarios/*.json`へ保存する。Local Serverは起動時にすべてのファイルを読み込み、IDの重複、時刻順、型、値の範囲を検証する。

```json
{
  "id": "perception-inputs",
  "name": "Perception input sequence",
  "description": "Inject reproducible service inputs.",
  "actions": [
    {
      "at_ms": 0,
      "type": "event",
      "kind": "person",
      "payload": {
        "status": "detected",
        "confidence": 0.94,
        "person_id": "demo-person",
        "center_x": 0.5,
        "center_y": 0.5,
        "width": 0.2,
        "height": 0.5
      }
    },
    {
      "at_ms": 600,
      "type": "event",
      "kind": "marker",
      "payload": {
        "status": "detected",
        "confidence": 0.9,
        "marker_id": 1,
        "relative_x_m": 0.5,
        "relative_y_m": 0.0
      }
    },
    {
      "at_ms": 1200,
      "type": "event",
      "kind": "voice_intent",
      "payload": { "action": "go_to_marker", "markerId": 1 }
    }
  ]
}
```

アクションは次の6種類である。

- `event`: `person`、`marker`、`voice_intent`をWebSocketへ配信する。
- `faults`: Simulatorの故障設定をまとめて適用する。
- `clear_faults`: すべての故障設定を解除する。
- `reset`: 停止、poseの原点復帰、故障解除を行う。
- `front_obstacle`: 三値状態、認識health、confidence、任意の距離・横位置を注入する。
- `clear_front_obstacle`: fresh/healthyな`CLEAR`観測がある場合だけ、理由付きで停止ラッチを解除する。

`at_ms`はシナリオ開始からの相対時刻であり、昇順に記述する。シナリオ開始時には実行中の高水準モーションを中断し、ローバーを停止する。完了、中断、失敗時にもローバーを停止し、故障設定を解除する。

## Injected events

人物とマーカーは実カメラと同じ検証経路を通り、次の共通メッセージとして全WebSocketクライアントへ配信する。

```json
{
  "v": 1,
  "type": "perception_event",
  "event_id": "19ff6a81d0",
  "kind": "marker",
  "status": "detected",
  "confidence": 0.9,
  "payload": {
    "marker_id": 1,
    "relative_x_m": 0.5,
    "relative_y_m": 0.0,
    "pose_correction": { "applied": true, "innovation_m": 0.5, "marker_id": 1 }
  },
  "source": "scenario",
  "accepted": true,
  "reason": ""
}
```

`source`は`manual`、`scenario`、`replay`のいずれかである。人物とマーカーは信頼度とpayloadを検証し、既知マーカーはpose補正にも使う。音声intentは引き続き`scenario_event`として配信する。

## Fault settings

|Field|Meaning|
|---|---|
|`command_latency_ms`|`drive`をSimulatorへ適用する前の遅延|
|`state_latency_ms`|stateを返す前の遅延|
|`drop_next_commands`|次に受け取る`drive`を指定回数だけ破棄|
|`pose_noise_m`|決定論的なx/yノイズの最大振幅|
|`yaw_noise_deg`|決定論的なyawノイズの最大振幅|
|`stale_state_ms`|指定時間前のposeと速度を返す|
|`battery_percent`|バッテリ表示の上書き。`null`は実値|
|`encoder_fault`|encoder入力を故障として扱い、odometry信頼度を低下|
|`imu_fault`|IMU入力を故障として扱い、odometry信頼度を低下|
|`seed`|決定論的ノイズの位相|

故障はSimulator Adapterの内部だけに実装する。通常停止、非常停止、Runtimeの操作権、速度上限、command TTLは無効化しない。`stop()`自体は遅延や破棄の対象にしない。

Development Labには個別の故障プリセットと複合プリセットがある。JSONシナリオでは複数の故障を一つの`faults`アクションとして固定できる。

## Front obstacle state

Development Labでは`CLEAR | BLOCKED | UNKNOWN`と`healthy | degraded |
unavailable`を別々に設定できる。`CLEAR`はhealthyな観測だけが確立できる。
Simulator Controllerは設定中の状態を1秒ごとにhealth heartbeatとして更新するため、
controllerが停止すればRuntimeの期限判定によって`UNKNOWN`へ戻る。これはSimulator専用で
あり、cameraや将来の実センサーのheartbeatを捏造しない。

一度`BLOCKED`になると、後から`CLEAR`を観測しても有効状態は`BLOCKED`のままである。
Development Labの`Clear latch`または`clear_front_obstacle` actionが、fresh/healthyな
`CLEAR`と解除理由を確認して初めて解除する。状態、health、freshness、latch、解除理由は
`/api/status.front_obstacle`、`/api/simulator/status`、WebSocket `front_obstacle`、
structured logで確認できる。

## Structured logs

Local ServerはセッションごとにJSON Linesファイルを作成する。既定の保存先はリポジトリの`.runtime/logs/`であり、Git管理対象外である。`APRIS_LOG_DIR`環境変数で保存先を変更できる。

主なカテゴリは次のとおりである。

- `client_message`: PWAから受信した走行・操作メッセージ
- `adapter_command`: Adapterへ渡したdrive、stop、reset
- `state`: pose、速度、バッテリなどの出力
- `server_message` / `server_event`: クライアントへの応答と安全イベント
- `scenario_event`: 人物、マーカー、音声intent
- `perception_observation`: カメラ、記録映像、scenarioからの認識観測と検証結果
- `simulator_faults` / `simulator_faults_clear`: 故障設定
- `scenario_lifecycle`: シナリオとリプレイの開始・終了
- `front_obstacle`: 観測、heartbeatによる更新、latch解除と有効状態

各行にはセッションID、連番、UNIX時刻、セッション開始からの`elapsed_ms`が入る。Development Labではstateを除いた最近のログを表示する。stateを含むログもAPIまたはJSONLファイルから取得できる。

## Safe replay

`Replay inputs`は、現在のセッションログから`scenario_event`、カメラまたは記録映像由来の`perception_observation`、故障設定だけを相対時刻順に再生する。scenario由来の認識観測は`scenario_event`との二重再生を避けるため除外する。`drive`、`move`、`turn`、モーター命令は再送しない。リプレイ開始前に実行中のモーションを中断し、終了時に停止と故障解除を行う。

この制限により、記録確認の操作が意図せずローバーを走行させない。走行を含む再現試験は、公開ミッションAPIを呼ぶテストまたは明示的なシナリオとして実装する。

## Development API

Simulator専用APIは以下である。

```text
GET    /api/simulator/scenarios
POST   /api/simulator/scenarios/{id}/run
POST   /api/simulator/scenarios/stop
GET    /api/simulator/status
POST   /api/simulator/events
PUT    /api/simulator/faults
DELETE /api/simulator/faults
PUT    /api/simulator/front-obstacle
POST   /api/simulator/front-obstacle/clear
GET    /api/simulator/logs
DELETE /api/simulator/logs
POST   /api/simulator/logs/replay
```

これらは開発・運営用であり、サービスミッションの公開APIではない。実機Adapterへ同じ故障設定APIを要求しない。

## Included scenarios

- `perception-inputs`: person → marker → voice intentを順に注入する。
- `perception-loss`: person detected → lost → 低信頼度markerの拒否を再現する。
- `fault-injection-demo`: 遅延、命令欠落、古いstate、poseノイズ、低バッテリをまとめて適用し、最後に解除する。
- `front-obstacle-latch`: CLEAR、BLOCKED、再度のCLEAR、理由付き明示解除を順に再現する。

テストは次のコマンドで実行する。

```bash
uv run --directory apps/server pytest
uv run --directory apps/server ruff check src tests
npm test
```
