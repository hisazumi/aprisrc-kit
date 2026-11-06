# run・受け渡しguard・運用者の制御契約

[English（正本）](control-contract.md) · [統合計画](integration-plan.ja.md) · [移動契約](motion-contract.ja.md)

既存の fake RunnerPort に実装した。共通 JSON の22ケースを TypeScript と Python で検証する。
現行アプリの起動経路や実機 adapter は変更しておらず、共有 FastAPI への統合はまだである。

## 識別と信頼境界

既存の継承 pipe で {action: "control", message: <control-v1>} を受け付ける。
初期接続時は既存 snapshot の controlEpoch を読む。
全メッセージに protocolVersion=1、connectionEpoch=controlEpoch、requestId、
robotId=fake-only を付ける。controlEpoch は port インスタンスごとに server が生成する。
別途発行する runEpoch が、移動契約の connectionEpoch／session に対応する。
古い epoch・運用者 ID・guard ID では新しい操作を許可しない。

ここは信頼されたローカル試験接続である。openOperator はログインや本人確認ではなく、
pipe に接続できる呼出元を信頼する。将来の network／session 境界では、/app・/console・/lab の
権限と識別子の保護を実装する。認証済みの複数利用者運用が完成したという意味ではない。

## コマンド

| コマンド | 共通 envelope 以外の項目 | 効果 |
| --- | --- | --- |
| openOperator | なし | operatorId と独立した lease を発行。明示復帰までは移動禁止 |
| operatorHeartbeat | operatorId、sequence | 新しい連番の場合だけ運用者 lease を延長 |
| openRun | operatorId、runId | 運用者が有効で、guard・移動禁止・古い I/O がない場合に runEpoch を発行 |
| runnerHeartbeat | runId、runEpoch、sequence | 新しい連番の場合だけ run lease を延長 |
| closeRun | runId、runEpoch | 該当 run を失効して停止を開始。guard は保持 |
| acquireHandover | runId、runEpoch | 停止証拠を確認し、guardId を発行して移動を禁止 |
| clearHandover | operatorId、guardId、confirmed=true | 人の退避確認で該当 guard を解除。別原因の移動禁止は解除しない |
| globalStop | なし | 現在の run を失効し、移動禁止を保持。要求記録の容量とは独立 |
| recover | operatorId、guardId または null、confirmed=true | guard ID の一致、run・移動・古い I/O の不存在、停止証拠を要求して復帰 |
| snapshot | なし | lease を更新せず状態を照会 |

受付応答は controlReply。コマンド名、operatorId、runId、runEpoch、guardId、
inhibited、stopPending を返す。識別子は該当状態がなければ null。
close／stop の受付応答は停止確認ではなく、移動 terminal の停止証拠とは別である。
stopPending は通常の移動も含む operation または古い I/O の存在を示し、物理的な停止計測ではない。
不正な要求は既存の外側のエラー応答とする。runId は port の生存中に再利用しない。

guard は質問・run・運用者の寿命を越えて残る。古い close で新しい run を止めない。
clearHandover／recover は対応する guard ID と停止証拠を必要とするため、
遅れて届いた退避確認で別の受け渡しを解除しない。
証拠は依然として fake 用であり、実機へ人が接近してよいという検証ではない。

## lease・重複要求・停止経路

運用者 lease は runner lease と移動の TTL／進捗期限から独立している。
実験値は400 msであり、本番向けの実測値ではない。
要求処理前と watchdog で期限を検査する。運用者が失効したら run を失効させ、停止を開始し、
移動禁止を保持する。遅れた heartbeat で復活させず、新しい運用者と明示復帰を必要とする。
runner heartbeat では運用者を延命せず、どちらの heartbeat も移動 TTL・進捗期限を延ばさない。

heartbeat の sequence は正の安全な整数。前回より大きい連番だけで lease を延ばす。
重複・古い連番は現在状態を返すだけで、期限を延長しない。
固定サイズの状態で処理し、heartbeat ごとに記録を増やさない。
snapshot も lease を延ばさない。通常画面の寿命と運用者 heartbeat を結び付けない方針は、
後の UI 接続でも維持する必要がある。

その他の制御は requestId ごとに成功応答・拒否理由を保持する（既定256件／port）。
同一要求の再送には過去の応答を返し、再実行しない。同一 ID の別内容は拒否する。
過去の open／close の再送で、後の run を開始・終了しない。
過去の応答は新しい snapshot や権限更新ではない。
容量超過では新しい通常制御を拒否するが、globalStop・snapshot・連番付き heartbeat は受け付ける。
globalStop は繰り返されても現在の機体状態へ適用するので、再接続時に自動再送しない。
本番での記録保持・接続切替の方針は後続とする。

openOperator で型付き制御を有効にすると、既存の admit／heartbeat／move／hold／clear／recover
から迂回できない。型付き motion、試験 fixture、既存の読取専用 snapshot、停止専用 revoke は残す。
内部では同じ port lock と期限検査を使う。
他の FastAPI client 全体に対する guard ではなく、その統合は段階 C で行う。

## 検証と次の作業

実装前にテストを書いた。decoder 実装後に共通22ケースが成功し、port 接続前には
振る舞い5件の失敗を確認した。接続後に、動作中停止・epoch・再送のケースも追加した。

- guard 中の移動拒否、run 終了後の保持、対応する退避確認による解除。
- 更新より前の運用者失効、guard 保持、駆動中の fake operation の中断。
- globalStop の受付時点では stopPending、その後に terminal の停止証拠。
- heartbeat 再送・snapshot による lease の意図しない延長がないこと。
- 記録容量が満杯でも停止・状態照会が可能なこと。
- 証拠欠落時の復帰拒否、既存呼出による迂回の拒否。
- 古い epoch・過去の close 再送で新しい run を終了しないこと。

ローカル検証は Node 107件、既存 motion／port／runtime 回帰を含む Python 97件、
厳密な TypeScript 検査と Ruff が成功。
別プロセス試験では、Node から Python へ運用者受付、復帰、run 開始、guard の取得・解除、
移動まで接続した。CI にも新規テスト・fixture・lint 対象を加えた。

次は activity の親子関係・mailbox・capability facade を単一 runner へ統合する（B）。
テスト用 stream 接続を上限付き transport に置き換え、共有 server の操作権・guard（C）、
実際の位置変化を伴う Simulator（D）へ進む。
guard の永続化、認証付き UI 復帰、実機停止の検証は別途必要である。
今回の型付き制御経路では、再起動後も明示復帰までは移動を禁止する。

## runner コア

[activity runner コア](activity-runner.ja.md)に親子 scope・mailbox・移動 capability を統合し、Python port に接続した。
