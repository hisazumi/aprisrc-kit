# 実機Playground

[English](hardware-playground.md)

共通UIはシミュレータで検証していますが、実機での再検証が必要です。
以前の人追従の実機結果は別のUIによるもので、この版の動作保証にはなりません。

## 準備と開始

1. [UGV02自己試験](../hardware/ugv02-self-test.ja.md)または
   [iron-Xネットワーク接続](../hardware/ironx-network.ja.md)で機体を準備します。競合する走行送信者は停止します。
2. 対応する実機AdapterでKitサーバーを起動します。ブラウザでAdapterは切り替わりません。
   固定したスマホでは[HTTPS](../local-https.ja.md)を使います。
3. `/playground?service=greeting`で**Start vision**を押し、カメラを許可して前方へ向けます。
   受理された人物観測と新鮮なtelemetryを確認します。
4. 操作者が周囲全体を空け、試験を承認します。最初は車輪を浮かせてください。
   **Acquire control → Confirm clear path · 30 s → Start service**の順に操作します。
   最後のボタンで動き始める可能性があります。カメラ起動だけでは走行しません。
5. 挨拶の短い旋回と停止を確認します。**Cancel and stop**で中断、
   **Emergency stop**で停止をラッチします。物理停止・電源も操作できるようにします。
6. 確認後、`/playground?service=carry`で短い監視付き試験を行います。
   **Yes → Items are loaded → We have arrived**で追従・終了を試します。

## 現在の走行許可の制約

実機のService・Playgroundは、別ボタンの**30秒の手動確認**を使います。
サービス開始では許可も延長もしません。時間は前方確認を押した時点から数え、
質問への回答待ちも含みます。追従中でも失効します。失効すると前方確認が取り消され、
前進が制限され、サービスが失敗・停止する場合があります。
全方向・全指令が正確に30秒で停止するという保証ではありません。

失効時は中断し、実際の停止と周囲を確認してから再許可し、明示的に再開してください。
再接続だけで再開してはいけません。旧Carry専用UIの自動更新は共通UIに引き継がれていません。
これは既知の操作上の後退で、新しい安全要件やファーム変更ではありません。

ページ非表示、フォーカス喪失、操作権喪失、切断、非常停止でも早期に失効します。
手動確認は障害物センサーではなく、後方・側方の保護はありません。
自動準備・更新をするのは**SimulatorのPlaygroundだけ**です。
Simulator接続でもService画面は別の手動確認を使います。

## 表示と範囲

共通サービスパネル、**Implementation**の実サービス定義、カメラ観測、地図・telemetry、
**Advanced controls**を表示します。旧専用UIの実行行強調やプレビュースライダーはありません。
仮想人物・マーカー操作はシミュレータ限定です。
実機マーカー案内はService・Playgroundとも無効です。
旧`/app?service=receptionist`も同じ画面への別名で、別の実機経路ではありません。

画面の構成は[PWA views](../pwa-views.ja.md)、PC・スマホの準備と非常停止解除は
[iron-X人追従](../hardware/ironx-follow.ja.md)を参照してください。
シミュレータ試験、telemetryだけ、過去の実機試験を、このUIの実停止確認と混同しないでください。
