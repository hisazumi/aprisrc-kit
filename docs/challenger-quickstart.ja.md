# APRISRC Kit 参加者向けquickstart

[English](challenger-quickstart.md)

APRISRC向けの自分のサービスを作る入口です。荷物運びは初期例で、指定課題ではありません。
まずロボット・カメラ・LLMキー不要のSimulatorで始めます。

## 起動

Node.js 22.12+または24+、npm、Python 3.12、uvを用意します。
WindowsのPowerShellで、リポジトリ直下から実行します。PCのブラウザはEdgeまたはChromeを使います。

```powershell
uv python install 3.12
npm.cmd ci
uv sync --directory apps/server --no-dev
$env:APRIS_ADAPTER="simulator"
$env:APRIS_DISABLE_HTTPS="1"
$env:APRIS_SERVER_URL="http://127.0.0.1:8000"
npm.cmd run dev
```

<details>
<summary>macOS / Linuxの場合（Bash・zsh）</summary>

```bash
uv python install 3.12
npm ci
uv sync --directory apps/server --no-dev
APRIS_ADAPTER=simulator APRIS_DISABLE_HTTPS=1 APRIS_SERVER_URL=http://127.0.0.1:8000 npm run dev
```

以降の確認コマンドは`npm.cmd`を`npm`に置き換えます。

</details>

起動時の問題は[Windowsのトラブル対応](windows-setup.ja.md)を参照してください。
`http://localhost:5173/playground?service=my-service`を開きます。ポートは起動表示を優先してください。

## 変更せずに試す

1. **Manual test**のまま**Start service → Enter view**を押します。
2. **Yes → Items are loaded**と回答します。
3. **Move away → Stand still**で人物を動かし、追従・距離を保った停止を観察します。
4. **We have arrived**を押し、**Service complete (stop confirmed)**を確認します。
5. **No**、**Leave view**、**Cancel and stop**でも試します。

開始できない場合は接続、Simulator設定、非常停止、他タブの操作権を確認します。
SimulatorのPlaygroundでは仮想の前方確認を自動準備・更新します。障害物認識ではありません。
このサービスにマーカーは不要で、**Markers visible**の既定はオフです。

## 自分のサービスを変更する

**Implementation**に表示される`apps/pwa/src/missions/myService.ts`を編集します。
表示名、質問文、awaitで呼ぶ処理の順序を変えます。例えば
`await service.followPerson(...)`の直前に
`await service.confirm("Ready to follow?", "Ready");`を追加すると、
追従前に確認が一つ増えます。

停止してから編集・再読み込みし、同じ手動入力で比較します。コード欄は読み取り専用です。
API、選択肢、シーンJSONは[My serviceガイド](demos/student-service.ja.md)を参照。
組み込み例は`service/examples/`に分離され、`service/catalog.ts`が定義とソースを
選択欄につなぎます。低水準missionを登録しただけではサービスは増えません。

## テストと拡張

```powershell
npm.cmd test
npm.cmd run typecheck
npm.cmd run build
```

正常終了、拒否、対象喪失、中断、停止失敗をテストします。
通すために操作権、TTL、速度上限、非常停止を変更しないでください。

低水準の移動行動を追加する場合は[Mission API](mission-api.ja.md)と
[音声・テキストで呼べる行動](adding-actions.ja.md)を参照します。
登録ミッションと文章・音声の解釈はPlaygroundの**Advanced controls**にあります。
共通サービスを止めてから使ってください。triggerを登録しても共通パネルの回答や行動には自動追加されません。

AIには[開発ガイド](ai-assisted-development.ja.md)、[技術メモ](ai-service-context.ja.md)と
現在のソースを渡してください。画面写真だけで判断させないでください。

## 実機へ進むとき

[UGV02自己試験](hardware/ugv02-self-test.ja.md)または[iron-X人追従](hardware/ironx-follow.ja.md)へ進みます。
共通実機UIは操作権取得、**Confirm clear path · 30 s**、**Start service**が別です。
旧Carry専用UIの許可自動更新は引き継いでいません。
動かす前に[実機Playground](demos/hardware-playground.ja.md)を確認してください。
実機マーカー案内は無効で、シミュレータ成功は実機の保証ではありません。
