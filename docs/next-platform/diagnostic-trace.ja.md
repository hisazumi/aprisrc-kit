# 位置・経路・サービスの診断ログ

## 目的と使い方

運用画面 `/console` の「診断ログを保存」で、そのサーバ起動中の記録を
`apris-diagnostic-trace.json` に保存する。実行終了後や失敗後にも保存できる。
取得APIは `GET /api/trace`。既存のloopback・共有トークン・Origin境界を使用する。
保存操作はoperator/runのlease更新、復帰、guard解除、移動を行わない。
サーバを再起動すると記録は消えるため、調査対象の実行後に保存する。

## 記録の対応付け

全レコードはサーバの単調時刻と連番cursorを持つ。traceIdはサーバ側の記録器を識別する。
contextにはcontrolEpoch、runId/runEpoch、同じrunのroute実行ID・経路ID・区間・動作数・状態、
位置推定の評価結果、位置ゲートの理由、受け渡しguardと移動禁止状態を持つ。
別runの古いrouteを新しいrunの記録へ付けない。
停止でrunを解放した後もrevoked・motion terminal・route terminal・service finishを
元のrunEpochへ対応付ける。

位置評価は安全ゲートが最後に評価したスナップショットを再利用する。
記録のために推定器の時計・連番・lost状態を進めない。
記録時刻と位置のsampleTime/receivedTimeは異なるため、鮮度の判断には両方を見る。
推定結果には地図のID・版・digest、localization/odometry epoch、odom/mapの位置、
誤差指標・品質・根拠が含まれる。未評価の場合はnullとなる。

| kind | 意味 |
| --- | --- |
| operatorAction | 復帰、受け渡し解除、run開閉などの受付後の状態。heartbeatは除外 |
| localizationSample | run中の定期位置評価記録。最大2Hz |
| markerCorrection | 正規化済みマーカ観測に対する推定器の処理結果 |
| routeStarted / routeAction | 経路開始／各区間の動作要求。routeActionだけでは受付・完了を意味しない |
| terminal / revoked / localizationLost / routeTerminal | 動作・run・位置・経路の終了または喪失理由 |
| serviceStarted / serviceFinished | サービス開始／終了結果 |
| serviceQuestion / serviceAnswer / serviceConsumed | 質問の発行／回答受付／安全確認後の消費。questionIdで対応付け |
| serviceSpeech | 発話の受付。本文ではなくサービス内のindex |

質問・回答・発話の本文と認証トークンは記録しない。
エラー理由には技術的な診断文字列が含まれる。

## 調査手順

1. `serviceFinished` のrunEpochを選び、同じrunの記録をcursor順で読む。
2. `routeStarted` で経路と開始位置を確認し、`routeAction` とmotion terminalを照合する。
3. 最初の `revoked` / `localizationLost` / 失敗terminalを探し、位置品質とゲート理由を見る。
4. `routeTerminal` で到着・中断・停止未確認を区別する。
5. 正常配送では到着後に受け取り質問が消費され、その後サービスが完了することを確認する。

停止未確認は停止成功や到着として解釈しない。
発話受付は音声出力の完了を意味しない。

## 上限と限界

最大512件・JSONレコード合計180,000 bytesのメモリリング。
1件16,384 bytesを超える記録やJSON化できない記録は保存せず、欠落として数える。
古い記録の削除も `dropped` に加算し、1件でも欠落すると `complete=false` となる。
cursorの飛びとdroppedを確認し、不完全なログから「その出来事はなかった」と断定しない。
`complete=true` も、この診断用に選んだイベントが欠落していないという意味であり、
全センサ入力を記録したことや事故解析用の完全な履歴を保証しない。

これは平面シミュレータの診断記録であり、実機の停止根拠を追加する機能ではない。
記録のアップロード・永続化・自動再生・モータ命令の再送APIは持たない。
M4の入力記録と再現試験は未完であり、このログ単独では決定的な再生はできない。

## 検証

Pythonの容量・byte上限・コピー独立性・欠落・認証・副作用なしの試験、
運用画面の保存操作試験、配送正常完了と途中中断の接続試験で検証する。
正常時は荷積み確認→経路開始→到着→荷受け確認の順を、
中断時は元runへの理由・終端の対応付けと到着非通知を確認する。
