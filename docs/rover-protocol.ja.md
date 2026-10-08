# APRIS Rover WebSocket protocol

[English](rover-protocol.md)

Status: **Development protocol v1 implemented and exercised on UGV02; production WSS,
rover-scoped credential provisioning, and full hardware qualification remain pending**

APRIS ServerとUGV02などのrover firmwareは、device-initiated WebSocket `/ws/rover`で通信する。このprotocolはPWAが使う[Client protocol](protocol.md)とは別version・別schemaで管理し、browser、mission、PhysiCode Bridgeへ公開しない。

## Responsibility boundary

APRIS Serverは操作権、mission、障害物判断、速度上限の調停と、Client protocolの`move` / `turn`を単一のbounded motionへ変換する。rover firmwareはencoderとIMUに近い制御周期でそのmotionを実行し、motor停止後にterminal結果を返す。

```text
Client / PhysiCode Bridge
        | move(distance) / turn(angle)
        v
APRIS Server
        | one bounded motion + renewable execution lease
        v
Rover firmware
        | local wheel-speed loop, odometry and stop
        v
Motor driver
```

Roverへprogramやmission全体を送らない。自動`move` / `turn`を左右輪速度の高周期streamへ展開しない。手動teleoperationだけは短いlease付き速度指令を使用できる。

## Units and signs

SI単位とROS REP-103の平面規約を使用する。

- positive `x` and `distance_m`: rover forward
- positive `yaw`, `angle_rad`, and `angular_speed_rad_s`: counter-clockwise / left turn
- velocity: metres per second and radians per second
- duration and TTL fields: integer milliseconds

UGV02はdifferential driveなので`vy`を受け付けない。Client protocolの`turn.angle_deg`はAPRIS Serverがradianへ変換してからRover protocolへ渡す。

## Connection and identity

1. RoverはTLSでserver identityを検証し、device credentialを使って接続する。現在のdevelopment bootstrapは`APRIS_ROVER_TOKEN`を`Authorization: Bearer` headerで送る共有credentialであり、tokenをURL/query/logへ入れない。hosted運用前にrover単位のcredential発行・失効へ置き換える。
2. 最初のapplication messageとして`rover_hello`を送る。少なくとも`protocol_versions`、`rover_id`、`boot_id`、firmware/build ID、hardware revision、capabilities、安全上限を含める。
3. Serverはversionを選択し、新しい`connection_epoch`を割り当てる。重複`rover_id`、未認証device、未対応versionは走行可能状態にしない。
4. Roverとserverはheartbeatで接続状態と時計誤差上限を監視する。heartbeatは`clock_offset_ms`と`clock_uncertainty_ms`を含み、未受信、期限切れ、または誤差上限超過の間は新しいmotion、lease更新、速度指令を拒否する。停止側の`stop` / `estop` / cancelは不健康時も送信を試みる。
5. 接続が切れた時点でroverはmotorを停止し、active motionをterminalな`cancelled`にする。再接続時は必ず新しいepochになり、未完了motionを再開しない。

`boot_id`はfirmware起動ごとに変える。これによりserverはWebSocket再接続とdevice rebootを区別する。

## Common command envelope

Serverからroverへ送る走行関連commandは、少なくとも次を持つ。

- protocol version and message type
- `connection_epoch`
- epoch内で単調増加する`seq`
- 一意な`command_id`
- server発行時刻とfreshness TTL
- optional correlation: `run_id`, `effect_id`, `request_id`

Roverは違うepoch、以前以下のsequence、期限切れcommandを拒否する。freshness TTLはserver送信時から数え、roverの受信時から新しく開始してはならない。時計同期の誤差が許容値を超える場合もfail closedで拒否する。field名と範囲の正本は[`packages/protocol/rover-v1.schema.json`](../packages/protocol/rover-v1.schema.json)であり、firmware側の時計同期方式と実測許容値はPhase 6のmotor command前に固定する。

Serverはcommand送信前にepoch内のsequenceを割り当て、`command_ack`をtimeout付きで待つ。`start_motion`のackは実行完了ではなく、同じ`motion_id`のterminal `motion_status`だけをClient motionの結果へ写像する。実行中はleaseの半分の周期を目安にrenewし、heartbeat/clock/ack failureでrenewできない場合はcancel/stopを試みた上で成功を推測しない。

## Server-to-rover commands

### `start_motion`

停止可能で上限のある単一動作を開始する。

- `motion_id`: 再送を安全にするidempotency key
- `kind`: `linear | rotate`
- `distance_m` for `linear`, or `angle_rad` for `rotate`
- maximum linear and angular speed
- `max_duration_ms`: motion固有の絶対実行上限
- `lease_ms`: 走行継続許可の短い期限

Roverはcapabilityとfirmware固定上限を超える値を拒否する。accepted後はlocal encoder/IMU feedbackで制御する。同じ`motion_id`を受けた場合、既知の状態またはterminal結果を返し、新しいmotionを開始しない。

### `renew_motion_lease`

同じ`motion_id`の走行継続leaseだけを更新する。目標値、上限、connection epochを変更できない。leaseが切れたmotionは停止してterminalになり、後からrenewしても再開しない。

### `cancel_motion`

active motionを減速または即時停止し、`cancelled`へ遷移させる。対象motionが既にterminalでも成功扱いにできるが、再実行はしない。

### `set_velocity`

Operatorの手動teleoperation用に`linear_velocity_mps`と`angular_velocity_rad_s`を短いlease付きで指定する。入力中だけ更新し、lease切れで停止する。自動motionと同時にactiveにできない。

### `stop` and `estop`

`stop`は通常停止、`estop`はfirmware側にもlatchする非常停止である。どちらもmotion/velocity commandより優先し、重複しても安全でなければならない。E-stop解除はserver側とfirmware側の双方のpolicyを満たし、解除messageだけで走行を再開しない。

## Rover-to-server messages

- `rover_hello`: identity、version、capabilities、安全上限
- `heartbeat`: boot/epoch、接続health、時刻同期情報
- `command_ack`: acceptedまたはstable rejection code
- `motion_status`: `accepted | running | completed | cancelled | failed`、`motion_id`、進捗、terminal reason
- `telemetry`: encoder、local odometry、velocity、IMU、battery、motor state、fault、E-stop/watchdog state
- `event`: reboot、watchdog stop、driver faultなどのlifecycle/safety event

`completed`は目標判定を満たし、motor出力を停止した後だけ送る。`accepted`や送信成功をAPRIS motionの完了と解釈しない。QR障害物による`blocked`などのPhysiCode固有結果はAPRIS ServerがClient/World境界で写像し、firmwareへ教育言語の意味論を持ち込まない。

## Motion state machine

```text
                  +--> completed
accepted --> running --> cancelled
    |             +--> failed
    +-----------------> cancelled / failed
```

terminal状態から`accepted`または`running`へ戻らない。次のすべてはmotor停止を伴う。

- execution lease expiry
- `max_duration_ms` expiry
- WebSocket disconnect
- `cancel_motion`, `stop`, or `estop`
- firmware watchdog, motor/encoder fault, invalid control state

通信断のあとAPRIS Serverが結果を確認できない場合、server側は成功を推測しない。再接続後のrover snapshotまたは同じ`motion_id`の照会でterminal結果を得られなければ`failed`として扱う。

## Phase 5 contract tests

- duplicate `motion_id` never causes a second movement
- stale epoch, non-increasing sequence, expired command, and unsafe clock uncertainty are rejected
- lease expiry, disconnect, cancel, stop, E-stop, and max duration stop the fake rover
- reconnect creates a new epoch and never resumes an unfinished motion
- `completed` is emitted only after the fake motor velocity is zero
- manual velocity and bounded motion are mutually exclusive
- firmware-advertised limits cannot be raised by server configuration
- Simulator and WebSocket Rover Adapter expose equivalent high-level motion terminal semantics

Version 1の両方向JSON Schemaは[`packages/protocol/rover-v1.schema.json`](../packages/protocol/rover-v1.schema.json)、実行modelは`apps/server/src/apris_server/rover_protocol.py`、registry/dispatchは`rover_registry.py`、実機境界は`websocket_rover_adapter.py`、motor-free state machineは`fake_rover.py`に置く。`scripts/generate-rover-protocol-schema.py`でschemaを再生成し、contract testがmodelとの差分とfixtureを検証する。fieldを実装都合で変更する場合も、[公開アーキテクチャ](architecture.ja.md)の責務境界と安全不変条件は変更しない。
