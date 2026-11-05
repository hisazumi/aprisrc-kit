# 外部runner：最初の実行契約の試作

[English](runner-prototype.md) · [アーキテクチャ](architecture.ja.md)

状態：独立した実行可能な試作、2026-11-05。既存PWAの置換や実機機能の追加ではない。

## 目的と範囲

既存サービスをサーバへ接続する前に、run/activityの識別、イベント配送、移動の排他、
受け渡し中の移動禁止、シミュレーションのキャンセルを確かめる。
Node.jsプロセス単独で動作し、同一プロセス内のメモリ上のfake backendを利用する。
実機の選択・通信、ネットワーク待受け、独立した安全プロセスはない。追加依存もない。

`apps/runner-prototype/`は契約を検証する試作であり、学生のミッション配置先ではない。
既存のmission/configの配置を維持する。既存student facadeの抽出・接続は次の段階。

## 実行方法

TypeScriptを直接実行できるNode.js 22.18以降を使用する。今回の実行環境は26.13.0。
リポジトリのルートから実行する。

```sh
node --test apps/runner-prototype/runtime.test.ts
node apps/runner-prototype/runner.ts
```

後者は標準入力のJSONを1行ずつ受け取り、応答と操作の終了イベントを標準出力へ返す。
新しいプロセスで、以下を順番に入力できる。

```json
{"id":1,"type":"start","service":"delivery"}
{"id":2,"type":"move","scope":{"runId":"run-1","activityId":"root","epoch":0},"duration":10}
{"id":3,"type":"pause"}
{"id":4,"type":"cancel","scope":{"runId":"run-1","activityId":"root","epoch":0}}
{"id":5,"type":"snapshot"}
```

pause中でもstepせずにcancelが完了し、操作と対応づいた終了イベントが返る。
実際のクライアントではstartの応答のscopeを使う。標準入力を閉じると実行中のrunを
中断して終了する。これはブラウザ切断時の運用方針を実装したものではない。

## APIと合格条件

| API | 今回の契約 |
| --- | --- |
| start(service) | runとepochを発行。同じserviceの実行重複を拒否。対象は1台のfake robot |
| activity(root, handler) | root直下の並行活動。遷移ハンドラは同期的に戻る |
| send / dispatch | 宛先別の上限付きFIFO。1回のdispatchで各活動1イベント。満杯・古い宛先を明示的に拒否 |
| move(scope, duration) | 秒単位の仮想時間による操作。tokenと終了Promiseを返す。移動競合を拒否 |
| cancel(scope) | scopeを先に失効。rootなら子活動・質問も破棄。対象操作を一度だけ終了 |
| prompt / answer | 質問IDで照合。受け渡し用は停止中のみ開始でき、ロボット全体の移動を禁止 |
| pause / step / reset | 仮想時間の停止・進行・試行の初期化。resetは全run中断後にepoch更新 |
| globalStop / snapshot | キューに依存しない全run中断と状態参照。全停止でも受け渡しの禁止は保持 |

合格条件を次の9件の自動テストにした。Node.js 26.13.0で全件成功した。

1. 移動待ちの間も別活動へ注文イベントを順番に配送できる。
2. rootキャンセル後の子活動・イベント・再取得を拒否し、古いstopが新しい所有者を止めない。
3. 通常の質問活動だけをキャンセルしても、別活動の移動が続く。
4. 受け渡し中は別runも移動できず、質問キャンセル後も禁止が残る。
5. 移動中には受け渡しを開始できず、明示的な離脱確認と回答の重複拒否が働く。
6. pause中は仮想時間が進まず、stepせずcancel/resetでき、旧epochは復活しない。
7. 重複startと満杯キューを明示的に拒否し、全停止は実行できる。
8. ハンドラの例外でrunを中断し、移動を無効化する。
9. 別の子プロセスで起動し、ブラウザなしでpause中のcancelとEOF終了ができる。

FakeMotionの公開メソッドはテスト用で、認可境界ではない。generation照合を用意したが、
実装済みの要求はscope付きstopだけで、drive/renewは未実装。停止の証拠は仮想操作の
無効化であり、実機の静止を意味しない。受け渡しキャンセル後は明示的なfake操作員の
離脱確認で禁止を解除する。reset時の解除は仮想世界全体の破棄に限定される。

標準入力APIはstart/move/cancel/pause/resume/step/reset/stop/snapshotのみ。
並行活動と質問は単体テストで直接検証する。既存PWA/serverのテストは今回の対象外。

## 次の検証と未実装事項

次は既存の逐次サービス1つにmotion/interaction/clockのportを注入して実行する。
fake安全ゲートウェイを別プロセスへ分離し、runner停止、イベントループ停止、通信断、
停止確認の遅延・失敗を注入する。その段階で実時間のlease/progress期限とTTLを定め、
通過後に既存Python serverへ接続する。

今回は、実機アダプタの停止確認・期限、実時間watchdog、認証・lease、UIの役割・再接続・
切断、観測バッファ、操作の全状態遷移、入れ子活動、永続ジョブ、自動dispatch、地図・
位置推定・認識、ROS/箱庭、WSL配布、実機の速度制限・安全確認は実装していない。
メモリのみの試作であり、技術選定の確定や実機安全性の検証結果とは扱わない。
