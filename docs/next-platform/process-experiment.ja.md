# サービスとfake安全ゲートウェイのプロセス分離実験

[English](process-experiment.md) · [最初の試作](runner-prototype.ja.md)

状態：第2段階の独立した試作、2026-11-05。
既存の[myService](../../apps/pwa/src/missions/myService.ts)を変更せず、別のNode.js
プロセスで実行する。StudentServiceApiの実装をfakeへ差し替え、mission/configの配置と
既存PWAは変更していない。第1段階のmailbox/epoch実験とはまだ独立しており、
本番用の統一runtimeにはなっていない。

## 実行

Node.js 22.18以降を使用する。最初のローカル検証は26.13.0。リポジトリのルートから実行する。

```sh
node apps/runner-prototype/demo.ts
node --test apps/runner-prototype/*.test.ts
```

demoはゲートウェイとrunnerの異なるPID、移動結果、質問と合成回答、サービスの終了結果を表示する。
Yes → Items are loaded → We have arrivedを自動回答する。実際の人の離脱を確認した証拠ではない。
実行に追加依存は不要。リポジトリのnpm依存導入後は次で型チェックできる。

```sh
node node_modules/typescript/bin/tsc -p apps/runner-prototype/tsconfig.json
```

process-experiment.tsがゲートウェイを持ち、service-worker.tsを子として起動する。
子は実際のmyServiceをimportし、そのAPIを提供する。ブラウザ向けrunStudentServiceは利用しない。
未対応の挨拶・経路案内は明示的にエラーにする。人物は合成観測、接近は80 msのfake操作、
追従は最長1秒のfake操作であり、画像認識・追跡・車体運動は実装していない。
短い時間設定は自動試験用で、手入力向けではない。既存サービス自体には時計呼び出しがないため
その移植はなく、待機中の移動をゲートウェイへ注入した時計と仮想pauseで制御する。

## 分離した責務と期限

runnerがCPU処理で応答しなくなっても、ゲートウェイは動作する。1つのsessionを受け付け、
移動tokenのsession/generationを照合し、受け渡し中の禁止と期限切れを管理する。
古いstop/renewが新しい所有者へ干渉することを防ぎ、要求・応答・終了結果を対応づける。
停止は学生のイベントキューを経由しない。実機への接続はない。

| 期限 | 実験値 | 更新条件・時計 |
| --- | --- | --- |
| 指令TTL | 250 ms | 現在tokenの更新のみ。ホスト単調時計 |
| runner lease | 400 ms | 有効なsessionのheartbeat。ホスト単調時計 |
| 操作進捗 | 1秒 | 開始時に固定し、延長しない。仮想時間 |
| 停止確認 | 200 ms | pause中もホスト単調時計 |
| 子側のRPC／終了待ち | 2秒／3秒 | クライアントの待機上限。超過は停止確認ではない |

runnerは40 ms間隔でheartbeatと現在tokenの更新を送り、ゲートウェイは10 ms間隔で確認する。
これらは試験値であり、実機の安全な停止時間を測定した値ではない。OSによる実行遅延もあり、
実時間保証を主張しない。heartbeatだけでは指令TTLを延長できず、指令更新が続いても
進捗期限は延長されない。pauseは仮想進捗を止めるが、ホスト側のleaseとTTLは止めない。

停止開始時にfakeの未実行動作を無効化する一方、確認は別に遅延・欠落させる。
確認待ちの間は新しい移動を禁止する。確認が届かない・遅すぎる場合はstop-unconfirmedとして
sessionを失効させ、移動禁止を保持する。到着や正常完了にはしない。
到着の停止確認待ちで権限が失効した場合も、終了結果をinterruptedへ切り替える。
recoverはfake操作員による静止・人の離脱の明示的確認であり、実機の復旧手順を規定しない。

荷物を載せる確認中はロボット全体の移動を禁止する。Items are loadedだけでは解除せず、
clearToMove=trueも必要。質問IDとsessionで古い回答・重複回答を拒否し、
runnerが失われても受け渡し中の禁止は残る。
既存サービスの最後は「荷物を取ってください」という発話で終了する。
**受取人が荷物を下ろす間の禁止・確認は今回追加していない。**
S2全体を実装するときのサービス変更として残る。

## ローカル試験用の操作

標準入力はid/typeを持つ改行区切りJSON。応答はid/ok/value/error。
非同期イベントはprompt/terminal/revoked/say/service-result/worker-exited。
応答はID、質問は質問IDとsessionで照合する。出力順を全体のイベント順序とは扱わない。

| 操作 | 内容 |
| --- | --- |
| start | sessionを発行し既存サービスを起動。両プロセスのPIDを返す |
| answer | promptId/session/answer。受け渡し用はclearToMove=trueも必要 |
| snapshot | fake対象、移動所有者、禁止、pause、runnerの状態 |
| pause / resume | 仮想進捗を制御。ホストwatchdogは停止しない |
| stop | session失効と停止要求。応答だけでは停止確認ではない |
| recover | confirmed=trueでfake静止・人の離脱を確認 |
| fault | kill/block/disconnect/stalled/missing-evidence/delayed-evidence/normal-evidence |

blockはrunnerだけを1.5秒CPU処理で止め、disconnectはIPCを切る。停止確認の遅延は100 ms、欠落は無応答。
故障注入はテスト専用でRoverAdapterの必須機能ではない。試行ごとに新しいプロセスを使う。
EOFでsessionを失効し、子を終了し、停止確認期限まではゲートウェイを動作させる。
標準入出力と継承IPCは信頼された試験用接続で、認証済みネットワークAPIではない。

## 検証と次の境界

「到着の停止確認待ちで権限失効」の競合も含め、全24件のテスト、strict型チェック、
自動demoがNode.js 26.13.0で成功した。GitHub ActionsにもNode.js 22/24で同じ検証を
行うworkflowを追加した。それらの環境での実行結果はCIを参照する。

内訳は第1段階9件、決定的なゲートウェイ試験8件、プロセス間試験7件。
TTL/lease/進捗期限、停止確認遅延・欠落、古いtoken、受け渡し禁止、到着との競合、
正常／辞退分岐、pause中のrunner強制終了・CPU停止・IPC切断を扱う。
既存PWA/Pythonのソース・実行経路は変更しておらず、それらのテストは今回再実行していない。

次はPython serverの受付・実行中・終了通知、停止確認、lease所有者を定義し、
fake adapterで接続する。既存の速度制限・安全確認・E-stop・機体の保護を維持する。
操作員の切断、カメラ消失、ゲートウェイ停止、下流機体watchdogも実機試験前に検証する。
ゲートウェイ自体が落ちる場合を同じプロセス内のfakeだけでは保護できない。

未実装：Python接続、本番facade/時計抽象化、UI再接続・役割認証、実機停止確認・TTL・速度／安全制限、
永続ジョブ、地図・自己位置・認識、mailbox統合、ゲートウェイ停止の安全性検証、
WSL配布、ROS/箱庭。停止結果は合成動作の無効化だけを表す。
