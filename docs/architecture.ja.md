# アーキテクチャと安全境界

[English](architecture.md)

APRISRC Kitはサービスの方針と認識・移動許可・motor制御を分けます。missionは操作権を持つ
browserで[Mission API](mission-api.ja.md)を使って実行します。phone/browserは認識を行い、
映像ではなく構造化観測を送信します。local serverは観測検証、操作権、速度/期限、logを担当し、
firmwareはmotorに近い制御とwatchdog停止を担当します。

browserは[Client protocol](protocol.md)、実機は`RoverAdapter`を介して別の
[Rover protocol](rover-protocol.ja.md)を使います。実機側からserverに接続します。
missionはGPIO/PWM/wheel指令を送らず、Simulator専用APIに依存しません。

- 移動の操作権は一つのclientだけが持ち、E-stopは操作権がなくても利用できます。
- 指令は失効し、切断・操作権喪失・cancel・E-stopで停止します。
- 再接続でmissionを自動再開しません。
- 前進にはfresh/healthyなCLEARが必要で、UNKNOWNは走行可能と扱いません。
- 監督許可は明示的・lease付き・期限付きで、障害物sensorではありません。
- 実機が示す移動上限をbrowser/serverから引き上げません。
- 観測検証後にevent/pose補正へ進み、odometryと表示用course補正を分けます。
- replayは仮想入力だけを送り、drive指令を再生しません。

Simulatorと実機adapterは同じ移動結果・安全確認の意味を保ちます。実機検証は環境固有なので
[Platform status](platform-status.ja.md)を参照します。内部の検討過程・実験logは初回公開に含みません。
