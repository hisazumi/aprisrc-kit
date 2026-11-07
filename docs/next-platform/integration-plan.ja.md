# Runner／server 統合計画

状態：設計案、2026-11-06。[English（正本）](integration-plan.md)。
[アーキテクチャ](architecture.ja.md)を、次に実装する単位へ具体化する。
試作が実運用可能になったという宣言ではない。

## 1. 目的と現在の根拠

メモリ内 runner、プロセス分離実験、Python port の成果を一つの実行系へ統合し、
既存 Simulator で実際に姿勢・位置が変化する bounded motion を実行する。
後述の合格条件を満たすまで、現行アプリの起動経路は変更しない。

レビュー修正済みの基準は commit
ef72930eba9ad9bcc12d0d0dd7c5986c246d0a21。
Node 33件（Python subprocess 7件を含む）、Python 27件、TypeScript、Ruff が
ローカルおよび対応する CI job で成功した。
詳細は [Python port の検証記録](python-port.ja.md)を参照。
これは fake の振る舞いとプロセス境界の検証であり、実機停止の保証ではない。
現在の PortFakeAdapter は疑似時間待ちであり、移動精度・オドメトリ・人物追従を検証していない。

## 2. 責務の所在

| 構成要素 | 所有する責務 | 境界 |
| --- | --- | --- |
| Node runner | run の受付、activity の親子関係、宛先付き mailbox、capability facade、質問、取消 | 移動を要求するが、機体の操作権は付与しない |
| Python server | 機体全体の操作権、世代管理、制限、lease、受け渡し中の停止保持、停止証拠、再動作禁止 | すべての移動クライアントに同じ検査を適用する |
| RoverAdapter／Simulator | backend の運動・観測、仕様を定めた停止証拠の提供 | サービス方針を持たず、試験用 fault を実機 adapter の要件にしない |
| PWA | サービス入力と状態表示、役割に応じた運用操作 | モータへ直接接続せず、通常画面の寿命に run を従属させない |
| シナリオ実行器 | 合成観測、人の応答、故障注入 | 試験入力と明示し、本番で暗黙の安全確認を作らない |

サービスと設定は apps/pwa/src/missions/、apps/pwa/src/config/ に維持する。
StudentServiceApi の実装からブラウザ依存を分離し、無条件の cleanup stop を
operation 単位の取消へ置き換える。/app、/console、/lab の役割は維持する。
TypeScript の fake gateway は契約テスト用とし、Python の前に第二の操作権管理者を置かない。

当初は機体ごとに一つのサービスを実行し、その内部で activity を並行動作させる。
各 activity のイベント処理は短時間で直列実行し、非同期処理を開始したら戻る。
業務イベントの queue は上限と可視の overflow を持ち、最新観測値の配信と分離する。
取消では子の追加を止め、子孫を取消・join し、timer・購読・質問を除去する。
既存の平坦な試作だけで一般的な階層状態機械が完成したとは扱わない。

## 3. 接続と operation の契約

最初は同一ホストの継承 pipe による JSON-lines を transport interface の裏で使う。
これは信頼されたローカル接続であり、認証済み network API ではない。
後の server 統合では手動操作・既存クライアントと同じ操作権管理を使い、
同じ機体に第二の runtime を起動しない。

全メッセージに protocolVersion、connectionEpoch、requestId を付ける。
operation 関連には robotId、runId、activityId、operationId も付ける。
**client が送信前に operationId を生成し、結果の受け口を登録する。**
Python は受付時に操作権の generation を付ける。更新・取消は ID と generation の
両方で照合する。地図導入時は run 設定に地図 revision を固定する。
不明なメッセージ種別や不正な値は protocol 検証で拒否する。

| メッセージ | 意味 |
| --- | --- |
| openRun／closeRun | run の受付・権限失効。close は停止確認を意味しない |
| startMotion | SI 単位の有限目標を検証し、受付または拒否 |
| renewMotion | 対象 operation の権限を、固定した進捗期限内で更新 |
| cancelMotion | 対象 operation の終了要求。応答は停止確認ではない |
| acquireHandover／clearHandover | 停止確認後に受け渡し guard を取得し、権限のある人の退避確認で解除 |
| heartbeat／snapshot | 接続の生存と現在状態。動作の再送許可にはしない |
| globalStop／recover | サービス mailbox を経由しない運用操作。復帰には明示操作と backend の証拠が必要 |

内部は距離 m、角度 rad とし、既存の度単位の簡易 API は明示的に変換する。
試作の duration→distance API は廃止する。
変換後の値を操作権の割当・adapter 呼出より前に検証する。

状態は requested → rejected、または accepted → running → terminal。
受付後に running を経由せず失敗することもある。
accepted は受付、running は runtime が実行開始を報告したことを表す。
terminal は completed／cancelled／failed／interrupted／stop-unconfirmed とし、
理由と停止証拠の metadata を付ける。
移動完了・取消・中断に「停止済み」を付けるには backend の証拠が必要。
動作前の拒否・失敗によって、別 operation の停止証拠を作らない。

terminal が受付応答より先に届いても結果を失わない。
live connection 内で request／operation ID の重複排除記録を上限付きで保持し、
満杯なら受付を拒否する。未解決の記録を黙って捨てない。
start の重複で二度移動せず、古い epoch／generation の通常 stop も拒否する。
操作権管理プロセスの生存中は、受け付けた operation に terminal を一度発行する。
server crash で配信できない場合は再接続時に不確実性を示し、
exactly-once 実行や架空の terminal を保証しない。

## 4. 停止・受け渡し・復帰

受け渡し guard は Python の共通境界で runner・joystick・既存経路のすべてに適用する。
積み降ろし中は人の退避確認だけで解除し、質問の取消・timeout・run 喪失・UI 喪失では残す。
global stop は guard 中でも有効とする。
現行サービス末尾の荷降ろし案内は受領確認ではない。
guard 付き荷降ろしは、後続の S2 サービス方針の変更として追加する。

運用者の操作許可、runner の生存、command TTL、operation の進捗期限を分ける。
watchdog に加え、更新要求を処理する前にも期限切れを検査する。
heartbeat だけでは進捗期限を延長しない。
必須観測の鮮度喪失は該当 capability を止めるが、無関係な通常画面の切断とは区別する。

短い state lock 内で権限を失効し、adapter／transport の I/O は lock 外で実行する。
停止期限は終了要求の受付から数え、stop I/O と証拠待ちの全体を含む。
期限切れでは stop-unconfirmed を通知し、再動作禁止を保持する。
遅れて届いた I/O 完了・証拠では解除しない。
古い I/O が残る間は新規受付・復帰を拒否し、新所有者への遅延 stop を防ぐ。
終了待ちにも上限を置く。取消不能な backend はプロセス隔離と、
別途検証した下流 watchdog が必要になる。

再接続では snapshot を取得し、古い質問を無効化する。移動は再送しない。
server 再起動後は運用者の明示復帰と新規 run を必要とする。
guard の永続化を設計するまでは、人の立入り状態を不明として起動時から移動を禁止する。
メモリ上の guard 消失を退避済みの証拠にしない。

## 5. 最初の Simulator 接続

1. 共通 runtime 境界へ既存 DifferentialDriveSimulator を注入する。
   合成入力と故障設定は apps/server/scenarios/ に置く。
2. 統合 runner から有限の move／turn を実行し、位置変化、局所オドメトリによる完了、
   操作権の排他を確認する。
3. 実際に simulated pose が変化している途中で、取消・故障を試す。
4. 次に、合成と明示した人物観測・応答を既存サービスへ接続する。
   approach／follow の制御を検証してから人物追従を主張する。
   汎用物体認識・地図経路移動は後続とする。

Simulator の停止証拠は simulation epoch と対応付け、対象 stop 後の
simulated actuation／velocity がゼロであることを確認する。
stop メソッドの return だけでは代用しない。
目標、観測姿勢、時刻、最終証拠を記録し、数値許容差は model から試験前に決める。
真値と推定値を区別し、地図補正で相対移動の完了判定を飛び越えない。

最初は real-time profile に限定し、pause／reset を公開しない。
導入時は simulation clock と host monotonic clock を分離する。
合意済み pause では simulation の進捗・鮮度期限を止め、生存監視と停止制御は続ける。
physics step なしで取消・reset でき、reset で epoch を更新する。
これは後続の F10 合格条件であり、TypeScript fake の試験から流用できる保証ではない。

## 6. 実装順序と合格条件

各変更の前に契約テスト・回帰テストを書く。

| 段階 | 成果物 | 合格条件 |
| --- | --- | --- |
| A | 型付きメッセージ、operation 状態・停止証拠の schema、transport interface | SI 値の拒否、重複 start、応答前 terminal、古い epoch／generation、重複排除容量 |
| B | activity 親子関係と fake capability を持つ単一 runner | 子の cleanup、queue overflow、質問取消、worker block／kill／IPC loss、孤立した移動なし |
| C | Python 共通操作権・guard | 手動・既存・runner の全経路で guard 有効、更新前期限判定、stop I/O 停滞中も応答、古い cleanup が新所有者に作用しない |
| D | 位置が変化する Simulator 接続 | move／turn の幾何、移動中停止、停止証拠の遅延・欠落、自動再開なし、scenario と trace による再現 |
| E | 最小 UI・運用者接続 | 質問への応答照合、古い応答拒否、独立した運用者 lease、通常 UI 再接続、明示的な再起動復帰 |

既存のレビュー回帰テストは維持し、subprocess 起動失敗と受付・terminal の同時配送も残す。
注入 clock で期限の直前・一致・直後を試し、実際の隔離は subprocess test で検証する。
server 自体の停止と下流の停止動作は、runner kill とは別の試験にする。
既存 server の安全関連テストと、適用可能な共通 adapter 契約テストを Simulator で実行する。
実機 adapter には固有の証拠と実測予算が必要になる。

当初の最初の実装はAとした。2026-11-07時点では、共通runtime、管理されたサービス起動、
[再現可能なサービスシナリオ](service-scenarios.ja.md)までの経路ができている。
これはA〜Eの全合格条件や実機を検証済みという意味ではない。
次は[M1：共通マップ読込みと位置契約](map-localization.ja.md)を実装する。
時計・pause/reset、実機の適格性確認は別途残る。

## 7. 要求との対応と後続範囲

主な対象は F05／F06（実行・生命周期）、F09（backend 境界）、F11（trace）、
F14（操作権の一元化）、Q01／Q03（安全・隔離）、Q04／Q06（差替え・出所）。
F10 は clock／pause／reset の検証まで部分対応とする。

地図・位置推定、YOLO provider、永続 job、S1〜S3 全体の方針、ROS／箱庭の選定、
WSL 配布、実機の適格性確認は後続とする。
実験の timeout 数値を製品の制限として採用せず、Q08 に沿って計測する。
本メモは現行起動経路や実装済み機能の表明を変更しない。
