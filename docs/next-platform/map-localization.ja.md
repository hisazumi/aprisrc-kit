# 次期プラットフォーム：共通マップと位置推定の契約

[English（正本）](map-localization.md)

状態：M1/M2＋Simulator登録経路の最小実行まで実装、2026-11-07。実機・学生APIへの接続は後続。
[要求 F01〜F03・F04・F11、Q01・Q04・Q06・Q08](requirements.ja.md)と
[アーキテクチャ](architecture.ja.md)を具体化する。
調査基準は `next-platform` の `39c6d92c98cd29404b17e1f26f9892f17f2a29f2`。

## 1. 今回決めること

会場のマップを共通にし、機体が供給するオドメトリを疎な既知マーカで補正する。
学生は名前付き地点と登録経路を選び、基盤が座標変換・位置品質・移動制御を担う。
最初の実装は **マップ読込みと検証、および位置契約の型・テスト** とする。
その後に推定器、最後に登録経路移動を接続する。

地図が共通でも機体ごとの校正は必要である。車輪径・トレッド・エンコーダ、
カメラ内部パラメータ・機体への取付姿勢、機体寸法・停止性能は機体プロファイルに置く。
地図とオドメトリだけから初期の絶対位置・向きは決まらない。

## 2. 既存実装と再利用範囲

| 現在の部品 | 再利用するもの | 次期向けの不足 |
| --- | --- | --- |
| `odometry.py` / `WheelImuOdometry` | エンコーダ＋IMUからの局所姿勢 | epoch、時刻の契約、距離・旋回に応じた誤差評価。現在のconfidenceは経験的な指標 |
| `perception.py` / `PoseFusion` | odom→courseの平面剛体変換、既知ID・距離・位置／角度innovationの拒否 | 未位置合わせ状態、地図版、撮影時刻のodomとの対応、品質劣化モデル |
| `runtime.py` | 相対move/turnはadapterの局所姿勢を使用し、配信用姿勢だけ補正 | 新しい位置snapshotと地図走行の品質ゲートへの接続 |
| `course-markers.json` / `courseMarkers.ts` | マーカ配置と行先の例 | サーバとPWAに重複、地図版・マーカ実寸・独立した地点／経路がない |
| `browserPerception.ts` | マーカ観測の入力経路 | 固定16cmと画像幅による概算距離。校正済み6DoF観測ではなく、向きも供給しない |
| `mobileReceptionist.ts` | 目的地マーカへ接近し、喪失時に止まるサービス例 | 疎なマーカの間を地図で移動する能力ではない |
| `test_perception.py`、既存runtime/Simulator試験 | 補正・不正観測・相対移動等の回帰試験 | 下記M1〜M4の契約・統合試験を追加 |

現在のPoseFusionは初期のゼロ変換にもcourseラベルを付ける。古いマーカ補正は
anomalyになるが、odomのconfidenceが高ければ地図上の位置品質が高く見え得る。
また、観測の鮮度は検証するものの補正には受信時に取得したodomを使う。
これらを地図走行の成立条件としてそのまま使用しない。

## 3. 責務と座標系

| 部品 | 責務 |
| --- | --- |
| Map loader | スキーマ・参照・有限値・版を検証し、不変のマップsnapshotを公開 |
| Robot / sensor profile | 機体、odom供給元、カメラ校正・外部変換、対応能力・運用制限 |
| Observation normalizer | 入力時刻・frame・校正版・マーカidentityを検証し、機体基準へ変換 |
| Localization | odom履歴と観測を対応付け、map→odom変換と位置品質を提供 |
| Route capability | 登録経路と位置から移動を決め、共通走行窓口へ要求 |
| Motion authority | 既存の単一所有者・TTL・guard・前方状態・停止根拠を維持 |

`T_A_B` はB座標をA座標へ変換するものと定義する。
`T_map_base(t) = T_map_odom(t) × T_odom_base(t)`。
`base`は機体の制御基準点、odomはその連続した局所移動、mapは会場固定座標。
SI単位、右手系、機体前方+x・左+y・反時計回りyawとし、mapの原点と+x方向を会場で固定する。
カメラの光学座標は校正情報で明示変換し、機体座標と同一視しない。

補正はT_map_odomだけを更新し、局所odomを上書きしない。相対move/turnの目標・進捗は
同じodomEpochで評価し、補正によって完了を飛び越えない。
odomの再起動・リセットはepochを更新し、旧変換・履歴を無効化する。
移動中なら停止・中断し、再位置合わせと新たな明示開始を必要とする。

## 4. Map v1案

最初は単一階の平面、名前付き地点と有向の登録経路。地点とマーカは別のものとする。
目的地に必ずマーカを貼る必要はない。逆方向の経路は別に登録する。

```json
{
  "schemaVersion": 1,
  "mapId": "apris-demo-room",
  "revision": "1",
  "frameId": "map",
  "units": { "length": "m", "angle": "rad" },
  "markers": [
    { "family": "example-square", "id": 1, "sizeM": 0.16,
      "pose": { "xM": 0.0, "yM": 0.0, "zM": 0.8,
        "rollRad": 0.0, "pitchRad": 0.0, "yawRad": 0.0 } }
  ],
  "places": [
    { "id": "start", "label": "Start", "pose": { "xM": 0.0, "yM": 0.0, "yawRad": 0.0 } },
    { "id": "desk", "label": "Desk", "pose": { "xM": 2.0, "yM": 0.0, "yawRad": 0.0 } }
  ],
  "routes": [
    { "id": "start-to-desk", "from": "start", "to": "desk",
      "via": [ { "xM": 1.0, "yM": 0.0 } ] }
  ],
  "initialPoseCandidates": [ { "id": "start-placement", "placeId": "start" } ]
}
```

これは形式説明用であり、実測会場・検出器設定・走行許可ではない。
`family`は配備時の対応検出器と一致させる。マーカ姿勢はマーカ中心の3D姿勢、
回転は `Rz(yaw) Ry(pitch) Rx(roll)`。マーカ固有軸は検出器プロファイルで正規化する。
平面推定器でもカメラ取付・壁上マーカの高さや傾きを無視しない。

M1では未知フィールドを拒否し、ID／(family,id)の一意性、有限値、正の実寸、
地点参照、経路順序、必須欄、対応schemaVersionを検証する。
経路の幾何はfrom→via→toの折れ線。空のviaは直線を意味し、黙って経路探索しない。
ファイルサイズ・要素数・ID長・座標の運用範囲をloader profileで制限する。
全体を検証してから原子的に有効化し、部分読込みや未知版の推測はしない。

`mapId + revision + contentDigest`で実体を識別する。digestは読込んだUTF-8バイト列の
SHA-256とし、同内容の書式変更でも別digestとなる。run開始時にロボット／校正／品質profile版と
ともに固定する。同じID・revisionに異なるdigestが来た場合は拒否する。
走行中・run中の交換は拒否し、停止根拠の確認と旧run終了後に運用者が明示適用する。
交換時は再位置合わせが必要。画面にはサーバの有効snapshotを配信する。

壁・進入禁止領域・走行幅はF01の後続拡張であり、M1だけでF01完了とはしない。
M3の登録経路実行前には機体幅・停止余裕を含む通行範囲の検証を追加する。
未対応geometryを含む地図を黙って走行に使わない。
初期位置候補は配置手順の参照であり、自動的に現在位置の根拠にはならない。

## 5. 位置と観測の契約

以下は新しい内部契約の意味であり、既存stateのフィールドの意味は変更しない。

| 情報 | 必須の意味 |
| --- | --- |
| スコープ | robotId、controlEpoch、odomEpoch、localizationEpoch、mapのID/revision/digest、profile版 |
| 時刻 | clockId/clockEpoch、sampleTime、receivedTime、単調なsequence。別時計を直接減算しない |
| odomPose | 未補正のT_odom_base、freshness、入力センサー状態 |
| mapPose / mapFromOdom | 同じsampleTimeの推定値と変換。未位置合わせならnull |
| quality | unlocalized / tracking / degraded / lost、理由、推定誤差、最後の補正、補正後の距離・旋回量 |
| 出所 | real / simulated / synthetic、推定器・校正版。Simulator真値は試験側だけで比較 |

推定誤差は位置m・角度radのprofile定義の指標とし、その評価法・版・適用範囲を付ける。
統計的な共分散や保証付き上界でない指標をそれらと呼ばない。
未知値はnullとして品質不足扱いにし、0やconfidence=1で埋めない。
`tracking`だけでも走行許可にはならず、経路の必要精度とfreshnessを別途照合する。

観測はsourceId/sessionEpoch/sequence/observationId、撮影時刻と時計、地図版、
校正版、marker family/id、frameId、相対姿勢、品質・出所を持つ。
時刻変換とその誤差が許容範囲内にあり、撮影時刻を挟む同一epochのodom履歴から
補間できる場合だけ補正する。履歴は有界にし、外挿・古い観測の現在時刻への付替えをしない。
初期実装では一度受理した撮影時刻より古い観測を拒否し、複雑な遅延融合は後回しにする。
変換した撮影時刻でT_map_odomを求め、現在のodomへ適用する。

機体座標へ正規化した姿勢観測を使うとき、
`T_map_base(capture) = T_map_marker × inverse(T_base_marker(capture))`。
3D変換を適用した後、平面モデルに整合する観測だけを平面へ射影する。
時刻・重複・有限値・校正・未知ID・距離・平面整合・位置と角度innovationを検証し、
拒否理由を記録する。棄却観測でlastCorrectionや有効期限を更新しない。
既存の2.5秒・3m・90度等を新しい走行向けの採用値とはしない。

## 6. 初回位置合わせと疎なマーカ

起動直後はunlocalized。次のどちらかで初期の対応を確立する。

- 運用者が、指定地点への配置と向きを確認し、校正済みprofileの不確かさを伴って初期化する。
- 既知マーカの十分な姿勢観測で位置・向きを初期化する。曖昧な解は棄却／追加観測を要求する。

方向情報のない単一マーカの相対位置だけでは、任意の初期位置・向きを一意に決められない。
既存のブラウザ概算観測だけで初期位置合わせが完了したとは扱わない。
初期化では任意のゼロ姿勢とのinnovation比較を使わず、別の初期化検証を行う。
tracking中の異常な大補正は拒否する。lostからの再位置合わせは停止後の明示操作とし、
停止済みの経路を自動再開しない。

マーカ不在だけで直ちにlostにはしない。経過時間、走行距離、累積旋回、odom品質から
誤差を増加させ、測定で決めた経路profileの範囲内ならデッドレコニングを続ける。
degradedは品質低下を示し、同じprofileで明示的に許容された場合だけ続行できる。
必要精度・鮮度を満たさない場合は移動を中断し、lostまたは品質不足理由を返す。
再観測で品質が戻っても中断済みoperationは復活しない。

## 7. 登録経路移動への接続（M3以降）

学生向けは`goTo(placeId)`、`followRoute(routeId)`等の高水準能力とする。
初期goToは確認できた開始地点と目的地を結ぶ登録経路が一意の場合だけ選択し、
曖昧ならrouteIdを要求する。経路外の現在位置から開始地点まで勝手に直行しない。
未対応能力、未知地点、地図版不一致、未位置合わせ、精度不足を開始前に返す。

経路実行は同じrun/activity/operationと移動所有権に結び付く。
短い有界move/turnの間に位置を再評価し、必要なら補正後の経路を再計算する。
大きな補正や経路逸脱では停止して再評価し、区間番号を飛ばして成功にしない。
走行中にもPython側で品質を監視し、runnerが監視を忘れても該当経路走行を止める。
この停止を既存のmotion authorityへ接続し、第二の指令主体を作らない。

到着は同一map/epochでの位置・必要なら向きの許容差、十分な位置品質、
停止根拠をすべて満たした時だけ。到着後の受け渡し完了は別の業務条件である。
地図／経路／マーカ観測は前方CLEARや運用許可の代用にならない。
一般的な障害物回避、SLAM、任意経路計画、実機の停止保証は今回追加しない。

## 8. 実装順序と合格条件

各段階で契約テストを先に追加する。既存の走行保護・service scenario回帰も保持する。

| 段階 | 成果物 | 合格条件 |
| --- | --- | --- |
| M1：次の変更 | Python map loader、版付きsnapshot、位置／観測契約、例地図、検証profile | 不正値・重複・参照切れ・容量超過・未知版・同版別digest・run中交換を拒否。失敗で旧map維持。未初期化mapPose=null |
| M2 | 共通localization、注入時計と有界odom履歴、明示初期化、品質モデル | 別の初期姿勢、平行移動＋回転、±π、撮影遅延、時計ずれ・履歴不足・旧epoch・順序逆転、マーカ喪失／再捕捉、大補正の拒否、odom不変 |
| M3 | 登録経路能力、通行範囲と品質ゲート、既存authorityへの接続 | 同じ地図を異なる機体profileで走行。相対move/turnが補正で早期完了しない。品質喪失時停止、停止未確認、guard・lease・前方UNKNOWN、取消後再開なし |
| M4 | `apps/server/scenarios/`の入力とtrace、運用表示・手順 | マーカ間移動、ドリフト補正、喪失停止、再初期化、map/odomリセット、旧観測拒否を反復。推定値と真値を別記録 |

M2/M3では合成条件の期待誤差・許容値を先に固定し、境界直前・一致・直後を試す。
実機で使うマーカ間隔・観測遅延上限・精度・停止余裕は別に計測してprofile化する。
機体差を吸収するとは契約と校正手順を共通化することであり、全機体で同じ精度を約束しない。

## 9. 移行と今回の範囲

既存`course-markers.json`は明示的な変換入力として残す。実寸・family・校正など
不足する情報は運用者が補い、暗黙の値で地図走行を有効にしない。
既存course表示・marker接近サービスは互換経路に残し、新しいmap位置契約とは区別する。
新しいサービスhostのguideTo対応はM3まで未対応のままとする。

ROS／箱庭／Godot／MuJoCoの選定を待たず、軽量Simulatorで
M1〜M4を検証できる境界を定めた。リッチな3D接続と認識器の高度化はこの契約へ後から接続する。

## 10. M1の実装状況

`course_map.py`に不変なPydanticモデル、`load_map(bytes)`、`MapStore`を追加した。
`localization_contract.py`は位置snapshotと機体座標へ正規化済みのマーカ観測の型を定義する。
例地図は`apps/server/config/maps/demo-room.json`。検出器familyは例示用である。

MapLimitsの既定値は256KiB、マーカ256、地点256、経路512、初期位置候補256、
各経路の中間点256、各座標の絶対値／マーカ実寸上限1000m。識別子は64文字、
labelは256文字。これは資源制限と試験用の値であり、実機の運用範囲ではない。
位置・観測契約は数値文字列、booleanの数値化、非有限値、未知フィールドを拒否する。
観測時刻は正規化後の同じ時計を使い、撮影が受信より未来なら拒否する。

MapStoreは同期・単一スレッド用の内部部品で、登録したrunが残る間は交換を拒否する。
`bind`で地図とprofile版を固定し、`release`は停止根拠を作らない。
`activate(stopped=True)`は将来の信頼されたauthorityが停止根拠を確認して呼ぶ契約であり、
ブラウザから渡す走行許可ではない。成功した再適用は同じ地図でもlocalizationEpochを更新する。
失敗時は有効地図・epochとも維持する。地図版履歴は既定256件、runは1件で、容量超過を拒否する。
履歴はプロセス内のみであり、再起動をまたぐ版の同一性検証は永続化接続時の課題。

**実行中のHTTPサービスにはまだ接続していない。** 既存runの存在や実機停止を
この部品単独で検出することはできない。authorityとの結線・原子的なrun受付、
必要能力と校正profileの照合はM2/M3の統合試験対象とする。
型の検証だけでは、姿勢変換の計算、観測の順序・epochの実行時照合、推定精度の妥当性、
走行許可を保証しない。M2の実装範囲は次節に記載する。

検証は`test_course_map.py`と`test_localization_contract.py`。
未位置合わせのnull、欠けた姿勢／変換、品質と補正履歴の矛盾、未来の撮影時刻、
地図交換失敗後の状態維持などを含む。

## 11. M2：位置推定の実装状況

`localization.py`の`Localization`は独立した同期処理の推定器である。
`localization_geometry.py`が平面変換・補間と3Dマーカ変換を担う。
既存の`PoseFusion`や稼働中のサービスは変更していない。

- `add_odometry`：機体・control/odom/clock epoch・連番・時刻・出所を照合して有界履歴へ追加。
  位置の飛躍、速度・角速度超過、座標範囲外を検知する。入力odomを書き換えない。
- `initialize_placement`：停止根拠を確認した運用側が初期位置候補を選び、最新odomとの変換を設定。
- `initialize_marker`：停止根拠を確認した運用側が、曖昧でない完全な姿勢観測で初期化。
  任意のゼロ姿勢とのinnovation比較は行わない。
- `correct`：初期化済みの場合だけ、撮影時刻のodomを補間して変換を更新。
  マーカ中心の3D姿勢と相対姿勢を合成し、機体の高さ・傾きがprofile内なら平面へ射影。
  位置・角度innovationを検査してから反映する。平滑化やEKFではなく、検証済み観測による変換の置換。
- `snapshot`：最新odom、map姿勢、変換、品質・理由・誤差指標・最後の補正を返す。
  最初のodomがまだなければ`odometry-unavailable`。odom取得後も初期化前のmapPoseはnull。
- `reset`：停止を確認し、新しいlocalizationEpochとodomEpochで履歴・補正・重複記録を破棄する。
  時計逆行時にはclockEpochの変更も必要。地図・profile自体の交換は別インスタンスを作る。

観測契約に必須の`poseAmbiguous`を追加し、trueの観測は補正にも初期化にも使わない。
入力元とsessionEpochは推定器の構築時に登録し、最大16入力元。校正版・地図版・品質profile版も照合する。
時計変換は入力側の責務であり、推定器は既に同じ時計に正規化された時刻を受け取る。
変換誤差の上限に加え、撮影時刻±時計誤差を覆う履歴も要求する。
同時刻以前の観測、重複ID、連番逆行、履歴外、古い観測、不正な出所は拒否する。
棄却した観測で補正時刻や誤差を更新しない。

品質は位置・角度それぞれについて、初期／マーカ誤差＋走行距離・累積旋回・経過時間の
係数で計算する。時計誤差分も補正時の誤差へ加える。これはprofile付きの経験的な指標であり、
統計的共分散でも、物理的な保証上界でもない。degraded/lostの閾値は位置・角度の両方に適用する。
マーカが見えないだけではlostにせず、測定された運用profileで許容される区間を走る設計である。

lostはラッチする。odom鮮度切れ・欠落・センサー利用不能・推定誤差超過を、新しい入力で
暗黙に解消しない。次のodom受信時にも前回入力からの鮮度切れを評価する。
再位置合わせは明示操作だけとし、喪失前に撮影した観測は再初期化に使わない。
大きなodom飛躍や時計異常は再初期化だけで解除せず、epoch付きresetを必要とする。

試験profileは`apps/server/scenarios/localization/profile.json`。
履歴256点／3秒、補正受付記録256件などを明示する。受付記録の上限で古いIDを捨てて
再受付することはせず、新たな補正を拒否し、必要なら停止・epoch付きresetを行う。
全数値は合成試験用であり、実機・会場への推奨設定ではない。

`test_localization.py`は仮想時計で、遅延補間、±π、3D姿勢、各種境界、品質劣化／回復、
喪失ラッチ、古いepoch、時計逆行、履歴／記録容量、既存WheelImuOdometryからの入力を検証する。
次はM3に向け、実行時のodom・校正済み観測をこの推定器へ結び付け、品質喪失を
Pythonの共通走行保護へ伝える。その後に登録経路の移動を接続する。
**M2推定器単独では停止要求を送らず、走行許可も与えない。実行系との接続は次節。カメラ校正・実機精度・経路走行の検証は未実施。**

## 12. M3の前段：Simulator実行系への接続

`runtime_localization.py`がRunnerPortとM2推定器を接続する。
現段階は固定の例地図と合成試験profileを使う、明示的に有効化するSimulator専用モード。
登録経路実行や物理ロボットへの接続はまだ提供しない。

```sh
uv run --directory apps/server python -m apris_server.operator_console --localization
```

フラグなしの既存デモは従来のまま。上記モードでは全走行入口に位置品質を要求する。
起動時から共通motion interlockを保持し、位置未確定のまま移動できない。
独立したオドメトリ取得と品質監視を開始し、サービスrunnerや画面の監視コードに依存しない。

運用手順：

1. `/console`で操作権を取得する。初回のSimulatorは例地図の開始地点・開始方向にある。
2. 配置確認をチェックし「開始地点で位置合わせ」を押す。
3. 人の退避を確認して「明示復帰」する。
4. 試験runまたはサービスを明示的に開始する。利用者画面は引き続き別の`/app`。
5. 品質喪失後は停止確認・run終了を待つ。入力の障害を解消し、実際に開始地点と向きを
   確認して再位置合わせ→明示復帰→新規開始とする。移動後に単にボタンを押して原点扱いにしない。

地図・校正・品質profile・localizationEpochをrunの受付時に固定する。
地図の差替えAPIは今回公開していない。位置合わせは運用者ID・controlEpoch・
localizationEpoch・配置確認を検証し、run／guard／他の操作所有者がある間は拒否する。
共通runtimeの静止状態とSimulatorの停止根拠、pending I/Oがないこと、freshで正常なodomを
確認してから新しい位置推定世代へ進む。古い位置合わせ要求の再送は拒否する。
位置合わせはguardやE-stopを解除せず、常に別の明示復帰を必要とする。

Simulatorは同じロック内で、推定odom・その正確な単調時計の取得時刻・odomEpochを返す。
ノイズ・古い状態・センサー故障の設定を経由した観測値を使い、真値へ置換しない。
odomリセットはepochを変更し、同じ座標へ戻った場合も検知する。
カメラ時計をここで推測変換することはしない。

監視はtracking以外で走行を禁止する保守的なprofileとした。degradedも停止対象。
オドメトリ取得失敗・取得task終了・更新停止・品質不足・epoch変更では、まずinterlockで
すべての新規移動を禁止し、run失効と既存runtimeの停止処理へ進む。
manual/legacy入口にも同じ禁止が効く。独立watchはportの要求ロックやadapter I/Oを待たずに
禁止を設定し、遅延した要求はinterlock epochで排除する。
止まれたrunはinterrupted、停止根拠を期限内に得られない場合はstop-unconfirmedとなる。
遅いI/Oが残れば復帰を拒否し、入力復活だけでは走行禁止・run・質問を復活させない。

試験用の実時間予算は取得間隔20ms、取得timeout 150ms、feed更新期限250ms、
watch間隔10ms。推定器側のodom鮮度期限と既存run/command/stop期限も維持する。
これらは実機の停止性能を保証する値ではない。
状態表示はキャッシュ済みの観測を使い、表示要求がセンサーI/O待ちで監視を塞がない。
取得前はstate=nullと位置未確定を表示する。

接続先の最小API：

- `GET /api/state`の`localization`：品質snapshot、禁止理由、地図identity、入力元世代、run binding。
- `POST /api/localization/initialize`：運用者・世代・candidateId・confirmedを持つ明示位置合わせ。
- `POST /api/localization/observation`：正規化済みのSimulatorマーカ観測。M2の完全なスコープと
  `sourceId=simulator-marker`、現在のsourceEpochを必要とする。旧世代や曖昧な観測は拒否し、
  禁止中の観測から再初期化しない。実カメラ入力用の校正・認証プロバイダではない。

APIは既存loopback/token/origin境界を使う。入力元世代は認証情報ではなく照合用であり、
共有tokenを持つローカル試験参加者を役割ごとに分離する認証はまだない。

`test_runtime_localization.py`で移動中のセンサー故障・古い状態・遅延、停止根拠欠落、
要求ロックを占有する遅延受付、manual入口、odom reset、旧観測の再送を試す。
HTTPの位置合わせ／復帰順序とブラウザDOM操作も回帰試験に追加した。
次は地図の通行範囲と機体寸法の確認を含めて登録経路能力を実装する。M3全体の完了ではない。

## 13. M3：登録経路の最小実行

`route_plan.py`が通行範囲と機体profileを検証し、`route_execution.py`が既存RunnerPortの
bounded move/turnをつないで実行する。実機への接続、任意経路探索、障害物回避、
学生サービスhostのguideTo置換は今回の範囲に含めない。

Map v1のrouteに任意の`corridorWidthM`を追加した。未指定の既存地図は読めるが、経路走行には
使えない。中心線はfrom→via→toの順序付き折れ線で、各区間の通行範囲は幅を直径とする
端点の円を含むカプセル形状とする。この領域全体が通行可能だと運用側が確認する契約であり、
壁や障害物を自動判定した結果ではない。

走行可能な中心位置の余裕は、通行幅の半分から次を差し引く。

- 機体がその場旋回しても収まる外接円の半径
- 停止余裕
- profileの最大位置誤差
- 短区間の移動中に向きの誤差で生じる横方向の余裕

余裕が正でない経路、参照切れ、長さゼロの区間、区間数／動作予算を超える経路を拒否する。
開始地点から離れている場合は経路へ勝手に合流しない。
`method=place`は目的地に入る登録経路が一意の場合に選び、複数ならrouteId指定を要求する。
現在位置を使った一般的な経路探索や複数経路の選択最適化は行わない。

実行の契約：

- run・地図・localizationEpoch・profile・route実行IDを固定し、区間順序を維持する。
- 相対移動の進捗は既存odomのまま。区間完了と停止根拠の後に、地図位置から次の操作を決める。
- route中は他のbounded motionと受け渡し開始を拒否する。運用者の全体停止は有効。
- 位置・向きの品質、区間からの逸脱、地図補正の急変、全体期限を監視する。
  大きな補正で経由点を飛ばして成功にしない。失敗・キャンセルではrunを失効し、移動禁止を保持する。
- runner/operatorのleaseは従来どおり外側が更新する。経路実行自身は自分のmotion TTLだけを更新する。
- 到着には終点までの距離＋位置誤差、方向差＋方向誤差、それぞれの許容範囲と停止根拠が必要。
  受け渡しの完了は別のサービス判断である。
- 同一requestIdの再送は当初の結果を返し、再実行しない。内容違いは拒否する。
  拒否済み要求も記録する。32件を超えたら受付を拒否し、古い要求を黙って再利用しない。
- 中止要求はroute実行IDとrunEpochを照合する。停止根拠が期限内に得られなければ
  stop-unconfirmedを保持し、後から証拠が届いても到着や中止成功へ書き換えない。

試験設定は`apps/server/scenarios/localization/route-profile.json`。
外接円半径18cm、停止余裕5cm、最大位置誤差10cm、到着条件は誤差込み12cm／0.2rad。
長い時間の動作を一度に発行せず、最大6cm／0.15radに分割する。
現行の比例減速・最低速度・完了許容差から区間時間を見積もり、既存1.2秒の進行期限と
整合するか開始前に確認する。watchdog期限は延長していない。
全体30秒・最大24動作と既存motion記録容量も維持し、超過時は失敗として止める。
これらの値と誤差モデルは合成試験用であり、実機の精度・安全性を保証しない。

`--localization`の例地図を`apps/server/config/maps/route-demo.json`へ切り替えた。
開始点(0,0)→経由点(0.16,0)→机(0.16,0.16)、終点方向π/2、通行幅1mの小さなL字経路である。
従来の`demo-room.json`は形式説明用として保持する。

運用画面では位置合わせ→明示復帰→試験run開始の後、「机まで登録経路で移動」を押す。
移動中は直接move/turnボタンを無効化し、中止ボタンと区間・結果を表示する。
サービスプロセスが動作中の手動経路開始は拒否する。

追加API（loopback/token/origin境界は従来どおり）：

- `POST /api/route/start`：controlEpoch、runId、runEpoch、requestId、method（route/place）、targetId。
- `POST /api/route/cancel`：id（route実行ID）、runEpoch。
- `GET /api/state`のroute：実行ID、地図/profile、waypoint、actions、status、reason。

テストは`test_route_plan.py`、`test_route_execution.py`、既存HTTP/DOM試験。
L字完走と静止、同一要求の再送、機体・通行幅の不整合、キャンセル、位置品質喪失、
M2では受理される大きさのマーカ補正による経路中断、終盤減速を含む時間見積りを検証する。
学生向けサービスAPIとの接続と配送例は14節を参照。
実機試験、詳細geometry、一般的な経路探索、M4の包括的な記録・再生は別途残る。

## 14. 学生向けサービスからの登録地点移動

接続型Nodeホストの `await service.guideTo('desk')` を登録経路実行へ接続した。
対象地点へ入る経路が一意で、現在位置がその開始地点にある場合だけ開始する。
開始受付では完了せず、同じrun・route実行IDの到着判定と停止を待って戻る。
経路失敗、中断、位置品質喪失、未登録地点では例外となり、その後の到着案内へ進まない。
ActivityRunnerのスコープ終了時は当該経路を中止して結果を待つ。
停止を確認できなければcleanup失敗として扱う。ホストはoperator leaseを更新しない。

`POST /api/service/route/start` は現在のサービスrunId/runEpochを照合して開始する。
既存の手動経路開始禁止を解除せず、managed serviceからも利用できる。
認証は従来の共有ローカルトークンであり、独立したユーザ権限分離ではない。

参照サービスは `apps/pwa/src/missions/registeredDelivery.ts`。
荷積み確認→運用側の安全確認→登録地点へ移動→到着案内→荷受け確認→
運用側の安全確認→配送完了、の順で進む。到着と受け渡し完了を区別する。
既存 `myService.ts` は変更していない。

起動例（server依存関係をインストール済みの環境、リポジトリルート）：

```sh
APRIS_SERVICE=registered-delivery PYTHONPATH=apps/server/src \
  apps/server/.venv/bin/python -m apris_server.operator_console --localization
```

表示された `/console` を開き、operator接続、開始地点での位置合わせ、明示復帰、
試験用の前方CLEAR入力を行い「サービス開始」を押す。手動試験runは開始しない。
利用者は別の `/app` で荷積み・荷受けに回答し、運用者が別途安全確認を解除する。
`APRIS_SERVICE` 未指定は従来のcarryサービス。未知の値は起動失敗となる。
再実行には開始地点への戻しと位置合わせが必要で、自動帰還は行わない。

`registered-delivery.test.ts` は独立したPython HTTPサーバとNodeホストを使用し、
managed起動でのL字移動・到着後の受け取り確認、途中キャンセル時の停止と到着非通知、
古いrunの拒否、位置機能なし・未登録地点の拒否を確認する。
これは合成入力と平面シミュレータの検証であり、実機での配送検証ではない。
次は位置・経路・サービスイベントを一緒に記録し、失敗原因を追跡できるようにする。

診断記録の初期実装を追加した。使い方・上限・未実装の再生については
[位置・経路・サービスの診断ログ](diagnostic-trace.ja.md)を参照。
