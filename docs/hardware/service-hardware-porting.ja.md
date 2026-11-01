# Service hardware assumptions and porting

[English](service-hardware-porting.md)

iron-X ROS 2 Humble向けの実験実装を追加した。
[操作と制約](ironx-quickstart.ja.md)、[Adapter契約](ironx-adapter.md)を参照。
UGV02のwire protocolではなく、KitとROS bridge間の同一ホストファイルを使う。
監視付きコンソール走行は確認済みだが、同じサービスの実行は別途検証する。mission APIは変更しない。

## Reference configuration

チャレンジャー向けmission APIの実機参照構成は次である。

```text
Phone camera / PWA
  person and marker observations
            |
            v
APRIS Server on student PC (Windows by default)
  ownership, validation, safety, logs
            |
            v
Waveshare UGV02 ESP32
  APRIS Rover protocol, encoder motion, motor watchdog
```

スマートフォン/browserは認識・利用者UI・操作権を持つtabでのmission実行を担当する。
PC serverは観測検証・移動許可・安全制御、UGV02はmotorに近い閉ループ制御と
通信断時停止を担当する。missionは`ServiceRover`だけを利用し、どの
機種が接続されているかを判定しない。

案内上の構成はUGV02一台、固定したスマホ、Windows PC、private LANである。
macOS/Linuxも代替ホストとして使う。過去のMacでの試験はWindowsでの検証を意味しない。
設定とセルフテストの入口は[引き継ぎガイド](../handoff.ja.md)を参照する。
挨拶・追従には印刷マーカーは不要。実機Playgroundは車載スマホ自身のcameraを使うが、
実機検証は未完了で、実機marker案内は有効にしていない。

## What can be replaced without platform code

| Replacement | Conditions |
| --- | --- |
| Smartphone model | HTTPS、`getUserMedia`、WebAssembly、十分なcamera性能をbrowserが提供する |
| 学生PC（標準はWindows） | Node.js、Python、`uv`、LANからのHTTPS/WSS到達性を用意する。macOS/Linuxの差分は起動ガイドの補足を参照 |
| Wi-Fi router | phone、PC、rover間のclient isolationがなく、ESP32が接続できるLANを提供する |
| Phone mount | cameraの正面、水平、画角を維持し、wheelや電源操作を妨げない |

端末交換後は、camera permission、人物認識範囲、左右のbearing符号、WebSocket再接続を
再確認する。画角が変わるため、人物のframe widthを距離として使うthresholdは再調整が
必要になる場合がある。

## Using another rover

別の車輪型ローバーを使う場合、missionを書き換えるのではなくAPRISの`RoverAdapter`
境界へ接続する。adapterまたはdevice firmwareは最低限、次を提供する。

- 接続状態と能力の報告
- SI単位のpose、linear/angular velocity、telemetry
- 期限付きmanual velocityと明示stop
- 距離指定のbounded linear motion
- 角度指定のbounded rotation
- accepted/running/completed/cancelled/failedを区別する結果
- firmwareまたはmotor controller側の固定速度上限
- command lease/watchdog、通信断時stop、latched E-stop
- reconnect後に中断motionを自動再開しない規則

device-initiated接続を実装できる場合は
[APRIS Rover WebSocket protocol](../rover-protocol.md)へ合わせる。ROS 2 robotでは、
Jetsonなどのedge processで`cmd_vel`、odometry、IMUと`RoverAdapter`を変換してもよい。
どちらの場合もbrowserやmissionをmotor protocolへ直接接続しない。

新しいadapterには、Simulatorと同じmove/turn/stopの意味、TTL、cancel、disconnect、
E-stop試験を適用する。少なくとも車輪を浮かせた試験、最低速度の床上試験、停止時間、
距離・角度符号を確認してからservice missionを実行する。

## Using stock UGV02 firmware

純正v0.96の`factory_http` adapterは通信診断とdead-man manual controlに限定される。
自動`move()` / `turn()`は拒否されるため、チャレンジャーmissionの実機実行には使用できない。
missionを動かすにはAPRIS WebSocket firmwareを導入するか、自動motionと停止保証を満たす
別adapterを実装する。

## Replacing perception hardware

スマートフォン以外のcamera、depth sensor、PC vision processを使う場合も、missionへ
sensor SDKを直接持ち込まない。認識clientはClient protocolへ登録し、personまたはmarkerの
構造化観測をAPRIS Serverへ送る。

Person observationには少なくとも次が必要である。

- stableなperson ID
- `detected | lost`
- confidenceと取得時刻
- 正規化した中心、幅、高さ
- rover正面を0度とするbearing
- observation source

serverの鮮度、confidence、payload検証を通った観測だけが`onPerson()`へ届く。前方障害を
扱うsensorは人物観測とは別に、`CLEAR | BLOCKED | UNKNOWN`、perception health、heartbeatを
供給しなければならない。単に「障害物を検出しなかった」ことを`CLEAR`へ変換しない。

## Porting checklist

1. 交換するcomponentと、維持する責務境界を決める。
2. Simulatorで変更前missionの期待結果を固定する。
3. adapterまたはperception clientのcontract testを追加する。
4. motorなし、raised-wheel、低速floorの順に検証する。
5. TTL、process loss、network loss、E-stopでzero outputを確認する。
6. 同じmissionを変更せずSimulatorと実機で実行する。
7. capability差、校正値、復旧方法、未検証項目をhardware documentへ記録する。

新しい機体のために`ServiceRover`へ機種固有命令を追加する必要が生じた場合は、まず
高水準の共通動作として表現できないか検討する。機種名、GPIO、PWM、wheel commandが
missionへ現れる設計はporting完了とはみなさない。
