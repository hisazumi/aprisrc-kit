# Service playground

[English](service-playground.md)

[実習ガイド](playground-workshop.ja.md)でSimulatorを起動し、
`/playground?service=my-service`を開きます。共通ヘッダーでMy service、Carry helper、
Person greeting、Mobile receptionistを選びます。画面を移動してもサービスの選択は維持します。

## 手動で試す

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
