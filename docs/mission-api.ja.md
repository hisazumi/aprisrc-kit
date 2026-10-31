# Mission API and service templates

[English](mission-api.md)

`apps/pwa/src/missions/`と`apps/pwa/src/config/`は、サービス固有の振る舞いと設定を追加するための編集領域である。ミッションはローバー固有の通信方式やモーター命令を使わず、`ServiceRover`の高水準APIだけを呼び出す。

## Editable files

```text
apps/pwa/src/
  missions/
    api.ts                 # 公開APIとMissionDefinition。基盤側が管理する
    observations.ts        # 認識イベントを待つ小さな補助API
    challengerStarter.ts   # 最初に編集する人物反応starter
    demoScenario.ts        # 最小のミッション例
    index.ts               # 画面へ公開するミッションの登録
  config/
    teamProfile.ts         # チーム名、サービス名、既定ミッション
    courseMarkers.ts       # コース上の既知マーカー座標
    index.ts               # 設定の集約
```

通常は新しいミッションファイル、`missions/index.ts`の登録一覧、`config/`だけを編集する。WebSocket、操作権、安全制御、`RoverAdapter`は編集対象にしない。自然言語から開始できるミッションでは、同じミッション定義内に`trigger`も記述する。

## ServiceRover API

```ts
await rover.move(0.40)       // 0.40 m 前進
await rover.move(-0.20)      // 0.20 m 後退
await rover.turn(90)         // 左へ 90 度旋回
await rover.turn(-45)        // 右へ 45 度旋回
await rover.stop()            // 通常停止

const pose = await rover.getPose()
const unsubscribe = rover.onPose((nextPose) => {
  console.log(nextPose.x, nextPose.y, nextPose.yaw)
})
unsubscribe()

const stopPeople = rover.onPerson((event) => {
  if (event.status === "lost") void rover.stop("person lost")
})
const stopMarkers = rover.onMarker((event) => {
  console.log(event.markerId, event.poseCorrection?.applied)
})
stopPeople()
stopMarkers()
```

`move`と`turn`はLocal Serverがposeを監視しながら実行する。呼び出しは動作完了まで待機し、中断または失敗時はPromiseがrejectされる。速度を省略した場合はプラットフォームの既定値を使う。

```ts
await rover.move(0.40, 0.15) // distanceM, speedMps
await rover.turn(90, 0.60)   // angleDeg, speedRadS
```

`getPose()`はLocal Serverから最後に受信したposeのコピーを返す。未接続または最初のstateを受信する前はrejectされる。`onPose()`は最新poseを通知し、購読解除関数を返す。購読時点でposeが存在する場合は、そのposeも直ちに通知する。

`onPerson()`と`onMarker()`は、Local Serverが受理した認識イベントだけを通知する。低信頼度、古い観測、未知マーカー、不正なpayloadはlistenerへ届かない。対象が一定時間見えなくなると`status: lost`が届く。追従などのミッションは`lost`を受けたときに`stop()`する状態遷移を実装する。

一度だけ人物を待つサービスでは、購読処理を直接書かず`waitForPerson()`を利用できる。
人物検出、timeout、`Cancel mission`によるabortを同じPromiseで扱う。

```ts
const person = await waitForPerson(rover, signal, 10_000)
await rover.turn(person.bearingDeg ?? 0)
```

`stop()`は通常停止をLocal Serverへ送信できた時点でresolveされる。非常停止ではないため、危険時はService AppまたはOperator Consoleの`Emergency stop`を使う。

## Defining a mission

最初の開発演習は[Challenger quickstart](challenger-quickstart.ja.md)に従い、
`challengerStarter.ts`を編集する。`demoScenario.ts`は、認識を使わず公開motion APIだけを
使う最小例である。

```ts
import { defineMission } from "./api"

export const greetingMission = defineMission({
  id: "greeting",
  title: "Greeting patrol",
  description: "Move forward, greet, and return.",
  runningDetail: "Forward 0.30 m → turn around → return",
  script: [
    "await rover.move(0.30)",
    "await rover.turn(180)",
    "await rover.move(0.30)"
  ],
  trigger: {
    intent: "greeting_patrol",
    description: "Run the short greeting patrol.",
    examples: ["挨拶してきて", "Run the greeting patrol"],
    keywords: ["挨拶", "greeting patrol"],
    response: "Okay. I will run the greeting patrol."
  },
  async run({ rover, config, signal, report, say }) {
    say("Starting the greeting patrol.")
    report({ phase: "approaching", detail: "Moving to the greeting point" })
    signal.throwIfAborted()
    await rover.move(0.30)
    signal.throwIfAborted()
    await rover.turn(180)
    signal.throwIfAborted()
    await rover.move(0.30)

    console.log(config.team.serviceName)
  }
})
```

`signal`は`Cancel mission`が押されたときにabortされる。各動作の間と、待機や認識処理の中で確認する。実行中の`move`または`turn`はLocal Serverへの`cancel_motion`でも停止される。

## Natural-language trigger

コード作成から登録・試行までの例は
[音声・テキストで呼べる行動を追加する](adding-actions.ja.md)を参照してください。

`trigger`は任意である。省略したミッションは従来どおり画面から選択して実行する。指定した場合、PWAは登録済みtriggerだけをLocal Serverの意図解釈候補として送る。

- `intent`: ミッションを識別する安定したID
- `description`: LLMが用途を選ぶための説明
- `examples`: LLMへ渡す代表的な発話例
- `keywords`: APIキーがない場合のローカル部分一致候補
- `response`: ローカル判定時に英語で読み上げる応答

ローカル判定で複数ミッションに一致した場合は、最も長いキーワード一致を優先する。`stop`、`wait_here`、`report_status`、`clarify`はプラットフォーム予約意図であり、ミッションから登録できない。特に停止表現はLLMやミッションより先に処理される。

LLMは登録済み`intent`と`destination`、`follow_distance`だけを返す。速度、角度、距離、モーター値、通信コマンドは出力schemaに存在しない。選択されたミッションの`run()`が、通常の`ServiceRover` APIを使って具体的な振る舞いを実装する。

`report()`はHuman InteractionとMission画面へ状態を通知し、`say()`はプラットフォームが選択した英語音声で応答する。人物追従のような判断ロジックは学生のミッションファイルに残し、通信TTLや速度上限はLocal Serverに残す。

## Registering a mission

作成した定義を`missions/index.ts`へ追加すると、Development Labの**Service missions**と
**Human interaction**から利用できる。`/app`はCarry assistant専用の利用者画面であり、
registryへ追加しただけでは汎用mission選択肢を表示しない。`/app`へ組み込む場合は、その
service UIが利用するmissionを明示的に選ぶ。

```ts
import { demoScenarioMission } from "./demoScenario"
import { greetingMission } from "./greetingMission"

export const missionRegistry = createMissionRegistry([
  demoScenarioMission,
  greetingMission
])
```

IDは空文字列にできず、重複したIDは起動時に拒否される。既定で選択するミッションは`config/teamProfile.ts`の`defaultMissionId`で指定する。

## Service configuration

`teamProfile.ts`にはサービス表示名と既定ミッションを定義する。`courseMarkers.ts`には、コース座標系におけるマーカーの既知位置をSI単位で定義する。これらは`MissionContext.config`から読み出せる。

設定はサービスの内容を変えるためのものであり、速度上限、TTL、非常停止などの安全値は含めない。

## Running and cancelling

汎用missionはDevelopment Lab (`/lab`) で操作権を取得し、missionを選択して
`Run selected mission`を押す。Service App (`/app`) はCarry assistantの状態遷移から
専用missionを開始する。Operator Console (`/console`)を別tabで開くと、poseと軌跡を
監視できる。

同時に実行できる高水準モーションは1件だけである。`Cancel mission`、通常停止、非常停止、操作権解放、WebSocket切断はモーションを停止する。手動ジョイスティック入力は実行中のミッションを中断して優先される。

## Safety boundary

- Local Serverはモーション中も短いcommand TTLを更新する。更新が止まれば安全レイヤーがローバーを停止する。
- 速度上限、TTL、操作権、非常停止はミッションから変更できない。
- 実機固有プロトコルと`RoverAdapter`はミッションから参照しない。
- PWAやミッションからモーターコントローラへ直接命令しない。
- LLMや認識器の出力を`drive()`へ直接渡さない。

## Current limitations

現在の`move`は開始地点からの平面距離、`turn`はyawの累積変化を使う。障害物回避や経路計画は行わない。実機ではencoder / IMU odometryの精度、床面の滑り、停止距離を確認して許容誤差を調整する必要がある。
