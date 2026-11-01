# 学生PCからiron-Xへ接続する（実験的）

[English](ironx-network.md)

毎回のWindows側の起動は[iron-X・UGV02の起動方法](startup.ja.md)から始めてください。

学生PCは**Windows・PowerShell**を標準とし、macOS/Linuxは折りたたみ補足を参照します。
ロボット上の準備コマンドはiron-XのLinuxで実行します。学生PCにROSやWSLは不要です。

PC・iPhoneでの開始・停止・復旧は[人追従ガイド](ironx-follow.ja.md)を参照する。
このページはネットワーク構築の参考資料である。

Kitサーバーとサービスは学生のPCで動かし、通常はSimulatorを使う。
承認された実機利用の順番になったら、そのサーバーを`ironx_network`へ切り替える。
学生PCにROSは不要。ROS、ドライバー、ローカルbridgeはロボット側に残す。
このネットワーク経路は実験的であり、限定的な監視付き試験の結果を末尾に記録する。
Windows対応は設計上の意図であり、Windowsからの実機操作は未検証。
過去の[ローカルAdapter試験](ironx-adapter.md)は、この経路の実機検証を意味しない。

```text
PCブラウザー / ローバー搭載スマートフォン -> 学生PCのKitサーバー
  -> ironx_network -> ロボット上の認証付きWebSocket gateway :8766
  -> ローカルcommand mailbox -> 既存ROS command/watchdog bridge -> driver
  <- gateway <- 既存のローカルtelemetry・command-statusファイル
```

## 学生PC：接続先を選ぶ

まず[参加者向けセットアップ](../challenger-quickstart.ja.md)を済ませる。
リポジトリのルートから、通常のPC単体での開発は次のように起動する。

```powershell
$env:APRIS_ADAPTER = "simulator"
$env:APRIS_DISABLE_HTTPS = "1"
npm.cmd run dev
```

<details>
<summary>macOS / Linuxの場合（学生PC）</summary>

```sh
export APRIS_ADAPTER=simulator
export APRIS_DISABLE_HTTPS=1
npm run dev
```

</details>

切り替える前に動作を止め、ロボットの静止を確認してから、起動中のKitサーバー・
開発プロセスを終了する。再起動する端末で環境変数を設定する。
変数の変更だけでは、起動済みサーバーの接続先は変わらない。
運用担当者がgatewayを準備し、自分の利用順になってからネットワーク構成で起動する。

```powershell
$env:APRIS_ADAPTER = "ironx_network"
$env:APRIS_IRONX_URL = "ws://robot:8766"
$env:APRIS_IRONX_TOKEN = "secret"
Remove-Item Env:APRIS_DISABLE_HTTPS -ErrorAction SilentlyContinue
npm.cmd run dev
```

<details>
<summary>macOS / Linuxの場合（学生PC）</summary>

```sh
export APRIS_ADAPTER=ironx_network
export APRIS_IRONX_URL=ws://robot:8766
export APRIS_IRONX_TOKEN=secret
unset APRIS_DISABLE_HTTPS
npm run dev
```

</details>

`robot`は運用担当者が指定するロボットのホスト名・アドレスに置き換える。
`secret`は例にすぎない。担当者から受け取った非公開tokenを使い、リポジトリや
ブラウザーコードに保存しない。学生PC側の`/api/status`で`ironx_network`、
新鮮な接続済みtelemetry、速度ゼロを確認する。既存の操作権、認識情報の鮮度、
障害物チェックを維持する。接続成功は移動許可ではない。
Simulatorへ戻す場合も、サーバーを停止して`APRIS_ADAPTER=simulator`で再起動する。

## ロボット側：運用担当者の準備

gatewayは[同一ホスト用Adapter](ironx-adapter.md)と既存のcommand・telemetry
bridgeを再利用し、command mailboxを排他的にロックする。
ロボットを停止して停止確認を終えてから、**旧ロボット上Kitサーバー
（`APRIS_ADAPTER=ironx`）を終了し、その後でgatewayを起動する**。
ROS、隔離されたdriver、telemetry bridge、command/watchdog bridgeは動かしておく。
bridgeの重複起動、直接のcommand送信、motion probeの併用は禁止。
ロック失敗を回避するためにロックを削除したり、別のcommandファイルを選んだりしない。

ロボット上の既存の非公開runtimeディレクトリを使い、稼働中bridgeと一致する
相互に異なる3つの絶対パスを指定する。ロボットのKit用Python環境で、
`ROOT`をチェックアウト先に設定した起動例：

```sh
cd "$ROOT"
export APRIS_IRONX_GATEWAY_TOKEN=secret
export APRIS_ROS2_STATE_FILE="$ROOT/.runtime/ironx/state.json"
export APRIS_IRONX_COMMAND_FILE="$ROOT/.runtime/ironx/command.json"
export APRIS_IRONX_BRIDGE_STATE_FILE="$ROOT/.runtime/ironx/command-status.json"
python -m apris_server.ironx_gateway --host 0.0.0.0 --port 8766
```

gatewayのtokenはPC側の`APRIS_IRONX_TOKEN`と一致させる。
パスのCLI引数は`--state-file`、`--command-file`、`--bridge-state-file`で、
環境変数の既定値より優先される。既定の待受は`127.0.0.1`であり、上の例は明示的に
LANからの接続を許可する。接続元は承認済みPCに制限する。
起動時は停止確認を完了してから利用可能になる。ここでは準備手順を示すだけで、
これらのコマンドを実行したわけではない。

## 操作権・停止・復旧

- gatewayだけがローカルmailboxを所有し、ネットワーク側の操作権も同時に1接続だけに
  与える。各Kitサーバー内のブラウザー操作権とは別の層である。
- PC側Adapterは最初の移動要求でgatewayのleaseを自動取得し、停止時に解放する。
  bounded move/turnの完了時も解放するため、学生のセッション全体やmission全体を
  予約する仕組みではない。利用順は別途合意し、指定された学生のネットワーク用
  サーバーだけを有効にし、他の学生はSimulatorを使う。交代時は前のサービスを止め、
  telemetryで静止を確認してネットワーク用サーバーを終了する。他の学生のmissionの
  動作間に操作権を取り合わない。
- 各driveには接続・操作権の世代に紐づいた、新鮮で1回限りのchallengeが必要。
  有効期間は300 msで、通信時間も消費する。clientのcommand TTL上限は200 msで、
  gatewayはchallengeの残り時間でも制限する。成功したdriveだけが300 msの操作権
  leaseを更新し、telemetryの読み出しでは更新しない。command期限切れ、操作権の
  期限切れ、所有接続の切断はローカルwatchdog・Adapter経由の停止を起こす。
- 停止確認の失敗はgatewayにラッチされ、担当者による復旧とgateway再起動が必要。
  timeoutやゼロcommandは実際の停止の証明ではない。独立した物理停止・電源操作を
  常に可能にしておく。bridge・OS・serialの故障は上流command watchdogでは覆えない。
- clientは障害後に状態観測のため再接続するが、指令の再送や操作権の再取得はしない。
  操作権の保持中・動作実行中の切断は、実際の停止確認後に明示的な停止解除が必要。
  非常停止は再接続でも保持し、解除要求に失敗した場合も解除しない。
  gatewayの停止確認失敗は引き続き担当者による復旧が必要。
  Wi-Fi復旧を前のmissionの動作再開の許可とみなさない。

## ネットワークの安全性とiPhoneカメラ

Bearer認証は暗号化ではない。`ws://`ではtokenと通信内容が平文で流れるため、
信頼できる隔離LANだけで使う。信頼できないネットワークでは、正しく設定した
TLS reverse proxyと`wss://`、信頼された有効な証明書を使い、Authorization headerを
転送し、gatewayへの直接接続を制限する。8766番ポートをインターネットへ公開しない。
スマートフォン側のHTTPSは、別経路のPC・gateway間通信を暗号化しない。

カメラ観測にはiPhoneをローバーに搭載し、**旧ロボット上Kitではなく、学生PCの
Kitサーバー**へ接続する。開発構成のURLは
`https://<student-PC-LAN-IP>:5173/service`。
[ローカルHTTPSとスマートフォン設定](../local-https.ja.md)に従い、証明書に学生PCの
アドレスを含め、そのCAをiPhoneで信頼する。`APRIS_DISABLE_HTTPS`は未設定にし、
カメラを許可して、証明書警告を解消してから試す。スマートフォン・PC・gatewayが
必要な経路で通信できることを確認する。観測はサービスを動かすPCへ送られる。

5173は通常のHTTPSポートで、固定要件ではない。実際の起動URLを使う（別起動なら5174など）。
iron-Xの現在の上限は0.15 m/s、0.2 rad/s。停止確認は重複する動作キャンセルから保護し、
既存のRPC期限3秒は維持する。期限切れでは安全側に停止する。最新修正と速度設定は実機再試験待ち。
以下の0.04 m/s試験は過去の根拠であり、現在の設定の評価完了ではない。

## 監視付き試験記録（2026-10-31）

iron-Xへgatewayを配備し、Mac上のKitからWi-Fi経由で操作した。
リモコン操作は成功したが、送信間隔200msとネットワーク指令の最大有効期限200msが
競合し、調査した操作区間で20〜41msのゼロ指令が83回挟まっていた。
送信間隔を50msへ変更し、停止期限は延長していない。

0.04m/sで2秒前進する監視付き試験を2回実施した。各40指令、指令エラーなし、
実機側ブリッジのログで走行途中のゼロ出力なし。オドメトリによる移動量は
約7.6cmと7.9cmで、停止後の速度はほぼゼロだった。最後の試験は操作者からも
良好との報告があった。距離は外部計測ではなくオドメトリの推定値である。
試験スクリプトはジョイスティックと同じKit WebSocketのdrive経路と50ms間隔を使った。

それ以前の試験はスクリプトが前方確認を更新し忘れ、約0.84秒で停止した。
これは2秒試験の成功には含めない。修正版は時間を限定した試験中だけ確認を更新した。

待機中の接続不可を調べ、ロック待ちも250msのRPC期限に含めていたことと、
状態取得の呼び出し側のキャンセルが共有接続を閉じる問題を修正した。
状態取得は重複をまとめ、呼び出し側のキャンセルから保護する。
状態RPCは1秒まで待つが、観測の鮮度上限300msと走行指令の有効期限は変えない。
切断ログに処理名と例外種別を残す。模擬接続での再現テストで確認した変更であり、
Wi-Fi自体の切断がないことを証明するものではない。

残課題：gatewayへ届かなかったPCだけの非常停止はプロセス再起動で失われる。
再起動を実機の非常停止解除として使わない。Windows、複数学生の実機引き継ぎ、
このネットワーク経路での物理的な通信断停止試験は未検証である。
次の試験前に[監視付き操作](ironx-quickstart.ja.md)と
[command bridgeの制限](ironx-command-bridge.md)を確認する。
