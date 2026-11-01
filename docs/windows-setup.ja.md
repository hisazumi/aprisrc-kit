# Windowsの起動・トラブル対応

[English](windows-setup.md)

## 初回起動（PowerShell）

Git、Node.js 22.12以降または24以降（npmを含む）、[uv](https://docs.astral.sh/uv/getting-started/installation/)を用意します。
`package.json`があるリポジトリのルートで実行してください。

```powershell
uv python install 3.12
npm.cmd ci
uv sync --directory apps/server --no-dev
$env:APRIS_ADAPTER="simulator"
$env:APRIS_DISABLE_HTTPS="1"
$env:APRIS_SERVER_URL="http://127.0.0.1:8000"
npm.cmd run dev
```

ルートと`apps/server`の`.python-version`でPython 3.12を選択します。
システム全体のPythonを入れ替えたり、シミュレータのために先にRustを準備したりする必要はありません。
通常は対応するビルド済みパッケージを利用します。ただし配布ミラーやインストール設定にも依存します。
パッケージ定義のPython最低バージョンは、それ以降の全バージョンでWindows向けビルド済み依存が
揃うことを保証しません。案内では固定した3.12を使います。

`http://localhost:5173/playground?service=my-service`を開きます。5173番が使用中ならViteが表示するポートを使います。
`[pwa]`と`[server]`の両方の起動を確認してください。画面が開くだけではバックエンドの起動確認にはなりません。
`http://127.0.0.1:8000/api/status`でJSONが表示されればバックエンドに接続できています。
終了はCtrl+Cです。この設定はPC上のシミュレータ用で、スマホカメラや実機は別途設定が必要です。

PowerShellでは`$env:NAME="value"`を使います。Bashの`NAME=value command`形式は使いません。
`npm.cmd`なら実行ポリシーを変更せずに`npm.ps1`のブロックを避けられます。
環境変数はそのPowerShellセッションに設定されるため、新しいターミナルでは再設定してください。

## 既存のPython 3.15環境から切り替える

APRISの開発サーバーをすべて停止してから、リポジトリのルートで実行します。

```powershell
uv python install 3.12
if (Test-Path apps/server/.venv) {
    $backup = ".venv-backup-" + (Get-Date -Format "yyyyMMdd-HHmmss")
    Rename-Item -Path apps/server/.venv -NewName $backup
}
uv sync --directory apps/server --python 3.12 --no-dev
uv run --directory apps/server --no-dev python --version
```

最後の表示が`Python 3.12.x`であることを確認し、初回起動欄の環境変数と`npm.cmd run dev`を実行します。
退避した仮想環境はバックアップです。移動先でそのまま実行するものではありません。コミット・共有もしないでください。

## トラブル対応

| 症状 | 確認・対応 |
| --- | --- |
| `npm.ps1`がブロックされる | `npm.cmd`を使います。実行ポリシーを緩める必要はありません。 |
| `[vite] ws proxy error ... ECONNREFUSED` | 最初の`[server]`エラーと8000番の`/api/status`を確認します。Pythonの準備に失敗してフロントだけ起動している場合があります。 |
| `watchfiles`・`maturin`・Rustのビルド失敗 | 実際にPython 3.12を使用しているか確認し、上の手順で環境を作り直します。3.12のインストールだけでは既存3.15環境は切り替わりません。なおビルドされる場合は依存のエラー全文と配布元設定を確認します。 |
| パッケージ取得のタイムアウト | `$env:UV_HTTP_TIMEOUT="300"`を設定して`uv sync --directory apps/server --no-dev`を再実行します。最初からキャッシュを消すと再取得が増えるため避けます。 |
| `127.0.0.1`ではバックエンドに接続できるがViteから失敗する | `$env:APRIS_SERVER_URL="http://127.0.0.1:8000"`を設定しViteを再起動します。以前の接続先指定が残っていないか確認します。 |
| 8000番が使用中 | 前のAPRISサーバーを停止します。無関係なプロセスは停止しません。 |

バックエンドだけ調べる場合は`npm.cmd run dev:server`で起動し、`Application startup complete`と
`/api/status`を確認します。**Ctrl+Cで停止してから`npm.cmd run dev`へ進んでください。**
後者もバックエンドを起動するため、同時に実行すると二重起動になります。

## テスト・開発ツール

通常の`npm.cmd run dev`は`uv run --no-dev`を使い、試すだけならpytestやruffを追加取得しません。
テストする場合は開発用依存を追加します。

```powershell
uv sync --directory apps/server --dev
uv run --directory apps/server pytest
uv run --directory apps/server ruff check src tests
npm.cmd test
npm.cmd run typecheck
```

この手順はスクリプトとuvのオプションに照らして確認していますが、今回の変更でWindows実機による実行確認は行っていません。
