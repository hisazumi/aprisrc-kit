# 受講生用：荷物運びサービス

[English](student-service.md)

編集するのは **`apps/pwa/src/missions/studentCarry.ts` の1ファイル**です。
`studentCarry.run(service)` の順序・if条件・文言を変えます。Reactの編集は不要です。
このファイルは `App.tsx` → `StudentServicePanel` から読み込まれており、登録済みです。
一般のmissionRegistryには登録しません（このサービスには入力待ちの専用画面が必要です）。
既存のCarry helperはそのまま比較できます。

## 開始（Windows PowerShell）

Node.js 22.12以降または24以降、Python 3.11以降、uv、Gitが必要です。
リポジトリのルートで実行します。

```powershell
npm ci
uv sync --directory apps/server --dev
npm run dev
```

ロボット接続用の環境変数を設定せず、既定のSimulatorで起動します。
`http://localhost:5173/lab?sample=student` を開きます。
開発証明書を生成済みなら `https://localhost:5173` を使います。

1. 「Student service」内の「Acquire control」を押します。
2. Simulator toolsでFront obstacle stateをCLEAR、Perception healthをhealthyにしてApply stateを押します。次に「Confirm clear path · 30 s」で前方確認を有効にします。切れたら再確認します。これは前方安全判定を置き換えず、既存のサーバー判定も適用されます。
3. 「Start service」を押し、Virtual personの「Start scene」を押します。初期位置の仮想人物へ接近します。
4. 質問に「Yes」→「Items are loaded」を押します。Virtual personの歩行・位置操作で追従を確認し、「We have arrived」で停止します。
5. 「No」の分岐、入力待ち中の「Cancel and stop」、追従中の「Stop scene」によるVirtual person無効化（対象喪失）も試します。
6. ファイルの文言・条件を保存し、実行中なら停止してページを再読み込み、操作権・前方確認を再取得して開始します。

実際のカメラを使うサービス画面は `http://localhost:5173/app?service=student` です。
Simulatorの仮想人物・障害操作は `/lab` にあります。複数画面で同時に操作権を取得しないでください。

## 編集例と境界

```ts
await service.waitForPerson();
await service.approachPerson();
if (await service.ask("Would you like help carrying your belongings?")) {
  await service.waitForLoaded("Place your belongings on the rover.");
  await service.followPerson();
  service.say("We have arrived.");
}
```

- `waitForPerson()`：次の人物検出を最大60秒待つ。時間切れは失敗。
- `approachPerson()`：既存comeHere部品で接近。対象喪失は失敗。
- `ask(text)`：「Yes」ならtrue、「No」ならfalse。停止確認してから入力を待つ。
- `waitForLoaded(text)`：「Items are loaded」を待つ。停止確認してから待つ。
- `followPerson()`：既存追従部品を実行。「We have arrived」で中断・終了を待ち、最後に停止を確認する。対象喪失は成功にしない。
- `say(text)`：表示と発話を依頼する。発話完了は待たない。ブラウザーの音声・言語設定に依存する。

基盤側が入力ボタン、操作権喪失・切断・緊急停止・ページ非表示・画面終了時のキャンセル、対象喪失、最終停止を扱います。再実行は前の処理の終了後に限ります。停止確認の失敗は完了扱いにしません。
高水準ServiceRover経由で動かし、TTL、速度上限、操作権、前方判定、latched E-stopを変更・迂回しません。接近・追従の人物選択と観測鮮度は既存部品の契約を引き継ぎ、人物の本人認証や荷物検知は行いません。「Items are loaded」は利用者の確認です。

基盤ファイルは `service/studentService.ts` と `components/StudentServicePanel.tsx` です。今回は汎用フレームワーク、音声入力、荷下ろし検知、複数人識別は追加しません。

## 検証範囲

自動テストは既存接近・追従部品を使い、正常・拒否・キャンセル・対象喪失・停止確認失敗と画面入力を確認します。Simulatorのブラウザー画面では、接近・承諾・荷積み確認・追従・到着・停止確認まで動作を確認しました。実機、Windowsでの起動、4台同時、実ネットワーク断、スマホでの新画面は未検証です。既存システムの実機記録を新APIの検証結果として扱わないでください。
