# 移動契約 v1：統合の最初の実装

[English（正本）](motion-contract.md) · [統合計画](integration-plan.ja.md)

apps/runner-prototype/motion-contract.ts と16件のテストを追加した。
段階 A の移動部分であり、再利用する契約コードとして実装している。
既存起動経路と通信形式は変更していない。
Python 側への採用、run・guard・運用者の契約は引き続き統合作業で扱う。

## メッセージの規則

全メッセージに protocolVersion=1、connectionEpoch、requestId、robotId、runId、
activityId、operationId を付ける。ID は空白だけでない64文字以下の文字列。
accepted／running／rejected／terminal は start の識別情報全体を引き継ぐ。
renewMotion／cancelMotion は自身の requestId を持ち、元の operationId と generation を
参照する。その要求への受付応答は今回の移動結果ストリームの対象外である。
未知の項目・version は拒否する。

runner が送信前に operationId を生成し、Python が generation を付与する設計とする。
connectionEpoch は server 再起動も含め接続ごとに新しくする。
generation は正の安全な整数で、epoch との組合せに意味がある。

| 種別 | 追加項目 |
| --- | --- |
| startMotion | move(distanceM, speedMps) または turn(angleRad, speedRadS) の goal |
| renewMotion、cancelMotion | generation |
| accepted、running | generation |
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

次に Python 境界へ採用し、共通のシリアライズ済み fixture で言語間の一致を検証する。
run・guard・運用者契約と要求受付応答も追加する。
両端が契約を使用するまで段階 A 完了とはしない。
その後に activity runner 統合（B）、共通操作権（C）、実際の位置変化を伴う Simulator（D）へ進む。
