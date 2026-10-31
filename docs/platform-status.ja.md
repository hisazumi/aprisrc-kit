# Platform status

[English](platform-status.md)

iron-X関連の更新・実機試験: 2026-10-31。UGV02の試験根拠は引き続き2026-09-25時点。

APRISRC Kitは、APRISRCで参加者がサービスを作るための開発キットである。
Simulator開発と同じ高水準missionの対応UGV02への移行経路を提供し、既定adapterはSimulatorである。
この文書はKitの実装状況で、競技規則や参加者のサービスの認証ではない。
[目的と位置づけ](positioning.ja.md)を参照する。

## Available now

- 挨拶・追従・マーカー案内のSimulator Playground。実コード、判断箇所の強調、再現可能な
  markerシーン、変更と比較の実習を用意
- camera観測、telemetry、高水準要求logを表示する実験的な実機Playground。
  明示的な監督許可で挨拶・追従を開始できるが、実機marker案内は無効
- `move`、`turn`、`stop`、pose、人物、markerを扱うservice mission API
- 操作権、速度上限、command TTL、通信断時停止、latched E-stop
- `/app`のCarry assistantとMobile Receptionist、`/console`の手動操作・監視、`/lab`の
  統合開発画面
- 仮想人物を使う人物反応、接近、追従、対象喪失のSimulator demo
- 三つの設定済み目的地と決定的なperson/intent/marker scenarioを持ち、activeなserver adapterから
  SimulatorまたはUGV02の動作を選ぶ共通Service Appのmarker-based Mobile Receptionist mission
- smartphone browser内の人物・上半身・APRIS marker認識
- 登録済みmissionだけを選ぶlocal keyword rulesと任意のLLM structured intent
- JSON scenario、fault injection、三値の前方障害状態、structured log、replay
- Simulator、UGV02 WebSocket、純正firmware診断用Factory HTTPのadapter選択

## Physical rover status

Waveshare UGV02の試験機にはAPRIS development firmware `0.97-apris-ws-dev`を導入済みで
ある。接続、heartbeat/telemetry、E-stop、lease/watchdog、server切断時停止、bounded
15度旋回、bounded 0.05 m後退を確認した。車載smartphoneの人物認識と30秒の監督付き
走行許可を使う人物追従も床上で動作を確認した。

これは一般環境での自律走行認証ではない。実機試験は
[UGV02 self-test](hardware/ugv02-self-test.md)の範囲で行う。

## Current limitations

- 実機Playgroundはソフトウェアテストと未接続画面のみ確認済み。実カメラ・実機の確認は未完了。
  従来のスマホ追従試験は別のサービス画面で行ったもの。
- 実機marker案内は、別経路のService Appも含め未検証。
- 前方のfree-spaceを常時保証する車載sensorはまだない。`UNKNOWN`は前進可能と扱わない。
- 前進を伴う人物追従は、利用者が期限付きで与える監督許可を使うMVPである。
- firmwareはprivate development LAN向けのplain WebSocketと共有tokenを使用する。
- production WSS、roverごとのcredential、永続idempotencyは未実装である。
- IMUとbattery telemetry、p95距離・角度誤差、停止距離の実機qualificationは未完了である。
- mission状態はbrowser-localであり、serverの`/api/status`は正本を持たない。
- browser音声認識・読み上げは端末依存で、production speech stackではない。
- iron-Xの状態表示、動作・停止・キャンセル、床上の前進・旋回、コンソール操作は1台で確認済み。
  サービスとLive Playgroundの対応判定は未検証。[iron-X操作ガイド](hardware/ironx-quickstart.ja.md)を参照。
- LiDARの安全制御への統合、SLAM、経路計画は未実装。

## Current priority

1. Simulator実習と変更可能なサンプルを引き継ぎ、他の人が独立して試用・開発できるようにする。
   入口は[引き継ぎガイド](handoff.ja.md)。
2. 初見の教員によるChallenger pilotを調整・実施し、そこで観測した導線、API、UI、
   error recoveryの摩擦を減らす。
3. offline配布、同一origin配信、端末セットアップなどevent-ready運用を仕上げる。
4. 実機が使えるときに新しい実機Playground、Mobile Receptionistのmarker接近、
   UGV02の停止・精度、前方安全sensorを検証する。

長期順序は[Development roadmap](roadmap.md)、起動・復旧は
[Operations runbook](operations/runbook.md)を参照する。
詳細な個別試験記録と外部integration bundleはこの公開版に含まない。現在の制約と試験順序はハードガイドで確認する。

## Verification baseline

実機Playground実装はPWA 122 testsとproduction build、未接続PC/スマホ画面の確認が成功した。
これはソフトウェアの根拠で、実機試験ではない。
