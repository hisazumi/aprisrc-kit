# Windowsの起動・トラブル対応

[English](windows-setup.md)

## 初回起動（PowerShell）

参加者向けの標準環境はWindowsです。PCはEdgeまたはChromeを使い、WSLやSafariは不要です。
macOS/Linuxの場合は[参加者quickstart](challenger-quickstart.ja.md)の折りたたみ補足を開いてください。

Git、Node.js 22.12以降または24以降（npmを含む）、[uv](https://docs.astral.sh/uv/getting-started/installation/)を用意します。

### Node.jsとnpmをインストールする

新しく準備する場合は、**Node.js 24系の公式Windowsインストーラー**を使います。
npmも一緒に入るので、別途インストールする必要はありません。
[npm公式の導入案内](https://docs.npmjs.com/downloading-and-installing-node-js-and-npm/)も参照できます。

1. [Node.jsのダウンロードページ](https://nodejs.org/en/download)で、バージョン**24系**、
   **Windows**、PCのアーキテクチャに合う**Windows Installer（.msi）**を選びます。
2. インストーラーを実行し、npmとPATHへの追加を有効にしたまま進めます。
   管理されたPCで管理者の承認が必要なら、制限を回避せず管理者へ相談してください。
3. PowerShellを閉じて開き直します。VS Code内のターミナルを使う場合はVS Codeも再起動します。
4. 次の両方を確認します。

```powershell
node --version
npm.cmd --version
```

最初が`v24.x.x`、次がnpmのバージョン番号になれば導入確認は完了です。
既に対応するNode.jsで両方動くなら、再インストールは不要です。
コマンドが見つからない場合は、まずターミナルを開き直し、インストールの完了とPATH設定を確認します。
PowerShellの実行ポリシーは変更しません。このガイドでは`npm.ps1`の制限を避けるため`npm.cmd`を使います。

### uvをインストールする

uvは、このプロジェクトで使うPythonと依存パッケージを準備するツールです。
以下の方法でuvを入れる前に、Pythonを別途インストールする必要はありません。
PowerShellで、[uv公式の導入案内](https://docs.astral.sh/uv/getting-started/installation/#winget)
にあるWinGetコマンドを実行します。

```powershell
winget install --id=astral-sh.uv -e
```

完了後、PowerShellを閉じて開き直します。VS Code内のターミナルならVS Codeも再起動し、確認します。

```powershell
uv --version
```

バージョン番号が表示されれば準備完了です。既に動く場合はインストール不要です。
`winget`が見つからない場合は、公式案内の別の導入方法を参照するかPC管理者へ相談してください。
組織のインストール制限を回避しないでください。
開き直しても`uv`が見つからない場合は、インストールの完了と実行ファイルのPATH登録を確認します。

続く`uv python install 3.12`でPythonを導入し、`uv sync`でこのプロジェクトの依存パッケージを準備します。

### シミュレータを起動する

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

## トラブル対応

| 症状 | 確認・対応 |
| --- | --- |
| `npm.ps1`がブロックされる | `npm.cmd`を使います。実行ポリシーを緩める必要はありません。 |
| `[vite] ws proxy error ... ECONNREFUSED` | 最初の`[server]`エラーと8000番の`/api/status`を確認します。Pythonの準備に失敗してフロントだけ起動している場合があります。 |
| `watchfiles`・`maturin`・Rustのビルド失敗 | 下の「Python依存パッケージのビルドに失敗する」で、使用中のPythonと最初のエラーを確認します。 |
| パッケージ取得のタイムアウト | `$env:UV_HTTP_TIMEOUT="300"`を設定して`uv sync --directory apps/server --no-dev`を再実行します。最初からキャッシュを消すと再取得が増えるため避けます。 |
| `127.0.0.1`ではバックエンドに接続できるがViteから失敗する | `$env:APRIS_SERVER_URL="http://127.0.0.1:8000"`を設定しViteを再起動します。以前の接続先指定が残っていないか確認します。 |
| 8000番が使用中 | 前のAPRISサーバーを停止します。無関係なプロセスは停止しません。 |

バックエンドだけ調べる場合は`npm.cmd run dev:server`で起動し、`Application startup complete`と
`/api/status`を確認します。**Ctrl+Cで停止してから`npm.cmd run dev`へ進んでください。**
後者もバックエンドを起動するため、同時に実行すると二重起動になります。

### Python依存パッケージのビルドに失敗する

**症状：** 起動時に`watchfiles`・`maturin`・Rust関連のビルドエラーが出て、
`[server]`が起動しません。画面だけ開き、Viteに`ECONNREFUSED`が出る場合もあります。

**確認：** 以前に別のPython（例：3.15）で作った仮想環境が残っていると、
対応するビルド済み依存パッケージを使えないことがあります。
リポジトリのルートで、既存環境のバージョンを確認します。

```powershell
apps/server/.venv/Scripts/python.exe --version
```

`.venv`がない場合は初回起動手順へ戻ってください。
3.12以外だった場合は、以下でプロジェクトの仮想環境だけを作り直します。
システム全体のPythonを変更する必要はありません。正常に起動している場合、この作業は不要です。

**対処：** APRISの開発サーバーをすべて停止してから、リポジトリのルートで実行します。

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

3.12でもビルドに失敗する場合は、Pythonのバージョンだけが原因とは限りません。
最初の`[server]`エラー全文とパッケージ配布元・ミラー・インストール設定を確認してください。
Rustの導入や同じ環境の作り直しを繰り返す前に、失敗している依存を特定します。

## 実機を起動する

設定済みの実機へ切り替える場合は[iron-X・UGV02の起動方法](hardware/startup.ja.md)を参照してください。
機体側の準備、PowerShell設定、スマホのURL、動かさない接続確認を分けています。
シミュレータ用の設定のまま実機試験へ進まないでください。

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
