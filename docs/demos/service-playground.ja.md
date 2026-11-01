# Service playground

[English](service-playground.md)

[実習ガイド](playground-workshop.ja.md)でSimulatorを起動し、
`/playground?service=my-service`を開きます。共通ヘッダーでMy service、Carry helper、
Person greeting、Mobile receptionistを選びます。画面を移動してもサービスの選択は維持します。

## 手動で試す

### 音声で回答する

作者はボタン表示や処理を変えずに、受け付ける別名を配列で追加できます。

```ts
const accepted = await service.ask("Would you like help?", {
  yes: ["yes please", "sure", "please help me"],
  no: ["no thanks", "not now"]
});
await service.confirm("Place your belongings on the rover.", "Items are loaded",
  ["ready", "all set", "loaded"]);
const destination = await service.choose("Where?", [
  { value: "desk", label: "Desk", phrases: ["my desk", "the desk please"] },
  { value: "entrance", label: "Entrance", phrases: ["the entrance please"] }
]);
await service.followPerson({ phrases: ["we are here", "arrived"] });
```

`label`はボタン表示、`value`はプログラムへの戻り値です。
表示名そのものと`phrases`の各表現を受け付けます。従来の文字列だけの選択肢も使えます。
`ask`は真偽値を返し、省略可能な`yes`・`no`配列で別名を指定します。
`confirm`は第3引数、`followPerson`は`phrases`オプションで別名を指定します。
Carry helperとMy serviceに記入例があります。マイク入力とPlaygroundの仮想発話は同じ判定です。
大文字・小文字と文末の句読点を無視して照合しますが、部分一致や自由な文章理解ではありません。
複数の回答に一致する場合は選択せず待機します。別名の重複を避けてください。
**Stop**は停止用なので回答の別名には使わないでください。

**Voice conversation**はServiceで標準オン、Playgroundで標準オフです。
どちらの画面でも切り替えられます。サービスを開始し、求められたらマイクを許可します。
オンの場合は質問の読み上げ終了後に英語の聞き取りを開始します。
**Yes**、**No**、**Items are loaded**、**We have arrived**など、表示中の選択肢を答えてください。
ボタン回答も残ります。回答は選択肢との照合で処理し、LLMは不要です。

オフの場合も**Answer by voice**を押すと一度聞き取ります。
一致しない場合やマイクが使えない場合は勝手に進まず、再試行かボタン回答を待ちます。
キャンセル・操作権喪失・画面離脱・回答完了時に聞き取りを終了します。
通常の音声コマンドと、表示中の質問への回答は別の入力です。

HTTPS（またはlocalhost）と音声認識対応ブラウザが必要です。
ブラウザの制限で再度タップが必要になる場合があります。非対応の場合は回答ボタンを使います。
音声認識は非常停止ボタンの代わりにはしないでください。

1. **Manual test**のまま**Start service**を押します。操作権とシミュレータの前方確認を自動で準備します。
2. **Enter view**で人物を出し、**Move away**、**Come closer**、**Walk left**、
   **Walk right**、**Stand still**で動かします。**Leave view**は対象喪失の試験です。
3. 表示された質問に回答します。My serviceとCarry helperは**Yes**、
   **Items are loaded**、**We have arrived**を使います。Person greetingは一度向きを合わせて挨拶します。
4. **Person says** / **Say**は現在の質問への認識済み文章を模擬します。
   マイク認識やLLMとの会話ではありません。
5. **Cancel and stop**で終了します。サービスやテストモードを変える前に停止してください。
   **Restart service**は前の試験を停止してから再開します。

## マーカーとシナリオ

**Test markers**は全サービスにあります。地図上に位置があっても検出済みとは限りません。
**Markers visible**の既定は**オフ**です。オンにすると視野条件に応じて観測を生成します。
実行中は座標を変更できません。

Mobile receptionistは開始前にEntrance/Deskの座標を設定し、**Markers visible**をオンにして、
**Start service**、**Enter view**、行き先、**Let's go**の順に操作します。
マーカーが見えなければその場で旋回探索し、検出したら接近します。探索・接近には上限があり、
走り回って探すことはありません。人物は開始のきっかけで、同行監視はしません。
実機のマーカー案内はService・Playgroundとも無効です。

再現可能な環境は、停止後に**Scenario runner**へ切り替え、編集または読み込み、
**Start selected scenario**で開始します。手動開始のステップは**Next step**で進めます。
編集を残すには再読み込み前にJSONを保存してください。[シーン定義](student-service.ja.md)を参照。
人物の手動操作とシナリオは全サービスで共通です。

## コードと診断

**Implementation**は実際のサービス定義を、サービス・地図の下に全幅で表示します。
読み取り専用で、エディタや命令単位のデバッガではありません。
My serviceは`apps/pwa/src/missions/myService.ts`、
組み込み例は`apps/pwa/src/service/examples/`です。停止して編集し、再読み込みして同じ条件で試します。

挨拶設定は`config/greetingStarter.ts`にあります。旧専用画面のプレビュースライダー、
**Follow me** / **Guide me**ボタン、実行行の強調表示は共通画面にありません。
汎用ミッション、対話、診断、障害注入は**Advanced controls**にあります。
汎用ミッションと共通サービスは同時に動かさないでください。

シミュレータの観測は幾何学的な入力で、描画画像を認識しているわけではありません。
実カメラ・ロボットは[実機Playground](hardware-playground.ja.md)を参照してください。
