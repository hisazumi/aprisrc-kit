# APRISRC Kit

[English](README.md)

**APRISのロボットチャレンジ「APRISRC」で、参加者がサービスを試作するための開発キット。**

APRISはカンファレンス、APRISRCはそのロボットチャレンジ、APRISRC Kitはこのソフトウェアと
開発キットを指す。参加者がスマホの認識・対話とロボットの移動を組み合わせた独自のサービスを設計し、
Kitはそのための共通API、Simulator、参照機材との接続、サンプル、ガイドを提供する。

挨拶・追従・荷物運び・マーカー案内は開発の出発点で、課題の指定解ではない。
Simulatorから始め、対応する高水準missionを実機で検証する。
責務と用語は[目的と位置づけ](docs/positioning.ja.md)を参照する。
このREADMEは競技規則・審査基準・公式または必須の位置づけを定めるものではない。

## Start here

| やりたいこと | 読むもの |
| --- | --- |
| Windowsから設定済みのiron-X・UGV02を起動する | [実機の起動方法](docs/hardware/startup.ja.md) |
| 体験・開発・実機引き継ぎの入口を選ぶ | [試す・変更する・引き継ぐ](docs/handoff.ja.md) |
| MVPを動かし、小さな改善を2つ試す（20〜30分） | [Playground実習ガイド](docs/demos/playground-workshop.ja.md) |
| 挨拶・人追従・マーカー案内の操作を確認する | [Service playground](docs/demos/service-playground.ja.md) |
| できているデモを動かす | [Human interaction demo](docs/demos/human-interaction.ja.md) |
| 自分のサービスを作る | [参加者向けquickstart](docs/challenger-quickstart.ja.md) |
| WebのチャットやAIとサービスのコードを書く | [AIを使った開発手順](docs/ai-assisted-development.ja.md) |
| mission APIと安全境界を知る | [Mission API](docs/mission-api.ja.md) |
| 対応UGV02で試す | [UGV02 self-test](docs/hardware/ugv02-self-test.ja.md) |
| PC・iPhoneでiron-Xの監視付き人追従を試す | [iron-X人追従](docs/hardware/ironx-follow.ja.md) |
| 開発・保守資料を探す | [Documentation index](docs/README.ja.md) |

実装済み機能、確認済み範囲、残る制約は[Platform status](docs/platform-status.ja.md)を参照する。

## What works today

- Simulator上で人物反応、接近、追従、荷物運びサービスを試せる。
- browser内の人物・上半身・APRIS marker認識をmissionから利用できる。
- textまたは対応browserの音声入力を、許可済みの高水準intentへ変換できる。
- 操作権、速度上限、command TTL、通信断時停止、E-stopをserverが一元管理する。
- APRIS WebSocket firmwareを書き込んだUGV02で、bounded turn/reverseと監督付き人物追従を
  実機確認済みである。

既定adapterはSimulatorである。実機は開発用firmwareとprivate LANを使用し、無人の自律走行や
一般環境の障害物回避を保証しない。

```text
Smartphone / Browser PWA
        │ WebSocket
        ▼
FastAPI Local Server
  control ownership / safety / logs
        │ Rover Adapter
        ▼
Simulator or supported rover adapter
```

## Repository layout

```text
apps/pwa/               React + TypeScript + Vite PWA
apps/server/            FastAPI Local Server and Simulator
apps/server/scenarios/  Reproducible Simulator input and fault scenarios
apps/server/config/     Local Server course marker configuration
packages/protocol/      Versioned JSON message schema
firmware/               UGV02 firmware sources and profiles
docs/                   Guides, reference, operations, and design records
```

## Development

通常の開発環境は**Windows + PowerShell**です。PCではEdgeまたはChromeで開きます。
Git、Node.js 22.12以降または24以降（npm含む）、uvを用意してください。
Python 3.12は以下で導入します。WSL、macOS、Safariはシミュレータの開始に不要です。
詳しくは[Windowsの起動・トラブル対応](docs/windows-setup.ja.md)。

```powershell
git clone https://github.com/hisazumi/aprisrc-kit.git
cd aprisrc-kit
```

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

開発サーバーはバックエンドを8000番、画面を5173番で起動します。
この例はSimulatorとPC用HTTPを明示的に選び、既存の証明書があってもHTTPSには切り替えません。
ポートが使用中の場合は起動表示を確認してください。

- [My serviceのPlayground](http://localhost:5173/playground?service=my-service)：まずここで試す
- [Service](http://localhost:5173/service?service=my-service)：選んだサービスの利用者画面
- [Console](http://localhost:5173/console?service=my-service)：操作・監視

`http://127.0.0.1:8000/api/status`でJSONが返ることも確認します。
画面が開くだけではPythonサーバーの起動確認にはなりません。
終了はCtrl+Cです。画面の役割は[PWA views](docs/pwa-views.ja.md)を参照してください。

スマホカメラを使うときだけ[HTTPSの準備](docs/local-https.ja.md)へ進みます。
Windows PCにiPhoneを組み合わせられます。iPhoneのSafariはスマホ側のブラウザであり、
Macを必要とする意味ではありません。カメラ映像ではなく、認識した構造化観測をサーバーへ送ります。

変更後の確認（PowerShell）：

```powershell
uv sync --directory apps/server --dev
npm.cmd run typecheck
npm.cmd test
npm.cmd run build
uv run --directory apps/server ruff check src tests
uv run --directory apps/server pytest
```

ブラウザ変更はService・Playground・Consoleの該当画面も確認してください。
Windows向けの案内を標準にしていますが、この文書変更でWindows実機試験を追加したわけではありません。
接続設定・保守資料は[ドキュメント索引](docs/README.ja.md)から参照できます。

## Coordinate convention

- `x`: forward
- `y`: left
- `yaw`: counter-clockwise positive
- distance and velocity: metres and metres per second
- angles and angular velocity: radians and radians per second

## Scope

基準実機はWaveshare UGV02の開発用APRIS firmware構成である。
実験的なiron-X ROS 2 Humble対応では、PC上のKitをLAN経由で接続できる。
iPhoneによる人追従の成功報告があるが、最新の停止確認修正と0.15 m/s設定は実機再試験待ち。
手順・確認範囲は[iron-X人追従](docs/hardware/ironx-follow.ja.md)を参照する。
広範な実機評価とLiDARを使う自律移動は引き続き[ロードマップ](docs/roadmap.ja.md)で管理する。

## 公開と開発への参加

コード開発はこちらの公開repoで行う。[初回公開の範囲](docs/release-scope.ja.md)と[開発への参加](CONTRIBUTING.ja.md)を参照する。
独自部分は[MIT](LICENSE)、同梱firmwareは既存GPLである。[ライセンスと出典](LICENSING.md)を確認する。

### 受講生用サービステンプレート

`apps/pwa/src/missions/myService.ts` でサービスの流れを編集し、Simulatorでは `/playground?service=my-service`、カメラを使う画面では `/service?service=my-service` を開きます。設定、入力ボタン、安全上の境界、確認範囲は[開始手順](docs/demos/student-service.ja.md)（[English](docs/demos/student-service.md)）を参照してください。
