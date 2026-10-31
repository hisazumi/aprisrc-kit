# 音声・テキストで呼べる行動を追加する

[English](adding-actions.md)

[参加者向けquickstart](challenger-quickstart.ja.md)の次に行う実習です。
サーバー・ファームウェア・LLMのプロンプトを変更せず、`/lab`へ行動を追加します。
まずSimulatorを使います。この例は移動せず自己紹介するので、行動の選択と走行を
分けて確認できます。

## 1. 行動を書く

`apps/pwa/src/missions/introduceRobot.ts`を作成します。

```ts
import { defineMission } from "./api";

export const introduceRobotMission = defineMission({
  id: "introduce-robot",
  title: "Introduce the robot",
  description: "Explain what this robot can do.",
  runningDetail: "Introducing the robot",
  script: ["Say the introduction", "Report completion"],
  trigger: {
    intent: "introduce_robot",
    description: "Introduce the robot and explain its available services.",
    examples: ["Introduce yourself", "Tell me about this robot"],
    keywords: ["introduce yourself", "about this robot"],
    response: "Sure. Let me introduce myself."
  },
  async run({ signal, say, report }) {
    signal.throwIfAborted();
    say("Hello! I can follow you or guide you to a marked destination.");
    report({ phase: "arrived", detail: "Introduction requested" });
  }
});
```

発話内容は自分のサービスで実際にできることに合わせて変更します。
`say()`はブラウザへ発話を要求するだけで、読み上げ終了を待ちません。
進捗表示は、音声の終了や実際に聞こえたことの証明ではありません。

## 2. 一覧に登録する

`apps/pwa/src/missions/index.ts`へ次を追加します。

```ts
import { introduceRobotMission } from "./introduceRobot";
```

既存の`createMissionRegistry([...])`の配列へ`introduceRobotMission,`を追加します。
既存の項目は残してください。`id`と`trigger.intent`はそれぞれ重複しない名前にします。
intent名は小文字の英字で始め、英小文字・数字・アンダースコアを使います。
予約名`stop`、`wait_here`、`report_status`、`clarify`は使えません。

登録すると、`/lab`の**Service missions**と**Human interaction**の行動一覧に入ります。
専用の`/app`サービス画面やPlaygroundのサンプルが自動的に増えるわけではありません。

## 3. 試して変更する

1. quickstartの手順でSimulatorを起動し、`/lab`を開きます。
2. 操作権を取得し、**Introduce the robot**を選んで手動実行します。
3. **Human interaction**に`Introduce yourself`を入力します。`rules`では登録した
   キーワードに一致します。マイクもAPIキーも不要です。
4. `say()`の文を変えて保存し、もう一度実行します。新しい文が聞こえるか確認します。
5. LLMを設定したら`Could you explain what you can do?`も試します。どの行動が選ばれたか
   確認してください。モデルの選択は保証されません。`rules`ではこの言い換えは一致しなくても正常です。

`rules / openai / gemini`の設定は[Assistant providers](assistant-providers.ja.md)を参照してください。
APIキーはサーバーに設定し、ミッションのコードには書きません。

| 変更する場所 | 変わるもの |
| --- | --- |
| `trigger.description`、`examples` | LLMが行動を選ぶ判断材料 |
| `trigger.keywords` | rulesとクラウド失敗時の部分一致判定 |
| `trigger.response` | ローカル判定時の応答 |
| `run()` | 実際のサービスの振る舞い |
| `say()` / `report()` | 発話 / 進捗表示 |
| `script` | 表示用の概要。実行コードではない |

LLMは登録済みintentを`action: "introduce_robot"`として返し、アプリが対応する`run()`を
呼びます。移動コードを生成するわけではありません。似た説明やキーワードの行動を複数登録すると
選択が曖昧になります。挨拶の変更なら、まず既存の`challengerStarter.ts`を編集しましょう。

## 4. 移動を加える前にテストする

リポジトリのルートで実行します。

```sh
npm run test:starter
npm run typecheck
```

既存のstarterテストは新しい行動を検証しません。
`challengerStarter.test.ts`を参考に`apps/pwa/src/missions/introduceRobot.test.ts`を追加し、
発話要求、進捗、実行前のキャンセルを確認してください。無関係な文を入力したときに
意図せずこの行動が選ばれないことも確認します。

人に反応する移動は`challengerStarter.ts`が参考になります。`waitForPerson`で人を待ち、
旋回角度を制限し、キャンセルを確認しています。[Mission API](mission-api.ja.md)だけを使い、
移動は`await`し、処理の間で`signal.throwIfAborted()`を確認してください。
人物なし・左右に人物・タイムアウト・キャンセルをSimulatorで試します。
Simulatorで動いても実機検証の完了ではありません。実機へ移す前にハードウェアガイドを確認してください。
