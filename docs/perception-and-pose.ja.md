# Perception and pose estimation

[English](perception-and-pose.md)

M4では、スマートフォン上の認識結果とローバーの位置推定を、サービスから利用できる共通形式へ変換する。映像や検出器の出力から直接走行命令を生成せず、Local Serverによる検証と共通イベントを必ず経由する。

## Data flow

```text
live camera / recorded video
        │ on-device detector
        ▼
perception_observation
        │ timestamp / confidence / payload validation
        ▼
perception_event ──> onPerson() / onMarker()
        │
        └── known marker ──> course-frame pose correction

wheel encoders + IMU ──> odom pose ──> course-frame pose
```

人物・マーカーの観測は操作権を必要としないが、走行命令ではない。認識器、イベントlistener、ミッションのいずれからもモーター命令へ直接到達できない。

## Browser detection

Service AppまたはDevelopment Labの`Camera preview`で、ライブカメラまたは端末内の記録映像を選択し、`Start perception`を押す。映像自体はPWAから送信せず、受理された構造化観測だけをWebSocketでLocal Serverへ送る。

人物にはMediaPipe Pose Landmarker Lite、QRマーカーにはブラウザのShape Detection APIを利用する。

- `PoseLandmarker`: 左右の肩を検出し、肩の中点を方位、肩幅を追従距離の代理値として使う。足や顔は必須ではなく、腰が見えない場合は肩幅から上半身領域を補う。
- `BarcodeDetector`: `APRIS:MARKER:<id>`という値を持つQRコードをマーカーとして検出する。
- Poseモデルは`Start vision`後に遅延ロードし、映像フレームの推論は端末内で行う。WASMとモデルはversion固定した配布元から取得し、映像自体は送信しない。
- `BarcodeDetector`は実行時に対応状況を判定し、未対応端末では人物認識だけを継続する。
- 記録映像もライブカメラと同じ検出経路を使う。

人物はMVPとして最大1人を追跡する。両肩のvisibilityとpresenceが閾値を満たさない場合は観測を生成せず、1.2秒継続すると明示的な`lost`になる。カメラ映像には同じ正規化領域を重ねて表示し、実機で認識範囲を確認できる。

マーカーの既定実寸は160 mm、カメラ水平画角は60度として距離と方位を概算する。QR検出だけではマーカーに対する3次元姿勢を求められないため、通常は位置だけを補正し、yawはodometryを維持する。将来AprilTagやArUcoの6DoF detectorへ差し替える場合も、同じ`relative_x_m`、`relative_y_m`、任意の`relative_yaw_rad`を出力する。

## Observation validation

ブラウザは次のメッセージを送る。

```json
{
  "v": 1,
  "type": "perception_observation",
  "observation_id": "perception-...",
  "kind": "marker",
  "status": "detected",
  "confidence": 0.9,
  "captured_at": 1786000000.0,
  "source": "camera",
  "payload": {
    "marker_id": 1,
    "relative_x_m": 0.7,
    "relative_y_m": 0.1
  }
}
```

Local Serverは次を検証する。

- observation IDの重複
- 2.5秒を超える古い観測、0.5秒を超える未来時刻
- 人物0.50、マーカー0.65未満の信頼度
- 正規化された人物領域と有限なマーカー相対位置
- 既知のmarker IDと0.08–5.0 mの観測距離
- 現在位置から3.0 mまたは90度を超える不自然な補正

拒否した観測は`status: rejected`と理由をOperator向けイベントへ出すが、サービスの`onPerson()`と`onMarker()`には渡さず、poseも変更しない。

## Service event API

```ts
const stopPersonEvents = rover.onPerson((event) => {
  if (event.status === "lost") {
    void rover.stop("person lost")
    return
  }
  console.log(event.personId, event.confidence, event.bearingDeg)
})

const stopMarkerEvents = rover.onMarker((event) => {
  console.log(event.markerId, event.poseCorrection?.applied)
})

stopPersonEvents()
stopMarkerEvents()
```

検出中は同じ対象を最大約1.7 Hzで通知する。1.2秒間見えなくなった対象には`lost`を1回通知する。`lost`自体は走行を開始せず、追従などのミッションはlistener内で明示的に`stop()`しなければならない。

## Odometry and pose correction

`WheelImuOdometry`は左右の累積encoder tickから移動距離と旋回量を求め、IMU yaw rateと相補的に統合する。Simulatorは次の仮想センサ値を生成するため、実機なしで同じ層を検証できる。

- wheel radius: 0.0475 m
- track width: 0.225 m
- encoder resolution: 1320 ticks/revolution
- IMU yaw weight: 0.70

Local Serverの`PoseFusion`はodometry座標からcourse座標へのSE(2)変換を保持する。既知マーカーの座標は`apps/server/config/course-markers.json`に置く。マーカー補正は信頼度に応じて段階的に反映し、`move`と`turn`の相対距離制御には補正前のodometryを使う。これによりマーカー補正で高水準motionの完了判定が飛ばない。

`state.pose_quality`は次を通知する。

- `frame_id`: `odom`または`course`
- `source`: `encoder_imu`、`encoder_only`、`marker_corrected`、`unavailable`
- `confidence`: 0.0–1.0
- encoder / IMUの状態
- `state_stale`、`encoder_fault`、`imu_fault`などの異常
- 最後に補正へ使ったmarker ID

Development LabではencoderとIMUの故障を注入できる。両方が故障した場合はposeの信頼度が低下して`unavailable`となるが、安全制御、TTL、停止操作は引き続きLocal Serverが処理する。

## Current limitations

- 初回の人物認識には約6 MBのPoseモデルとMediaPipe WASMの取得が必要である。オフライン会場向けの自己ホスト化は未実装である。
- 肩幅は距離の代理値であり、衣服、姿勢、カメラ画角に応じた実機校正が必要である。
- 両肩が隠れる、極端に横を向く、または画面外になる状況では人物を見失う。
- Barcode Detection APIの対応状況はブラウザに依存する。
- QRマーカーからの距離は未校正の概算であり、実機でカメラ内部パラメータとマーカー寸法を設定する必要がある。
- マーカーmapはServerとサービス設定の双方で同じID・座標を使う必要がある。配布構成で単一設定へ統合する。
- 実機encoder / IMUの単位、符号、更新周期、異常値はUGV02 Adapter実装時に確認する。
