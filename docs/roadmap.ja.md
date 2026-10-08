# Development roadmap

[English](roadmap.md)

この文書をAPRISRC Kitの優先順位の正本とする。ここには未完了の成果と完了条件を
記載する。現在利用できる機能は[Platform status](platform-status.ja.md)、設計理由はADR、実測値は
hardware記録で管理する。完了した実装の詳細はGit履歴に残し、主導線のroadmapには置かない。

これはKit開発の計画で、APRISRCの締切・必須課題・審査基準ではない。
参加者はKitを使って独自サービスを作る。[目的と位置づけ](positioning.ja.md)を参照する。

Last reviewed: 2026-10-08

Current focus: 変更可能なSimulatorサンプルを引き継ぎ、他の開発者が独立して試用・拡張できるようにする。
実機依存の検証は未完了として残し、引き継ぎの前提条件にはしない。

## Status definitions

- **Next**: 直ちに取り組む実装対象
- **In progress**: 利用可能な縦切りはあるが、完了条件が残る
- **Waiting**: 外部参加者または環境が利用可能になれば実施できる
- **Hardware-dependent**: 実機または現地環境が必要
- **Optional**: コアプラットフォームの導線外にある発展項目
- **Completed**: Completed foundationに一度だけ要約し、詳細なtask listは削除する

## Near-term order

1. [引き継ぎガイド](handoff.ja.md)とPlayground実習を使い、実機なしで体験・変更・開発する。
   初見のセットアップと変更の摩擦を記録する。
2. 参加可能になった初見の教員1名でM7Bを実施し、致命的な摩擦を除いた後で3〜5名へ広げる。
3. pilot結果をMission APIの使いやすさとM5のsetup・配布導線へ反映する。
4. 実機が使えるときに、新実機Playgroundの挨拶・追従、M7A Service App/UGV02 marker試験、
   M6Bの残るqualificationを確認する。
5. production音声方式は、現在のM8 browser/structured-intent経路では不足する具体的な要求が
   pilotで見つかるまで選定しない。

## M7: Reference service prototypes

Status: **In progress**

人物への挨拶、仮想人物への接近・追従、Carry assistant、対象喪失、cancel、E-stopのflowは
実装済みである。外部評価をengineering作業のblockerにしないよう、M7を二つに分ける。

### M7A: Marker-based Mobile Receptionist

Status: **In progress**（共通Service Appと自動検証は完了、対話的Simulator walkthroughと
監督付きUGV02 walkthrough待ち）

Goal: 人物認識、構造化された依頼、marker認識、bounded movement、音声応答を組み合わせた
サービスを、プラットフォームの安全境界を迂回せず実現できることを示す。

Reference flow:

1. 来訪者を検出して挨拶する。
2. 「入口まで案内して」など、allowlist済みの依頼を受ける。
3. bounded turnで設定済みdestination markerを探す。
4. markerへ向きを合わせ、bounded stepで接近する。
5. 到着を音声で知らせて停止する。
6. cancel、観測の期限切れ・喪失、前方の`BLOCKED` / `UNKNOWN`、操作権喪失では停止する。

Deliverables:

- `onPerson`、`onMarker`、`move`、`turn`、`stop`、`say`だけを使う登録済みmission
- 実際の重複を減らす場合に限り、marker観測を待機・検証する再利用helper
- person、intent、destination marker、到着を含む決定的なSimulator scenario
- Local Server adapterだけを切り替え、同じMissionをSimulatorまたはUGV02で実行する一つの
  Service App画面
- 正常完了、別marker、marker喪失、cancel、前方blockのtest
- service固有コードとplatform所有の安全機能を区別する短い実行ガイド

実装済み: 登録Mission、設定可能な三つの目的地、person/intent/markerを含む決定的scenario、
scenario自動起動またはphone camera引き継ぎを行う共通`/app?service=receptionist` flow、
監督付き実機clearance、正常・安全test、日英デモガイド。

Exit criteria:

- serviceがSimulator固有motionやRover protocolを使用しない。
- 決定的scenarioが到着し、commanded velocityをゼロで終了する。
- 喪失、cancel、前方が安全でない場合はすべて通常のMission API経由で停止する。
- Lab専用controlを使わず、共通Service AppでSimulator walkthroughが完了する。
- source変更なしで、同じMissionが監督付きUGV02 marker approachを完了する。

### M7B: 初見の開発者からのfeedback

Status: **Waiting** for independent trials

Simulator実習とサンプルを試して変更できるか、起動・編集・失敗からの復帰の摩擦を記録する。
問題報告と提案は[開発への参加](../CONTRIBUTING.ja.md)に従う。個人の評価記録や内部pilot計画は公開しない。

## M5: Event-ready local distribution

Status: **In progress**

利用可能: 正しいliveness/readiness、runtime status、doctor、typed/redacted config、開発用一括起動、
local HTTPS/WSS手順。

Remaining:

- build済みPWA、API、WebSocketをFastAPIの同一originから配信する。
- offline会場setupと接続URL/QRを提供する。
- service worker更新とcache復旧を文書化する。
- 代表的なiOS/Android端末でcamera、microphone、install、permission、updateを確認する。

Exit: 新しいPCとsmartphoneを、会場Internetなしでも手順書だけで接続・復旧できる。

## M6B: UGV02 hardware qualification

Status: **Hardware-dependent / In progress**

確認済み: firmware flash、registration、heartbeat/telemetry、E-stop、lease/watchdog、
server切断時停止、bounded turn/reverse、監督付きsmartphone人物追従。

Remaining:

- production WSSとrover単位のcredential provisioning
- IMU/battery qualificationと意図しないRF-loss試験
- duplicate/max-duration試験とpersistent idempotency
- p95距離・角度誤差、最大停止距離、停止時間envelopeの計測
- 前方安全perceptionの要件確定とqualification

Exit: 設定だけでSimulator/UGV02を切り替えられ、missionは変更せず、全loss pathで安全に停止し、
事前に宣言したmotion/safety limitを満たす。

## M8: Voice and structured intent

Status: **In progress; production provider work deferred**

利用可能: browser speech recognition/synthesis、local keyword rules、任意のOpenAI structured
intent、allowlist検証、予約済みstop処理、mission dispatch。model出力にmotion parameterや
transport commandを含めることはできない。

pilotで必要性が示された場合に残る作業: production STT/TTSの選定・計測、端末差の試験、
latency/error budgetの定義。

## M9: iron-X ROS 2 Humble bridge

Status: **Hardware-dependent**

実際のiron-Xを確認してから着手する。topic、type、frame、QoSを調査し、Jetson側adapterで
`/cmd_vel`、`/odom`、`/imu`を変換する。再接続と通信断時停止を維持し、mecanumの`vy`は
当初ゼロに制限する。PWAとmission codeは変更しない。

## M10: LiDAR and advanced autonomy

Status: **Optional**

RPLIDAR C1またはiron-X `/scan` adapter、scan記録、operator向け可視化、単純な障害物停止、
将来のmapping/path planning実験を候補とする。LiDARなしでもcore serviceを動かせる状態を維持し、
LiDAR固有情報をservice missionへ漏らさない。

## Completed foundation

次のmilestoneは完了済みであり、詳細なtask listをroadmapから削除した。

- **M0**: Simulator、Client protocol、単一操作権、速度/TTL制限、通信断時停止、E-stop、
  共通`RoverAdapter`境界
- **M1**: smartphone camera、HTTPS/WSS開発、高水準motion、Service App、Operator Console、
  Development Labの画面分離
- **M2**: 公開Mission API、mission registry、編集可能なmission/config境界、starter、文書、test
- **M3**: 再現可能なSimulator scenario、fault injection、structured log、replay、安全回帰test
- **M4**: 人物/marker認識、pose推定、marker補正、confidence、対象喪失処理
確認済み範囲は[Platform status](platform-status.ja.md)を参照する。
公開版では外部integration bundleと個別の検討履歴を省略する。
