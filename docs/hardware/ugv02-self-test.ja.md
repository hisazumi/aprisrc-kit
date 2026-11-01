# UGV02 self-test

[English](ugv02-self-test.md)

この手順は、一人でSimulator確認済みのmissionを対応UGV02へ移して試すためのものである。
firmwareの書き込みとnetwork provisioningが済んだ1台を想定し、missionコードは変更しない。
先に[Challenger quickstart](../challenger-quickstart.ja.md)をSimulatorで完了する。

これはphoneが観測を送り、PC tabがmissionを実行する従来の二端末手順である。
車載phoneでcameraとmissionを実行する新しい[実機Playground](../demos/hardware-playground.ja.md)
とは別で、新UIの実機検証は未完了。準備がまだなら[引き継ぎガイド](../handoff.ja.md)から始める。

## Reference hardware

| Role | Assumed hardware |
| --- | --- |
| Rover | Waveshare UGV02、ESP32、wheel encoder、APRIS firmware `0.97-apris-ws-dev` |
| Vision/UI | ローバー前面へ固定したsmartphone。画面側を進行方向へ向け、front cameraを使う |
| Local Server | Node.js、Python、`uv`を導入したMacまたはPC |
| Network | PC、smartphone、UGV02が相互通信できるprivate LAN |
| Recovery | UGV02の物理電源スイッチ。firmware更新時だけdata通信可能なUSB cable |

通常走行ではUSB cableを接続しない。別のsmartphone、rover、認識装置を使う場合は
[Hardware assumptions and porting](service-hardware-porting.md)を先に確認する。

## One-time setup

1. [Local HTTPS and smartphone setup](../local-https.md)に従い、PCのLAN addressを含む
   開発証明書を作成し、自分のsmartphoneでCAを信頼する。
2. [UGV02 APRIS WebSocket firmware](ugv02-websocket-firmware.md)に従い、firmware、Wi-Fi、
   server address、rover ID、tokenを設定する。
3. repository rootのignored file `.env`へ、firmwareと一致する値を保存する。

```dotenv
APRIS_ADAPTER=websocket_rover
APRIS_ROVER_ID=ugv02-demo-1
APRIS_ROVER_TOKEN=<same development token as the rover>
```

`.env`、firmwareの`apris_rover_secrets.h`、CA秘密鍵はcommitまたは共有しない。

## Every self-test

最初は車輪を浮かせ、物理電源スイッチへ片手で届く状態にする。starterは最大15度の
旋回だけだが、周囲と配線が車輪へ触れないことを確認する。

1. UGV02とsmartphoneを固定し、cameraを塞いでいないことを確認する。
2. PC、smartphone、UGV02を同じLANへ接続する。
3. UGV02の電源を入れ、OLEDに`APRIS UGV02`と`0.97-apris-ws-dev`が出ることを確認する。
4. repository rootでAPRISをRover modeとして起動する。

依存関係はroot READMEに従い先に導入する。8000/5173の既存Simulator serverを終了する。
`.env`の編集だけでは稼働中serverは切り替わらず、このコマンドも自動読み込みしないため、
以下でexportする。`APRIS_DISABLE_HTTPS`は未設定にする。

```bash
set -a
source .env
set +a
npm run dev
```

5. PCで`uv run --directory apps/server apris-doctor --json`を実行し、次を確認する。
   - `status`が`ready`
   - adapterが`websocket_rover`
   - `ugv02-demo-1`がconnected
   - heartbeatとtelemetryがhealthy/fresh
   - linear/angular velocityが0、active motionがない
6. smartphoneで`https://<PC-LAN-IP>:5173/service?service=my-service`を開き、**Start vision**だけを押す。
   この試験はPCから汎用missionを動かすので、**Start service**は押さない。
7. camera枠が人物を認識し、接続表示がonlineであることを確認する。
8. PCで`https://localhost:5173/playground?service=greeting`を開き、**Advanced controls**を展開して手動操作欄の**Acquire control**を押す。共通サービスは開始しない。
9. **Service missions**から`Person greeting starter`を選ぶ。
10. 自分がcameraの外にいる状態で**Run selected mission**を押す。
11. 30秒以内にrover正面の少し左または右へ移動する。
12. roverが自分の方向へ最大15度だけ旋回し、停止して`Greeting complete`になることを
    確認する。

raised-wheel試験が成功した後だけ床へ置いて再試験する。starterは床上でも旋回のみである。

## Stop and finish

- 通常終了はPCの**Cancel mission**または**Release control**を使う。
- 予想外の動きでは**Emergency stop**を押す。画面操作ができなければ物理電源を切る。
- 試験後はlinear/angular velocityが0、active motionなしであることをdoctorまたは
  `/api/status`で確認する。
- smartphoneのcameraを停止し、`npm run dev`をCtrl-Cで終了してからUGV02の電源を切る。
- telemetryだけで判断せず、車輪の停止も目視する。
- 再接続だけで中断したmissionは再開されない。状態確認後に明示して再実行する。

## Forward motion is a separate step

`Person greeting starter`は前方障害認識がなくても試せる旋回だけを行う。正方向の`move()`
には、fresh/healthyな`CLEAR`を供給する認識経路または期限付きの監督許可が必要である。
`UNKNOWN`を走行可能として扱ったり、Simulator専用APIで実機の安全判定を迂回したりしては
いけない。後退と旋回が可能でも、前進が自動的に許可されるわけではない。

## Quick diagnosis

| Symptom | Check |
| --- | --- |
| phoneでcameraを開始できない | URLがHTTPSか、CA trust、camera permission、別appによるcamera使用 |
| APRISが`ready`にならない | `.env`のrover ID/token、OLEDのWi-Fi、server address、heartbeat |
| PCで**Acquire control**できない | phoneで**Start service**を押していないか、別tabがownerでないか |
| 人物枠は出るがmissionが反応しない | phoneとPCが同じAPRIS Serverへ接続しているか、30秒timeout前か |
| 旋回しない | E-stop、control owner、personの`bearingDeg`、3度未満のdeadband |
| 逆方向へ旋回する | phoneの向きとcamera facingを確認し、試験を止めて符号を記録する |
| forwardだけ拒否される | front obstacleが`UNKNOWN`または`BLOCKED`; 安全判定を迂回しない |

解決できない場合は、電源を切る前に可能なら`apris-doctor --json`と最新のstructured logの
時刻を記録する。tokenや秘密鍵は診断情報へ含めない。
