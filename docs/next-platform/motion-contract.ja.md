# 移動契約 v1：統合の最初の実装

[English（正本）](motion-contract.md) · [統合計画](integration-plan.ja.md)

apps/runner-prototype/motion-contract.ts と16件のテストを追加した。
段階 A の移動部分であり、再利用する契約コードとして実装している。
現行アプリの起動経路と既存通信形式は維持する。Python の実験用 port へ
motion action を追加して移動契約を接続した。run・guard・運用者の契約は引き続き扱う。

## メッセージの規則

全メッセージに protocolVersion=1、connectionEpoch、requestId、robotId、runId、
activityId、operationId を付ける。ID は空白だけでない64文字以下の文字列。
accepted／running／rejected／terminal は start の識別情報全体を引き継ぐ。
renewMotion／cancelMotion は自身の requestId を持ち、元の operationId と generation を
参照する。その要求には commandAck で受付を返す。停止確認を意味しない。
未知の項目・version は拒否する。

runner が送信前に operationId を生成し、Python が generation を付与する設計とする。
connectionEpoch は server 再起動も含め接続ごとに新しくする。
generation は正の安全な整数で、epoch との組合せに意味がある。

| 種別 | 追加項目 |
| --- | --- |
| startMotion | move(distanceM, speedMps) または turn(angleRad, speedRadS) の goal |
| renewMotion、cancelMotion | generation |
| accepted、running、commandAck | generation |
| rejected | reason |
| terminal | generation、outcome、reason、evidence |

入力範囲は既存 Python の MoveCommand／TurnCommand に合わせる。
距離は±5 m、絶対値1e-9 m以上、速度0.05〜0.30 m/s。
角度は±4π rad、角速度0.10〜1.20 rad/s。
既存の最小回転角1e-9度は明示変換して検査する。
今後の Python 接続では、既存の度単位 API 境界で変換する。
これは互換性のための範囲であり、すべての機体・場面で最大値が安全という意味ではない。
Python の最終制限検査は残す。非有限値や文字列からの暗黙変換は受け付けない。

## 結果と停止証拠

completed／cancelled／interrupted は simulated または physical の証拠を必要とする。
failed はそれらの証拠、または「当該 operation は駆動していない」not-started を持つ。
stop-unconfirmed は unknown を持ち、普通の取消と区別する。
証拠の epoch は backend の時間系、observedAt はその時間系の非負の単調時刻（秒）。
異なる epoch や実時刻とは直接比較しない。対象 operation／generation は外側の識別情報で示す。
検証できるのは形式と意味の整合であり、証拠の真実性は backend の責務である。
実機 adapter の検証を省略できるわけではない。

MotionClient は send 前に結果の受け口を登録する。
同期的に terminal が accepted より先に届いても結果を失わない。
最初に対応する進捗・terminal の generation を記録し、異なる epoch・ID・以後の世代では
完了させない。最初の terminal を採用する。
不正な受信や受付後の拒否は接続を閉じ、未完了 Promise を operation-uncertain として失敗させる。
通信断・送信失敗も同様で、架空の停止済み・成功は返さない。
client の終了自体は stop を送らないため、server の独立した lease／watchdog との接続が必要。

MotionTransport はメッセージと切断を通知する interface とした。
具象 transport には framing・buffer の上限、parse／stream error の報告、
移動の自動再送禁止が必要になる。send は同期受付で、後発の書込失敗は切断通知にする。
今回、具象 stream transport は追加していない。

## 記録容量と受付モデル

MotionClient は完了済みも含む operation／request ID を接続中保持する（既定256件）。
重複 start と容量超過は送信前に拒否し、古い記録を黙って捨てない。
本番での接続切替には明示的な終了・復帰の意味を先に実装する必要がある。

StartLedger は server 受付の契約テスト用モデル。
JSON の項目順によらず、同一要求の再送には元の generation と duplicate=true を返す。
duplicate=false の場合だけ新しい仕事を開始できる。
同じ ID の異なる要求・容量超過は拒否する。
機体の操作権や結果の再配信は実装していない。最終的な管理主体は Python である。

## 検証と次の作業

最初の11件を module 作成前に書き、未実装による import 失敗を確認した。
実装後に11件が成功し、追加の境界・生命周期5件も成功した。
新規コードのテスト先行開発であり、既存製品の不具合を再現したという意味ではない。
既存の Node 33件（Python subprocess 7件を含む）と厳密な TypeScript 検査も成功した。
既存 CI の wildcard で、新規テストも Node 22／24 と Python 統合 job の対象になる。

## Python 接続（2026-11-06）

既存 RunnerPort に {action: "motion", session, message: <motion-v1>} を追加した。
接続受付・heartbeat は引き続き実験用の既存 envelope を使う。
server が発行した session を connectionEpoch とし、robotId は fake-only に限定する。
最初の start で runId を固定する。
共通 JSON fixture（apps/runner-prototype/fixtures/motion-v1.json）の正常・異常32ケースを
TypeScript と Python がそれぞれ検証する。UTF-16 の ID 長、空白、真偽値と数値の区別、
有限の SI 値について両言語を合わせた。

Python は既存 TurnCommand 境界で rad を度に変換し、runtime の安全検査と
TTL・進捗・停止期限を維持する。PortFakeAdapter の疑似時間待ちを回転にも対応させたが、
実際の位置変化はまだ検証していない。simulated 停止証拠の epoch は fake- で始め、
実機接続は引き続き許可しない。

受付・拒否した start と最終結果を Python が保持する。同一要求の再送には同じ受付・結果を
返し、二度動かさない。同じ ID の異なる内容は拒否する。
renew／cancel は自身の requestId と commandAck を持ち、再送で TTL の再延長・取消の再発行をしない。
記録容量（既定では session あたり256要求）が満杯なら、新しい移動 protocol の要求は
renew／cancel を含め拒否する。独立した既存 revoke／global-stop と TTL／lease 期限は有効。
暗黙の記録破棄・接続切替はしない。不正・失効済みの要求は外側のエラー応答にする。
本番の長時間実行には記録保持・接続切替の方針が必要になる。
session 失効後の再送も拒否し、古い動作の再許可にはしない。

Python decoder／接続の前にテストを追加した。decoder 実装後は共通32ケースが成功し、
port の3件は unsupported-action で失敗した。接続後に3件も成功した。
さらに古い scope／epoch、拒否の保持、容量、回転の単位変換、非有限値、更新前期限切れを検証した。
別プロセスの Python に MotionClient を接続する3件では、完了・取消・停止証拠欠落を確認した。
stream 接続はテスト用であり、本番の framing・認証・queue 上限は別途実装する。

ローカルでは Node 84件、既存 port／runtime 回帰を含む Python 67件、厳密な TypeScript 検査、Ruff が成功。
Node suite に共通 fixture と新しい subprocess 3件を加え、CI に Python の契約テストと lint を組み込んだ。

次は run・guard・運用者の契約と本番 transport、その後に activity runner（B）と
共通操作権（C）を統合する。FastAPI／手動操作を含む guard、実際の位置変化を伴う Simulator（D）は未完了。
今回の到達点は既存 fake port への移動契約の接続であり、段階 A 全体の完了ではない。

## 制御契約の接続

[制御契約](control-contract.ja.md)に run の受付・終了、受け渡しguard、独立した運用者 lease を実装した。
次は runner と上限付き transport の統合、その後に共有 server 全体の操作権を統合する。
