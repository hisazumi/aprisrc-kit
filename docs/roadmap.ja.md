# Development roadmap

[English](roadmap.md)

この文書をAPRISRC Kitの優先順位の正本とする。ここには未完了の成果と完了条件を
記載する。現在利用できる機能は[Platform status](platform-status.ja.md)、設計理由はADR、実測値は
hardware記録で管理する。完了した実装の詳細はGit履歴に残し、主導線のroadmapには置かない。

これはKit開発の計画で、APRISRCの締切・必須課題・審査基準ではない。
参加者はKitを使って独自サービスを作る。[目的と位置づけ](positioning.ja.md)を参照する。

Last reviewed: 2026-11-03

Current focus: チャレンジ後の安全な運用、起動・復旧、再現可能な開発環境。
実機の評価と次回の機体構成選定は未完了として残す。

## Status definitions

- **Next**: 直ちに取り組む実装対象
- **In progress**: 利用可能な縦切りはあるが、完了条件が残る
- **Waiting**: 外部参加者または環境が利用可能になれば実施できる
- **Hardware-dependent**: 実機または現地環境が必要
- **Optional**: コアプラットフォームの導線外にある発展項目
- **Completed**: Completed foundationに一度だけ要約し、詳細なtask listは削除する

## チャレンジ後の優先順位

2026-11-03のチャレンジを踏まえた優先順位案であり、リリースの確約ではない。
従来の「pilotを待ってから進める」順序を更新する。既存milestoneの詳細は後半に残す。

### 振り返りと確認範囲

- 学生によるSimulatorと共有iron-Xでのサービス試用があった。現場のフィードバックとして
  活かすが、独立したユーザビリティ評価や実機の安全評価が完了したとは扱わない。
- 充電中の机上の機体をSimulatorと取り違えて遠隔操作し、落下したという報告があった。
  床への設置・走行しない試験での車輪を浮かせる注意を日英で追記済みだが、注意文だけでは
  接続先の取り違えは解消しない。
- 起動の複雑さ、前方Clear確認の繰り返し、非常停止の復旧案内が負担になった。
  スマホで何度も押す必要があった事例は、ブラウザと通信のどちらが原因か未切り分け。
- 開発・試用中に通信指令の遅延、操作権・nonceの失効、機体内制御ループの異常が見られた。
  これらを一括して「Wi-Fiの問題」とせず区別する。
- 1台で起動順の競合を修正し、再起動後の自動起動を確認した。ただしNTPが応答せず、
  その後の時計同期をまたいだ計測継続は未確認。
- 発表から、シミュレーション時間、部屋、独自スマホUI、座標移動、任意の3D環境、
  認識対象の多様化という要求が加わった。これらは要望であり、実装済みではない。

### P0: 実機操作と復旧を取り違えない

- [ ] Service・Playground・Consoleと動作許可の操作付近で、確認済みの実際のAdapterと
  機体アドレス・識別情報を明示する。不明な場合も明示し、トークンは表示しない。
  仮想フィールドの表示をSimulator接続と誤認させない。
- [ ] 操作前確認を短くまとめる。床への設置、走行しない試験では車輪を浮かせて確実に固定、
  周囲の確保、走行時の充電ケーブル取り外し、すぐ止められる人の配置を含める。
- [ ] 通常の非常停止、操作権の競合、再起動が必要な
  `control_loop_delayed_restart_required`・`stop_unconfirmed`などを区別する。
  処理中・成功・失敗と、学生ができる復旧／先生に依頼する復旧を表示する。
- [ ] 不明・障害物ありを勝手にClear扱いせず、前方確認の不要な繰り返しを減らす。
  復旧時に自動で走行を再開しない。

完了条件：初見の人が接続先と復旧方法を推測せず判断できる。不明・再接続時の表示と、
自動走行再開がないことを自動テストで確認する。

### P1: 起動と日常利用を再現可能にする

- [ ] 次回向けの固定リリースと、PC・PWA・firmware・機体bridge・対応スマホ／ブラウザの
  検証済み対応表を用意する。現行ガイドと状態説明を確認済みの変更に合わせ、
  古いprivate派生の計画や過去の試験記録を起動手順と取り違えないよう明示する。
- [ ] 三輪先生の報告をもとにWindows導入を精緻化する。OpenSSLの必要性、
  `spawnSync openssl ENOENT`、WinGet、実行場所・`OPENSSL`の確認、証明書生成の再試行を含める。
  PC単体のSimulator利用とスマホHTTPS準備を分ける。案内した導入手順の新規Windows検証は未完了。
- [ ] 起動手順を減らし、Simulator用と実機用の入口を明確にする。
  認証情報、スマホURL、サーバー重複・操作権競合の確認、終了方法を整理する。
- [ ] 機体の起動順、非常停止付き自動起動、新鮮な計測、時計補正を検証する。
  プロセスが動いているだけで利用可能と判定しない。
- [ ] スマホ操作の反応遅延を再現し、操作から応答までをブラウザ描画・通信・機体応答と分けて計測する。
- [ ] 接続先、構成要素の版、停止理由、直近の指令・観測の遅延をまとめた診断情報を、
  SSHなしで保存・共有できるようにする。トークン・鍵・パスワード・非公開設定を
  含めないこともテストする。
- [ ] 共有機の引き継ぎを明確にする。機体識別、利用可能／操作権所有者の状態、
  操作権返却、別タブとの競合や接続先間違いの対処を示す。
  原則1チーム1台になっても使える仕組みにする。

完了条件：別の先生・学生が新規Windows PCから日英の手順だけで起動・接続・停止・復旧でき、
開発者の介入を要しない。

### P2: ジッタ対応とUGV02搭載構成を1台で検証する

- [ ] 学生のサービスコードの実行場所を決める。現状は操作権を持つブラウザでMissionが
  動くため、タブ終了・バックグラウンド化・スマホのスリープ・通信断・復旧を試験する。
  サーバーだけ搭載してもサービス実行は機体内で完結しない。
  前景利用を前提として明記する案と、同じAPIの機体内runnerを比較する。
  中断後は明示的な再開始を必要とし、自動で走行を再開しない。
- [ ] 突発的な遅延、欠落、重複、順序逆転、再接続をシミュレーションで再現する。
  操作権失効・指令陳腐化・観測陳腐化・機体内ループ停滞を分け、
  送信周期・最新指令の扱い・復旧方式を遅延／停止ログで比較する。
- [ ] 速度に応じた減速・停止条件を定め、停止時間・距離を実測検証する。
  シミュレーションや監視者の存在を実機故障試験の代わりにしない。
- [ ] UGV02に専用コンピュータを載せて1台試作する。Raspberry Piは候補で、未選定。
  スマホ認識を機体専用接続で渡す案と、カメラ・認識まで搭載する案を比較する。
  サーバーだけ機体へ移しても遠隔の認識・制御に依存する通信は残る。
- [ ] 学生PCでの開発・Simulatorを維持し、電源・固定・計算性能・費用は試作後に決める。
  原則1チーム1セットを目指す。借用iron-Xの共有も有効な選択肢であり、今回の構成を否定しない。

完了条件：再現可能なジッタ試験と1台の実機で、使える追従と上限内の停止を確認してから
台数調達や制限緩和を検討する。

### P3: Simulatorの環境と時間を編集・再現できるようにする

- [ ] 仮想観測＋Simulator、実カメラ＋Simulator、監視付き実機という段階的な試験導線を
  用意する。実観測と仮想観測を明示し、認識の問題と移動・通信の問題を分けて確認できるようにする。
- [ ] シミュレーション時間、一時停止・再開、リセット、時間進行の調整を導入する。
  Missionのタイマー・観測・移動のどこまで同じ時計を使うかを定め、
  実機watchdogは実際の単調増加時計で動かす。描画速度で試験結果を変えない。
- [ ] 上から見たフィールド・部屋の編集機能を追加する。壁・障害物・ローバー・人物・
  マーカーを配置し、初期配置を保存・読み込みする。配置編集とシナリオ実行を分離する。
- [ ] 部屋を検証環境と呼ぶ前に、衝突・領域境界・遮蔽の扱いを定める。
  壁を描くだけで認識や物理安全まで再現できたと扱わない。
- [ ] 2D環境を有用にしてから、任意の3D環境も検討する。同じサービスAPIとシーン定義を
  活かし、Simulator専用サービスを別に作らない。

完了条件：部屋と初期状態を保存し、同じ時間条件で試験を再現できる。編集操作は実機へ
走行指令を送らない。3Dは発展項目で、コア利用の必須条件にはしない。

### P4: 学生が作れるサービスを広げる

- [ ] 現在の行動、受け取った観測、待っている条件、停止理由を、変更するサービスコードと
  対応づけて可視化する。学生がコードの変更と振る舞いの関係を説明できるか検証する。
  行単位のハイライトは任意とし、必須条件にしない。
- [ ] 「座標へ移動する」最小例を文書化する。座標系・単位・自己位置の前提、
  キャンセル・到着時停止・失敗時の扱いを示す。まず既存Mission APIの提供範囲を確認し、
  相対移動と経路計画・ナビゲーションを区別する。直線移動を障害物回避と説明しない。
- [ ] 同じMission APIを使う、変更しやすいユーザ向けスマホアプリの最小テンプレートを用意する。
  サービス固有のボタン・状態表示と運用／開発用操作を分け、画面と振る舞いを一緒に変更できるか試す。
- [ ] 認識オブジェクトの種類を広げる。例はペットボトルを見つけたら発話するサービス。
  オブジェクト観測の検証・信頼度・鮮度・対象喪失・Simulator入力を定義する。
  検出と距離推定・個体追跡は別の能力として扱う。
- [ ] 変更可能なサンプルを改善し、初見の学生がAPIと変更箇所を理解できるか確かめる。
  マーカー案内の実機対応は、選ぶサービスで必要になった段階で進める。

完了条件：学生が独立してスマホUIとサービスを変更し、Simulatorで試せる。
実機では何が追加検証になるかも説明できる。

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

実装済み: 登録Mission、目的地設定、決定的scenarioの基盤、正常・安全test、日英ガイド。
現行の`/playground?service=receptionist`は人物・マーカーの手動入力またはシナリオ実行を使い、
UIの行き先はEntranceとDesk。Markers visibleの既定はオフ。
旧専用画面のscenario自動起動・カメラ自動切替は現在の操作手順ではない。
実機マーカー案内はService・Playgroundとも無効で、実機の完了条件は未達である。

Exit criteria:

- serviceがSimulator固有motionやRover protocolを使用しない。
- 決定的scenarioが到着し、commanded velocityをゼロで終了する。
- 喪失、cancel、前方が安全でない場合はすべて通常のMission API経由で停止する。
- Lab専用controlを使わず、共通Service AppでSimulator walkthroughが完了する。
- source変更なしで、同じMissionが監督付きUGV02 marker approachを完了する。

### M7B: 初見の開発者からのfeedback

Status: **In progress** — チャレンジのフィードバックあり、改善後の体系的な再評価待ち

Simulator実習とサンプルを試して変更できるか、起動・編集・失敗からの復帰の摩擦を記録する。
問題報告と提案は[開発への参加](../CONTRIBUTING.ja.md)に従う。個人の評価記録や内部pilot計画は公開しない。

チャレンジで得たフィードバックは上記P0〜P4に集約した。M7Bは初回試用待ちではなく、
改善後の独立した再評価を集める段階とする。

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

利用可能: browser speech recognition/synthesis、local keyword rules、任意のOpenAI/Gemini structured
intent、allowlist検証、予約済みstop処理、mission dispatch。model出力にmotion parameterや
transport commandを含めることはできない。

pilotで必要性が示された場合に残る作業: production STT/TTSの選定・計測、端末差の試験、
latency/error budgetの定義。

## M9: iron-X ROS 2 Humble bridge

Status: **ネットワーク経由サービスの試行報告あり、最新構成は実機再試験待ち**（2026-10-31）

ROS状態表示、指令期限付きbridge、同一ホストAdapter、認証付きLAN gatewayとPC Adapterを実装した。
コンソールの床上試験とiPhone人追従の操作者報告を記録している。mission APIは変更せず`vy`はゼロ。

次は停止確認キャンセル修正と0.15 m/s設定を実機で再確認し、対象喪失時の停止を計測して
観測が途切れる原因を調べる。その後、認識・操作権の引き継ぎ、Live Playground、通信断からの復旧、
bridge・OS・シリアル故障への独立した保護を評価する。ソフトウェアの復旧テストは実機故障評価ではない。
LiDAR安全確認は未実装。[iron-X人追従](hardware/ironx-follow.ja.md)から進める。

停止復旧の表示・手順はP0、ジッタと起動・時計補正の検証はP1〜P2で管理する。
上記の日付付きmilestone記録は、現在の各機体の正常性を示すものではない。

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
