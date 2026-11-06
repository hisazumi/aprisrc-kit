# activity runner の統合コア

[English（正本）](activity-runner.md) · [統合計画](integration-plan.ja.md)

apps/runner-prototype/activity-runner.ts の ActivityRunner に、activity の所有関係、
宛先付き mailbox、scope 付き capability facade をまとめた。
Node 側に移動操作権や受け渡しguardを重ねて持たせず、MotionClient を介して Python に委ねる。
段階 B のコアであり、新しい実行用実験や現行ブラウザ起動経路の置換ではない。

## 生命周期とリソース

host が受付済みの runId／runEpoch を渡し、runner が root activity を作る。
activity は上限内で任意に入れ子にでき、それぞれ mailbox、AbortSignal、移動 Promise、
質問、timer、購読解除処理を所有する。
capabilities(scope) は move・prompt・after・subscribe・spawn を提供し、
無条件の stop や直接の通信経路を公開しない。

取消では先に子孫全体を無効化し、queue を消す。その後に移動取消、質問の失敗通知、
timer の取消、購読解除を行い、すでに終了処理中の子も含めて管理対象の処理を join する。
取消の再要求は同じ完了 Promise を返す。
古い応答・イベント・終了済み親への子の追加は拒否する。
質問だけを取り消しても兄弟の移動を止めず、質問への回答で Python のguardを解除しない。

後始末の待機上限は既定1秒（host 時間）。timeout、backend の不確実性、cleanup 失敗では
join を失敗させ、診断情報を残す。timeout を停止済みと見なさず、未解決の Promise は
snapshot の pending に残す。
AbortSignal で任意の非協調的な JavaScript を強制終了できるわけではなく、
プロセス隔離と Python の独立した期限検査は引き続き必要である。

既定上限は mailbox 8件／activity、終了済み記録を含め256 activity／runner、
管理リソース64件／activity。質問は Promise と cleanup の2枠を予約する。
これは件数上限であり、payload のバイト数上限は後の transport で扱う。
timer は現在 host 時間のみで、pause／reset 対応とはしない。

## イベント処理と移動

mailbox は宛先付き FIFO とし、入力を複製して格納する。
1回の dispatch では、その開始時に存在した各 activity から最大1件を処理する。
追加の round は setImmediate で実行し、microtask の連鎖で他の処理を塞がない。
queue overflow は送信側へ通知する。
handler は同期的に戻り、capability の非同期処理は開始してから結果を後で扱う。
handler の例外や Promise の return は run を中断する。
runner が管理・join するのは facade に登録された処理である。

MotionClient は generation が届く前の取消を保持し、判明したら1度だけ scope 付き取消を送る。
先に terminal が来た場合は取消を送らない。
取消受付では移動 Promise を完了させず、terminal と停止証拠を待つ。
adapter は動作中40 msごとに operation を更新し、abort／terminal で更新を止める。
Python の固定された進捗期限は延長しない。
更新要求 ID にも容量上限を設け、超過時は未完了処理を不確実として扱う。
取消用には operation あたり1件を別途確保する。
Python 側の要求容量が先に上限へ達する場合もあり、本番の session 切替は未実装。
これらの値は実験用で、実機の安全を保証する数値ではない。

## 検証

ローカルの Node suite は Python subprocess を含む121件が成功し、厳密な TypeScript 検査も成功。
既存 CI の wildcard に新規テストが含まれる。Python のソースは変更していない。

runner の8件では、親子の無効化・join、兄弟の独立性、FIFO・overflow、リソース cleanup、
handler 失敗、非協調的な処理、scope・容量、停止不明の扱いを検証した。
MotionClient の3件では、受付前取消、terminal 先行時の取消抑止、上限付き更新を検証した。
別プロセスの3件では、runner と既存 Python fake port を接続し、
更新なしの TTL を越える移動の完了、子孫の取消、Python 喪失を確認した。

新規 module の前にテストを書いた。
追加の失敗テストで、最初の実装が join 時に移動 Promise の失敗を無視することを検出した。
修正後は不確実性を保持し、後始末を成功扱いしない。

## 残る統合作業

旧 runtime.ts・プロセス実験は回帰試験用として残し、新しい runner 経路で二重に操作権を管理しない。
StudentServiceApi 全体、観測入力、既存 service-worker の起動経路はまだ接続していない。
試験 host が制御契約による受付、運用者・run の独立した heartbeat、root cleanup 後の closeRun を担当する。
ローカルの root 取消だけで server の run やguardを解除することはない。
Python 喪失試験は不確実性の扱いの確認であり、その状況での実機停止の検証ではない。

次は上限付き transport と実行hostを一つにまとめ、失敗時の run 終了を担当させる。
そのうえで学生向けサービスをこのコアへ接続する。
続いて共有 server 全体の操作権・guard（C）、実際の位置変化を伴う Simulator（D）へ進む。
実機、認証付き複数利用者 UI、リッチな simulation が完成したという意味ではない。

## host の統合

[サービスhost](service-host.ja.md)に上限付き通信、受付、生存更新、終了処理をまとめ、既存の学生サービスを接続した。
