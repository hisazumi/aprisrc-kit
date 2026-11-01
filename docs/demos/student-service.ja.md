# 受講生用：荷物運びサービス

[English](student-service.md)

編集するのは **`apps/pwa/src/missions/studentCarry.ts` の1ファイル**です。
`studentCarry.run(service)` の順序・if条件・文言を変えます。Reactの編集は不要です。
このファイルは `App.tsx` → `StudentServicePanel` から読み込まれており、登録済みです。
共通画面は `service` 引数でサービスを受け取り、荷物運びテンプレートを直接読み込みません。
一般のmissionRegistryには登録しません（このサービスには入力待ちの専用画面が必要です）。
既存のCarry helperはそのまま比較できます。

## 開始（Windows PowerShell）

Node.js 22.12以降または24以降、uv、Gitが必要です。Pythonは3.12に固定し、以下で導入します。
リポジトリのルートで実行します。

```powershell
uv python install 3.12
npm.cmd ci
uv sync --directory apps/server --no-dev
$env:APRIS_ADAPTER="simulator"
$env:APRIS_DISABLE_HTTPS="1"
$env:APRIS_SERVER_URL="http://127.0.0.1:8000"
npm.cmd run dev
```

この設定は実機ではなくPC上のSimulatorを明示的に選びます。
`http://localhost:5173/lab?sample=student` を開きます。
証明書が存在してもHTTPで起動します。既存のPython環境からの切り替えや起動エラーは
[Windowsの起動・トラブル対応](../windows-setup.ja.md)を参照してください。

1. 上部の「Student service」を開きます。既定は**Manual test**です。**Start service**で操作権・シミュレータの前方確認を準備して開始します。
2. **Enter view**でローバーの正面に人を置き、質問に「Yes」→「Items are loaded」と答えます。
3. **Test person**のMove away（離れる）、Come closer（近づく）、Walk left／right（左右に歩く）を押します。Stand still、位置変更、サービス終了、ページ非表示、移動範囲の端まで歩き続けます。速度は人物の速度で、ローバーの速度ではありません。
4. **Leave view**で対象喪失を試すか、**We have arrived**で正常終了します。**Reset person**は現在のローバーの前方1.35 mに人を置くだけで、ローバーの位置やサービスはリセットしません。対象喪失で終了したら、Enter viewとStart serviceで再度試せます。

### 発話を試す

**Person says**に文字を入れて**Say**を押すと、音声認識後の発話を模擬できます。マイク入力や音声読み上げではありません。回答待ちのときは画面の回答ボタンと同じ文言（Yes、No、Items are loaded、We have arrived、独自の選択肢）を受け付けます。大文字小文字と末尾の句読点は無視し、「はい」「いいえ」も対応します。「Stop」「停止」はサービスを中断します。それ以外はNo matching answer、回答待ちでなければNo question is waitingと表示し、別のミッションを起動しません。発話は一度だけ処理し、後の質問へ持ち越しません。LLM会話や自由な音声指示の解釈ではありません。

人の操作は環境内の仮想人物1人を動かし、ローバーとの相対位置から既存の知覚経路で観測を生成します。Enter/Leaveは視野内・視野外への即時配置です。シミュレータのLab限定で、実機や実際の人物は動かさず、マイク音声も送信しません。

### 同じ条件を再現するシナリオ

サービスを止めてから**Scenario runner**へ切り替えます。プリセット・定義編集・JSON保存／読み込み・実行状態の表示は残っています。選んでStart selected scenarioを押し、サービスへの回答後にNext stepで環境を進めます。シナリオ試験中もプリセットの選択変更は定義だけに反映されます。

シミュレータの走行許可は実行中だけ更新し、キャンセル・操作権喪失・ページ非表示で取り消します。この簡易開始はシミュレータのLab限定で、実機の開始手順は変更しません。非常停止や障害物ラッチも自動解除しません。解除・手動走行・障害注入は「Advanced controls」で行います。他のタブが操作権を持つ場合は先に解放してください。

「No」「Cancel and stop」「Lose the person」プリセット（対象喪失）も試せます。コード変更後は実行を止め、再読み込みして「Start selected scenario」を押します。

## テストシーンを定義する

シーンは環境、`studentCarry.ts` はロボットのサービスを定義します。サービスコードを変えずに異なる状況を試せます。

- **Wait in front**：人が正面で待つ。Yes/Noの分岐や荷積み確認を試す。
- **Enter from outside view**：視野外から2秒後に歩き始め、視野に入る。2回目の歩行はNext stepを待つ。
- **Walk and stop**：荷積み確認後にNext stepを押すと、終点まで歩いて止まる。
- **Lose the person**：Next stepで歩き、歩行完了後にもう一度押すと消える。正常到着ではなく対象喪失として停止するかを確認する。

**Edit scene**でローバーの位置・向き、人の初期位置、順番に実行するステップを編集します。行動はWalk（複数の通過点）、Stand、Disappear。開始条件はNext stepまたはAfter delayです。秒数は直前の行動の終了から数え、最初の行動だけシーン開始から数えます。歩行は最後の通過点で終了します。時間待ちは遅延付きStandでも表せます。歩行中にNext stepで飛ばすことはできません。サービスの状態を自動で判断する条件はないので、追従試験では承諾・荷積み確認を終えてから手動で進めます。

座標はマップと同じワールド座標、単位はmです。向き0度では+xが前方、+yが左。画面の向きは度、JSONはラジアンです。歩行速度は人物の速度で、ローバーの速度ではありません。相対位置と視野角から検出を計算し、描画画像を認識しているわけではありません。

**Selected scenario**は編集する定義であり、実行状態を持ちません。試験中もプリセット選択・編集・読み込み・保存ができ、実行中の試験には影響しません。**Running**は開始時にコピーした定義による実行で、進行表示とNext stepはこちらにあります。終了後は**Last trial**として最後の進行状態を残します。人物の行動が完了しても、サービスの成功を意味するわけではありません。

**Start selected scenario**を押すたびに、選択した定義のコピーを初期状態から実行します。試験中なら先に中断・終了を待ち、停止を確認してから切り替えます。停止確認に失敗した場合や切り替え中にキャンセルした場合、新しい試験は開始しません。Reset sceneは不要です。停止待ち中に選択を変えても、開始を押した時点の定義で実行します。キャンセル・操作権喪失・ページ非表示でシーンの時計も停止します。シミュレータの位置リセットAPIは注入済みの故障もクリアします。非常停止・障害物ラッチは自動解除しません。

**Export JSON**で保存、**Import JSON**で検証して読み込みます。読み込むだけでは動きません。編集を残す場合は再読み込み前に保存してください。形式は`version: 1`、読み込みは64 KBまで、20ステップ・各20通過点まで、座標は±10 m、待ち時間0〜120秒、人物の速度0.01〜0.5 m/sです。[シーン例](scenes/person-enters.json)も参照できます。チェック項目は人が観察するためのもので、自動合否判定ではありません。複数人、障害物形状、サービスへの回答の自動化は今回の範囲外です。

実際のカメラを使うサービス画面は `http://localhost:5173/app?service=student` です。
Simulatorの仮想人物・障害操作は `/lab` にあります。複数画面で同時に操作権を取得しないでください。

## 編集例と境界

```ts
await service.waitForPerson();
await service.approachPerson();
if (await service.ask("Would you like help carrying your belongings?")) {
  await service.confirm("Place your belongings on the rover.", "Items are loaded");
  await service.followPerson();
  service.say("We have arrived.");
}
```

- `waitForPerson()`：次の人物検出を最大60秒待つ。時間切れは失敗。
- `approachPerson()`：既存comeHere部品で接近。対象喪失は失敗。
- `ask(text)`：「Yes」ならtrue、「No」ならfalse。停止確認してから入力を待つ。
- `confirm(text, buttonLabel = "Continue")`：停止確認後、指定した名前のボタンを待つ。
- `choose(text, choices)`：停止確認後、選択肢ごとのボタンを表示し、選ばれた文字列を返す。選択肢は空でなく、重複・空白だけの文字列を含めない。
- `waitForLoaded(text)`：互換用。`confirm(text, "Items are loaded")` と同じ。
- `followPerson({ message?, buttonLabel? })`：既存追従部品を実行。アダプタの設定で有効なら連続追従を使う。既定のボタンは「We have arrived」。到着時は直ちに停止を要求し、実行中の処理の終了と停止確認を待ってから戻る。対象喪失は成功にしない。
- `say(text)`：表示と発話を依頼する。発話完了は待たない。ブラウザーの音声・言語設定に依存する。

### 画面の共通利用

質問やボタンは荷物運び専用の画面実装ではなく、サービス側で指定します。

```ts
const destination = await service.choose("Where would you like to go?", ["Desk", "Reception"]);
await service.confirm(`Ready for ${destination}?`, "Ready");
service.say(`You selected ${destination}.`);
```

この例は行き先の選択・表示だけで、目的地までの移動は行いません。移動には対応する行動を明示的に組み合わせます。画面には質問を一つずつ表示するので、各操作は `await` で順に呼びます。キャンセルは回答を選択せず、入力待ちを中断します。

別のサービス定義を使う場合は、`App.tsx` の `StudentServicePanel` に `service={yourService}` を渡します。同じ位置の画面で定義を切り替える場合はReactの `key` も変え、旧サービスをキャンセルしてください。操作権・前方確認・キャンセル・非常停止は共通です。汎用的な画面作成フレームワークではなく、小さなサービス実行画面です。

基盤側が入力ボタン、操作権喪失・切断・緊急停止・ページ非表示・画面終了時のキャンセル、対象喪失、最終停止を扱います。再実行は前の処理の終了後に限ります。停止確認の失敗は完了扱いにしません。
高水準ServiceRover経由で動かし、TTL、速度上限、操作権、前方判定、latched E-stopを変更・迂回しません。接近・追従の人物選択と観測鮮度は既存部品の契約を引き継ぎ、人物の本人認証や荷物検知は行いません。「Items are loaded」は利用者の確認です。

基盤ファイルは `service/studentService.ts` と `components/StudentServicePanel.tsx` です。今回は汎用フレームワーク、音声入力、荷下ろし検知、複数人識別は追加しません。

## 検証範囲

自動テストは既存接近・追従部品を使い、正常・拒否・キャンセル・対象喪失・停止確認失敗と画面入力を確認します。Simulatorのブラウザー画面では、接近・承諾・荷積み確認・追従・到着・停止確認まで動作を確認しました。実機、Windowsでの起動、4台同時、実ネットワーク断、スマホでの新画面は未検証です。既存システムの実機記録を新APIの検証結果として扱わないでください。

今回の共通画面化では、任意の選択肢・確認文言、不正な回答、距離指定の移動中の到着、到着時の停止失敗、mainの連続追従との連携を自動テストに追加しています。テスト用ローバーによる検証であり、新たな実機検証ではありません。上記のブラウザー動作確認は元のテンプレートの検証記録です。
