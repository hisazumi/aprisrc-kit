# APRISRC Kitを試す・変更する・引き継ぐ

[English](handoff.md)

APRISRC Kitは、APRISのロボットチャレンジAPRISRCで参加者がサービスを開発するためのキットです。
サービスを作るのは参加者で、Kitは共通の開発機能と参考サンプルを提供します。
[目的と位置づけ](positioning.ja.md)を参照してください。

リポジトリを渡された人向けの入口です。サービスの体験・変更に実機は不要です。
ローカル開発ツールは必要で、オフライン配布済みの完成アプリではありません。
実機試験はPC/server一つとローバー一台を前提にします。

## 入口を選ぶ

| やりたいこと | 最初に読むもの | 到達点 |
| --- | --- | --- |
| 実機なしで試す | [Playground実習](demos/playground-workshop.ja.md)、20-30分 | 三つのサンプルを動かし、一つの変更を比較する |
| サービスを作る | [参加者向けquickstart](challenger-quickstart.ja.md)、30-45分 | runtime/firmwareを変えずにmissionとテストが動く |
| 設定済みUGV02で試す | [UGV02セルフテスト](hardware/ugv02-self-test.ja.md) | 浮かせた車輪で挨拶の旋回と停止を確認する |
| 未設定のUGV02を準備する | [ファーム設定](hardware/ugv02-websocket-firmware.md)、その後セルフテスト | firmware・LAN・ID/token・HTTPSと停止状態を確認する |
| 実機でコードと観測を見る | [実機Playground](demos/hardware-playground.ja.md) | 監督付き挨拶・追従試験を記録する。このUIの実機検証は未完了 |
| 別のスマホやローバーを使う | [機材と移植条件](hardware/service-hardware-porting.ja.md) | 観測・移動・安全の同じcontractを満たす |

実機があってもSimulatorから始めます。PC実習にcamera、microphone、LLM API key、印刷マーカー、
ROS 2、LiDARは不要です。変更はfeatureブランチで行い、ソース編集前にサービスを停止します。
Simulatorの成功は実機の安全性・精度の証明ではありません。

## 実績と制約

| 対象 | 現状 |
| --- | --- |
| Simulator Playground | 共通サービス、人物手動操作、シナリオ、読み取り専用の定義ソース。実行行強調はなく、仮想観測はカメラ認識ではない |
| UGV02 firmwareと従来のサービス画面 | 試験機でbounded旋回・後退、lease/切断停止、監督付きスマホ追従を確認 |
| 実機Playground | 模擬入力テストと未接続PC/スマホ画面を確認。実カメラ・実機試験はこれから |
| 実機マーカー案内 | 未実証。実機Playgroundでは無効。旧URLも共通画面への別名で、実機向けの迂回経路ではない |

現在の機能は[Platform status](platform-status.ja.md)、実測履歴はfirmwareガイドを参照します。
無人自律走行・一般的な障害物回避・停止距離の保証はありません。監督許可は人による通路確認で、sensorではありません。

## サービスを変更する

Implementationで場所を確認し、`apps/pwa/src/missions/myService.ts`を編集します。
共通サービスは`service/catalog.ts`、低水準missionは`missions/index.ts`で登録します。
シーン設定はソースを書き換えません。保存・共有にはJSONの書き出し・読み込みを使います。
quickstartとpublic APIに従ってください。

missionは操作権を持つbrowser tabで実行します。serverは観測検証と移動許可、firmwareはmotor制御と
watchdogを担当します。監督試験ではbrowserを前面に保ち、端末をsleepさせません。
missionにGPIO・PWM・通信処理・安全迂回を追加しません。機材/sensorの変更はadapter/client境界で行います。

変更後は`npm test`、`npm run typecheck`、`npm run build`を実行します。server変更にはroot READMEの
Ruff/pytestも必要です。PRに挙動の変更と試験環境を書き、mockの成功を実機検証とは記載しません。
[ロードマップ](roadmap.ja.md)で実機依存の作業と実機なしの作業を区別できます。

## 引き継ぎ・問題報告

次を秘密情報を除いた試験メモやissueに残します。

- Git commit/branch、firmware version、adapter、sample URL
- phone/browser、固定方法とcamera方向、車輪を浮かせたか床上か
- 準備の完了項目、最後に動いたガイドと手順
- シーン/presetや実物配置、一つのコード/設定変更、期待と実際の結果
- 画面の状態・error・screenshot、必要なら`apris-doctor --json`
- 停止方法、車輪が止まったことを目視したか、未確認事項

rover IDと接続情報はprivateな経路で渡し、開発tokenは受け手の環境で設定します。
token、Wi-Fi password、`.env`、`apris_rover_secrets.h`、CA秘密鍵、flash backupをcommitしません。
LAN変更時はfirmwareのserver host設定と証明書の再生成が必要な場合があります。
前の利用者のIPやCAが別PCでも使えるとは考えないでください。

予想外の動きではE-stopと必要に応じて物理電源を使います。原因不明のまま床上試験を繰り返しません。
telemetryがない、または0というだけでは車輪停止の証明になりません。
process復旧は[Operations runbook](operations/runbook.md)を使用します。過去の実験記録は参照資料で、設定手順ではありません。

## 現行の編集・許可方式

入口は[My service](demos/student-service.ja.md)。`missions/myService.ts`を編集し、
選択欄との対応は`service/catalog.ts`で管理する。汎用missionのregistryとは別である。
Implementationは読み取り専用で実行行強調はない。シーンはJSON保存・読み込みを使う。
実機は別途30秒の手動確認が必要。開始だけでは延長しない。
[実機操作](demos/hardware-playground.ja.md)の現行手順を使う。
