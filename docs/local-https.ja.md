# HTTPSとスマホ接続

[English](local-https.md)

Kitを動かす**Windows PC・PowerShell**を標準に説明します。macOS/Linuxは折りたたみ補足を参照。
スマホが必要なのはカメラ試験時で、PCだけのSimulatorはHTTPで動き、証明書は不要です。
iPhoneのSafariはスマホ側のブラウザで、PCにMacを用意する意味ではありません。

スマホからViteへHTTPS/WSSで接続し、ViteからFastAPIの8000番へHTTPで中継します。
機体・gatewayとの別のWebSocket通信まで暗号化するものではありません。

## 1. Windowsで証明書を生成する

リポジトリ直下で実行します。証明書生成には通常のシミュレータ用ツールに加えてOpenSSLが必要です。
スクリプトは環境変数`OPENSSL`があればその実行ファイルを使い、なければ`openssl`を探します。

```powershell
openssl version
```

見つからなければ、所属組織で承認されたOpenSSLを用意してください。
Git for Windowsに同梱されている場合は、その実際のパスを指定できます。例えば：

```powershell
$env:OPENSSL = "C:\Program Files\Git\usr\bin\openssl.exe"
Test-Path $env:OPENSSL
& $env:OPENSSL version
```

実行ファイルが存在し、バージョン確認が成功してから進みます。
これはパスの例で、すべてのGit環境に存在する保証ではありません。

```powershell
npm.cmd run cert:generate
```

Git管理対象外の`.certs/`に、公開CAの`apris-local-ca.pem`、CA秘密鍵
`apris-local-ca-key.pem`、`localhost.pem`と`localhost-key.pem`を生成します。
localhostと現在のLANアドレスを含めますが、信頼設定は自動で行いません。
追加アドレスは`npm.cmd run cert:generate -- <PC-LAN-IP>`で指定します。
プレースホルダーは実値に置き換え、アドレス変更時は再生成してください。

## 2. Windowsで自分のCAを信頼する

このプロジェクトで自分が生成したCAだけを信頼してください。
警告回避のために出所不明の証明書を取り込まないでください。
PowerShellで公開CAをDER形式に変換し、現在のWindowsユーザー用に登録します。

```powershell
if (-not $env:OPENSSL) { $env:OPENSSL = "openssl" }
& $env:OPENSSL x509 -in .certs/apris-local-ca.pem -outform DER -out .certs/apris-local-ca.cer
Import-Certificate -FilePath .certs/apris-local-ca.cer -CertStoreLocation Cert:\CurrentUser\Root
```

変換成功を確認してから登録してください。
[MicrosoftのImport-Certificate説明](https://learn.microsoft.com/en-us/powershell/module/pki/import-certificate)も参照。
組織のポリシーで禁止されている場合は管理者へ相談し、ポリシーを緩めないでください。
最終的なURLをEdgeまたはChromeで開き、証明書警告が出ないことを確認します。
終了後はこのプロジェクトのCAの信頼を削除します。秘密鍵は共有・コミットしません。

<details>
<summary>macOS / Linux：証明書生成とPC側の信頼設定</summary>

OpenSSLを用意し（`OPENSSL`で実行パス指定も可能）、`npm run cert:generate`を使います。
macOSはキーチェーンアクセスへ公開CAの`.certs/apris-local-ca.pem`だけを登録し、
自分の開発用CAを明示的に信頼します。Linuxはディストリビューションとブラウザの証明書設定に従い、
必要なら管理者へ相談してください。ブラウザの証明書ストアも異なるため、警告なしで開けることを確認します。

下の起動操作は`unset APRIS_DISABLE_HTTPS`と`npm run dev`に置き換えます。
PCだけのHTTP Simulatorは`APRIS_ADAPTER=simulator APRIS_DISABLE_HTTPS=1 npm run dev`です。

</details>

## 3. スマホで公開CAを信頼する

`apris-local-ca.pem`または公開CAの`.cer`だけを非公開の経路で渡します。
`*-key.pem`は渡しません。PC側の信頼設定はスマホへ自動反映されません。

- **iPhone/iPad：** 設定でダウンロード済みプロファイルをインストールし、
  「設定 → 一般 → 情報 → 証明書信頼設定」でこのCAを有効にします。スマホ側はSafariを使います。
- **Android：** 端末の証明書設定で公開CAを登録します。端末・ブラウザで挙動が違うため、
  その端末で最終URLとカメラ権限を確認してください。

証明書警告を無視して進めず、信頼・期限・アドレスの不一致を解消します。

## 4. PCで起動し、スマホから接続する

設定変更前に既存の開発サーバーを停止します。Adapterは実機ガイドで指定した設定を使います。
以下のコマンドは機体を選択せず、走行も許可しません。

```powershell
Remove-Item Env:APRIS_DISABLE_HTTPS -ErrorAction SilentlyContinue
npm.cmd run dev
```

Viteの証明書ファイルが両方必要です。起動表示のHTTPSポート（通常5173）を確認し、
スマホで`https://<PC-LAN-IP>:<HTTPS-port>/service?service=carry`を開きます。
証明書に含むPCのアドレスを使い、スマホのlocalhostやロボットのアドレスとは区別します。
PC・スマホ間でLAN通信できる必要があります。Windowsファイアウォールは無効化せず、
信頼できる試験ネットワークと必要なポートに限定して許可します。
ゲストWi-Fi等の端末間通信制限は証明書では解決できません。

PCだけのSimulatorは[Windowsの起動手順](windows-setup.ja.md)を使ってください。
再生成後はViteを再起動し、CA自体を変えた場合はPC・スマホ双方の信頼設定も更新します。
カメラ準備だけでは走行しません。実機ガイドの許可手順に従ってください。

## 確認範囲

送信するのは構造化観測で、映像ではありません。開発用HTTPSの手順で、本番運用向けではありません。
Windowsを標準の案内にしていますが、今回の変更でWindows実機での実行確認は行っていません。
