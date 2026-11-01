# iron-X・UGV02の起動方法

[English](startup.md)

機体の初期設定が済んだ後、**Windows PC・PowerShellから毎回起動する手順**です。
先に[Windowsの準備](../windows-setup.ja.md)とSimulatorでの試行を済ませてください。
PCのコマンドはリポジトリ直下で実行します。この手順ではファームの書き換えや走行指令は行いません。
共通実機UIとWindowsからの実機操作は、監視付きの実機検証が必要です。

## 起動前

1. 実行中のサービスを止め、車輪の停止を確認してから、既存のKit開発サーバーをCtrl+Cで終了します。
   環境変数だけを変えても、起動済みサーバーは切り替わりません。
2. この機体を使う操作者とPCを1組に決めます。他の学生はSimulatorを使います。
3. 信頼できるLANを使い、アドレス・tokenは機体の担当者から非公開で受け取ります。
4. 車載スマホのカメラを使う場合は[HTTPS設定](../local-https.ja.md)を先に済ませます。
   PCの現在のLANアドレスを証明書へ含め、スマホ側でCAを信頼します。
   Windows PCとiPhoneを組み合わせられます。Safariはスマホ側です。
5. 物理停止・電源を操作できるようにします。起動・接続成功は走行許可ではありません。
   動かす直前には別途、操作者の承認を得てください。

| | iron-X | APRIS WebSocketファームのUGV02 |
| --- | --- | --- |
| PC側Adapter | `ironx_network` | `websocket_rover` |
| 接続方向 | PCから機体のgatewayへ。通常8766番 | 機体からPCの8000番、`/ws/rover`へ |
| 必要な値 | gateway URLと非公開gateway token | ファームと一致するrover ID・token |
| 機体側の準備 | ROS、telemetry bridge、command/watchdog bridge、gateway | APRISファーム、Wi-Fi、PCサーバーのアドレス、ID・token |

## iron-X

### 機体側の前提

担当者に設定済みの機体側プログラムを起動してもらい、準備完了を確認します。
電源を入れただけで、次が動いているとは限りません。

1. ROSと分離したdriver。Node-RED等から競合する走行指令を送らない状態にする。
2. 同じ非公開runtimeパスを使うtelemetry bridgeとcommand/watchdog bridge。
   command bridgeの有効化は操作者の承認後に行う。
3. 合意したLANアドレス・ポートで待ち受ける認証付きgateway。
   旧機体内サーバーの`APRIS_ADAPTER=ironx`が同じcommand mailboxを所有していてはいけない。

機体準備のLinuxコマンドは**iron-X上**で実行し、Windowsでは実行しません。
[ROS・telemetry設定](ironx-readonly.md)、[command bridge](ironx-command-bridge.md)、
[gatewayの起動](ironx-network.ja.md)を参照してください。
既に動いているROS・SSHは維持し、重複起動しません。学生PCにROSやWSLは不要です。

### Windows PCで起動する

担当者から受け取ったgateway URLを入力します。形式は`ws://<機体アドレス>:8766`などです。
アドレスは実値に置き換え、URLへtokenを含めないでください。

```powershell
$env:APRIS_ADAPTER = "ironx_network"
$env:APRIS_IRONX_URL = Read-Host "Robot gateway URL"
$env:APRIS_IRONX_TOKEN = Read-Host "Private gateway token"
$env:APRIS_SERVER_URL = "http://127.0.0.1:8000"
Remove-Item Env:APRIS_DISABLE_HTTPS -ErrorAction SilentlyContinue
npm.cmd run dev
```

`ws://`は暗号化されないため、信頼できる試験用LANだけで使います。
tokenはgatewayの`APRIS_IRONX_GATEWAY_TOKEN`と一致させ、入力画面を共有・録画しないでください。
`ironx`は機体内でKitサーバーを動かす場合のAdapterです。Windowsでは選びません。

連続追従は明示的に選ぶ試験用設定で、上のコマンドだけでは有効にしません。
合意した連続追従試験の場合だけ、Vite起動**前**に
`$env:VITE_IRONX_CONTINUOUS_FOLLOW="1"`を設定します。
[連続追従ガイド](continuous-follow-trial.ja.md)を参照し、接続確認だけなら既存の追従設定は変えません。

## UGV02

### 機体側の前提

初期設定済みの**APRIS WebSocketファーム**を使います。工場出荷時0.96のHTTP操作とは別です。
Wi-Fi、`APRIS_SERVER_HOST`としての**PCのLANアドレス**、8000番ポート、サーバーと一致する
rover ID・tokenが必要です。OLEDに表示される機体自身のIPは、サーバーのアドレスではありません。
PCやネットワークが変わった場合は、担当者が[ファーム設定ガイド](ugv02-websocket-firmware.md)に従って
接続先を変更します。この起動手順では書き換えません。

### Windows PCで起動する

設定済みのrover IDとtokenを入力します。すべての機体が例のIDを使うとは限りません。

```powershell
$env:APRIS_ADAPTER = "websocket_rover"
$env:APRIS_ROVER_ID = Read-Host "Configured rover ID"
$env:APRIS_ROVER_TOKEN = Read-Host "Private rover token"
$env:APRIS_SERVER_URL = "http://127.0.0.1:8000"
Remove-Item Env:APRIS_DISABLE_HTTPS -ErrorAction SilentlyContinue
npm.cmd run dev
```

続いて設定済み機体の電源を入れます。既にオンならファームの再接続を待ちます。
画面で想定したAPRISファームとWi-Fi状態を確認してください。
機体から接続するため、上のPC環境変数に機体のIPは不要です。
PCの8000番への着信は信頼できる試験用LANだけに許可し、Windowsファイアウォール全体は無効化しません。
USBは初期設定用で、通常のWi-Fi操作には不要です。床上試験前には取り外します。

## 動かさずに接続確認

起動したターミナルは開いたままにします。別のPowerShellをリポジトリ直下で開きます。

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/status | ConvertTo-Json -Depth 10
```

Adapterが`ironx_network`または`websocket_rover`であること、接続、新鮮なtelemetry、
動作中でないこと、報告速度ゼロを確認します。車輪も目視で停止を確認してください。
telemetryだけでは実停止の証明になりません。確認を通すためだけにfaultを解除しないでください。

- PC：Viteが表示したURLの`/console?service=carry`を開きます。
  まず監視だけを行い、まだ操作権取得やジョイスティック操作はしません。
- 車載スマホ：`https://<PCのLANアドレス>:<HTTPSポート>/service?service=carry`を開きます。
  通常は5173番です。**どちらの機体でもPCのアドレス**を使い、iron-Xのgateway URLやUGV02のOLED IPとは区別します。
- **Start vision**だけを押してカメラ観測を確認します。接続確認では**Start service**を押しません。
  証明書警告は先に解消します。

承認後の動作試験は[iron-X人追従](ironx-follow.ja.md)、[UGV02自己試験](ugv02-self-test.ja.md)、
または[共通実機操作](../demos/hardware-playground.ja.md)に進みます。
共通サービスは現在**Acquire control → Confirm clear path · 30 s → Start service**です。
開始しても30秒許可は更新しません。実機マーカー案内は無効です。

## 終了・Simulatorへ戻す

サービスを中断し、実停止を確認して操作権を解放、カメラを止め、PCサーバーをCtrl+Cで終了します。
iron-Xの機体側プロセス停止は担当者と相談し、共有中の機体を勝手に終了しません。
UGV02は停止後に電源を切ります。再接続だけで以前の試験を再開してはいけません。

Simulatorへ戻す場合はPowerShellで設定して起動します。

```powershell
$env:APRIS_ADAPTER = "simulator"
$env:APRIS_DISABLE_HTTPS = "1"
$env:APRIS_SERVER_URL = "http://127.0.0.1:8000"
npm.cmd run dev
```

`http://localhost:5173/playground?service=my-service`を開きます。別ポートなら起動表示を使います。
環境変数はそのターミナルに設定され、このコマンドでは`.env`を自動読み込みしません。
tokenや非公開設定はコミットしないでください。

<details>
<summary>macOS / Linuxの場合（学生PC）</summary>

前提・接続確認は同じです。シェルの設定は次に置き換えます。

```bash
# iron-X: replace values with the operator-provided private settings
export APRIS_ADAPTER=ironx_network
export APRIS_IRONX_URL='ws://<robot-address>:8766'
export APRIS_IRONX_TOKEN='<private-gateway-token>'

# OR UGV02: use these instead of the three iron-X settings above
# export APRIS_ADAPTER=websocket_rover
# export APRIS_ROVER_ID='<configured-rover-id>'
# export APRIS_ROVER_TOKEN='<private-rover-token>'

export APRIS_SERVER_URL=http://127.0.0.1:8000
unset APRIS_DISABLE_HTTPS
npm run dev
```

tokenは非公開で指定し、ターミナル履歴や録画を共有しないでください。
別ターミナルの`curl http://127.0.0.1:8000/api/status`で接続を確認します。
終了後、`APRIS_ADAPTER=simulator APRIS_DISABLE_HTTPS=1 npm run dev`でSimulatorへ戻せます。

</details>

## 接続できない場合

| 症状 | 確認 |
| --- | --- |
| AdapterがSimulatorのまま | 以前のサーバーを止め、再起動に使うターミナルへ変数を設定したか |
| iron-Xにつながらない | 機体のgatewayプロセス、URL・ポート、token、LAN経路、競合する所有者。[ネットワーク設定](ironx-network.ja.md)を参照 |
| UGV02が現れない | ファームのPCアドレス・ポート、ID・token、Wi-Fi、PCのファイアウォール。PC環境変数だけではファームの接続先を変更できない |
| スマホで開けない | PCアドレス、実際のHTTPSポート、証明書信頼、ファイアウォール、Wi-Fiの端末間通信制限 |
| サービスが途中で止まる | 許可期限、観測鮮度、表示されたfault。通信断と決めつけたり、安全判定を無効化しない |

この文書変更の検証でロボットは動かしていません。
Windowsからの実機実行と現行共通UIは、監視付きの実機検証が必要です。
