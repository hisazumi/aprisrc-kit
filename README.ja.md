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
| 体験・開発・実機引き継ぎの入口を選ぶ | [試す・変更する・引き継ぐ](docs/handoff.ja.md) |
| MVPを動かし、小さな改善を2つ試す（20〜30分） | [Playground実習ガイド](docs/demos/playground-workshop.ja.md) |
| 挨拶・人追従・マーカー案内の操作を確認する | [Service playground](docs/demos/service-playground.ja.md) |
| できているデモを動かす | [Human interaction demo](docs/demos/human-interaction.ja.md) |
| 自分のサービスを作る | [参加者向けquickstart](docs/challenger-quickstart.ja.md) |
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

Requirements: Node.js 22.x (22.12+) or 24+, npm, Python 3.11 or later, and `uv`.

```bash
git clone https://github.com/hisazumi/aprisrc-kit.git
cd aprisrc-kit
npm install
uv sync --directory apps/server --dev
npm run dev
```

`npm run dev` starts the FastAPI server at `http://localhost:8000` and the Vite development server at `http://localhost:5173`. The PWA development server proxies `/ws` and `/api` to FastAPI. 開発証明書が `.certs/` に存在する場合、Vite は自動的に `https://localhost:5173` へ切り替わり、WebSocket も WSS になる。

稼働確認は`/api/livez`、走行可能性を含むreadinessは`/api/readyz`、詳細なruntime
snapshotは`/api/status`で確認する。CLIでは次を実行する。

```bash
uv run --directory apps/server apris-doctor --json
```

- `https://localhost:5173/app`: スマートフォン用Service App
- `https://localhost:5173/console`: PC用Operator Console
- `https://localhost:5173/lab`: Simulator開発用の統合画面

`/`へアクセスした場合もService Appを表示する。各画面の役割は [PWA views](docs/pwa-views.ja.md) を参照する。

PC の `localhost` ではカメラを利用できるが、スマートフォンから PC のローカル IP アドレスへ接続する場合は HTTPS が必要になる。セットアップ方法は [Local HTTPS and smartphone setup](docs/local-https.ja.md) を参照する。映像はサーバへ送信せず、PWA内で認識した構造化観測だけを送る。

変更後は次の標準チェックを実行する。

```bash
npm run typecheck
npm test
npm run build
uv run --directory apps/server ruff check src tests
uv run --directory apps/server pytest
```

すべて成功してからコミットする。ブラウザに関係する変更では、必要に応じて`/app`、`/console`、`/lab`も実際に開いて確認する。

実機adapterの設定、factory firmware診断、実装詳細などの保守手順は
[Documentation index](docs/README.ja.md)から辿る。

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

`apps/pwa/src/missions/studentCarry.ts` でサービスの流れを編集し、Simulatorでは `/lab?sample=student`、カメラを使う画面では `/app?service=student` を開きます。設定、入力ボタン、安全上の境界、確認範囲は[開始手順](docs/demos/student-service.ja.md)（[English](docs/demos/student-service.md)）を参照してください。
