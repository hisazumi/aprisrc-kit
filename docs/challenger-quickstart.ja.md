# APRISRC Kitの参加者向けquickstart

[English](challenger-quickstart.md)

AIとコードを書く場合は[AIを使った開発手順](ai-assisted-development.ja.md)を参照してください。
渡すファイル、変更範囲、ローカルでの確認方法をまとめています。

APRISRCの参加者がAPRISRC Kitを使って独自サービスを作るためのガイドです。
starterはAPIを示す例で、課題の指定解ではありません。サービスの目的と人との関わりは
参加者が決めます。[目的と位置づけ](positioning.ja.md)を参照してください。

この手順は、APRISの基盤コードやfirmwareを変更せず、人物に反応する小さな
ローバーサービスを作るための最短経路である。最初は実機を使わずSimulatorで
確認する。所要時間の目安は30〜45分。

## 1. Start the development environment

必要なものはNode.js 22.12以降または24以降、npm、Python 3.12（固定）、`uv`です。
Windowsでは[PowerShellの起動・トラブル対応](windows-setup.ja.md)を使ってください。
以下はmacOS/LinuxのBash・zsh向けです。リポジトリのルートで実行します。

```bash
npm ci
uv python install 3.12
uv sync --directory apps/server --no-dev
APRIS_ADAPTER=simulator APRIS_DISABLE_HTTPS=1 npm run dev
```

`http://localhost:5173/lab`を開く。上の設定は証明書があってもPC用HTTPとSimulatorを
明示的に選ぶ。UGV02は不要。adapter変更前に既存serverを停止する。
変更と比較を案内に沿って試すなら[Playground実習](demos/playground-workshop.ja.md)を使う。
このガイドは汎用Mission Panelを使う。

## 2. Run the starter unchanged

1. **Acquire control**を押す。
2. **Virtual person**で配置を`Left`または`Right`にして**Start scene**を押す。
3. **Service missions**で`Person greeting starter`を選ぶ。
4. **Run selected mission**を押す。
5. ローバーが人物の方向へ最大15度旋回し、`Greeting complete`になることを確認する。

動かない場合は、接続表示、操作権、E-stop、Virtual personの`visible`表示を順に確認する。

## 3. Change one service

編集するファイルは次の1つだけである。

```text
apps/pwa/src/missions/challengerStarter.ts
```

まず`apps/pwa/src/config/greetingStarter.ts`の`greeting`、`maxTurnDeg`、`minTurnDeg`を変更する。
[Service playground](demos/service-playground.ja.md)では挨拶と旋回角度を一時変更して試せる。保存するとブラウザへ
自動反映される。次に`run()`内で公開APIを組み合わせる。

```ts
say("I found someone.")
await rover.turn(10)
await rover.move(-0.10, 0.05)
await rover.stop("service completed")
```

前進は前方安全状態が`CLEAR`の場合だけ許可される。最初の改造では、旋回、後退、
発話、人物の`bearingDeg`による条件分岐を推奨する。速度制限、通信TTL、操作権、
E-stopをミッションから変更してはいけない。

## 4. Add a voice or text trigger

新しい行動のコード、登録、変更して試す手順は
[音声・テキストで呼べる行動を追加する](adding-actions.ja.md)を参照してください。

同じファイルの`trigger`に、サービスを表すintent、発話例、ローカル判定用keywordを
記述する。`/lab`の**Human interaction**欄へkeywordを含む文を入力すると、API keyが
なくても登録したミッションを開始できる。

```ts
trigger: {
  intent: "greet_person",
  description: "Find and greet a visible person.",
  examples: ["人に挨拶して", "Greet the person"],
  keywords: ["挨拶", "greet"],
  response: "Okay. I will look for someone."
}
```

LLMや音声認識はミッションを選ぶだけで、距離、速度、モーター指令を生成しない。

## 5. Check the work

```bash
npm run test:starter
npm run typecheck
```

スターターの振る舞いを変更した場合は
`apps/pwa/src/missions/challengerStarter.test.ts`の期待値も変更する。ほかのmissionを
追加する場合は新しいファイルを作り、`apps/pwa/src/missions/index.ts`へ登録する。

## 6. Optional hardware handoff

Simulatorでstarterを確認できた後、同じmissionを対応UGV02へ移せる。一人で行う接続、
raised-wheel確認、床上試験、停止、診断は[UGV02 self-test](hardware/ugv02-self-test.ja.md)に
分離している。別機種を使う場合は
[Hardware assumptions and porting](hardware/service-hardware-porting.md)を参照する。

## Editable boundary

通常のチャレンジャーが編集する範囲は次だけである。

- `apps/pwa/src/missions/<service>.ts`
- 対応する`<service>.test.ts`
- `apps/pwa/src/missions/index.ts`
- `apps/pwa/src/config/`

`useRoverSocket.ts`、server runtime、adapter、firmware、protocol schemaはプラットフォーム
側の所有物である。必要な機能が公開APIにない場合は、内部実装を迂回せず運営者へ
API要求として記録する。
