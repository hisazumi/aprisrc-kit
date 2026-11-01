# PWA views

[English](pwa-views.md)

Rover PWA は単一のコードベースとビルド成果物を使い、用途別に3つのURLを提供する。画面を分けても、Local Server、WebSocketプロトコル、ミッションAPI、UIコンポーネントは共通である。

共通ヘッダーではサービスと画面（**Service / Playground / Console**）を独立に選ぶ。
URLのサービス識別子は `?service=my-service`、`carry`、`receptionist`、`greeting`。
画面移動ではサービスを、サービス変更では画面を維持する。再読み込み・戻る・リンク共有でも両方の選択を復元する。
実行中は停止してから切り替える。画面移動でシミュレータ／実機の接続先が変更されることはない。

**My service** は `missions/studentCarry.ts` の編集用ひな形。初期動作は荷物運びの例であり、用途を限定しない。
表示名はコードの `title` で変更でき、URLの識別子は `my-service` のまま使う。
旧 `/app`、`/lab`、`?service=student`、`?sample=student|greeting|follow|receptionist` も受け付け、新URLに整理する。
`follow` は `carry` に対応し、選択がない場合は My service が既定となる。

コンソールの最新手順は[iron-X操作ガイド](hardware/ironx-quickstart.ja.md)も参照する。
`/console`には **Confirm clear path · 30 s** を追加した。接続中の操作権保持者が、
前方を目視確認して既存APIへ期限付きの手動確認を送る。押すだけでは走行しない。
期限切れ・接続断・操作権喪失・E-stop・障害物検知・タブ非表示・フォーカス喪失・解除・離脱で無効になる。
後方や側方の障害物保護を追加するものではなく、周囲全体の監視が必要。他画面の操作は変更しない。

## `/service` — Service App

選択したサービスを体験・実行する利用者画面である。既定は My service。
インストール済みPWAの識別子は維持し、開始URLは `/service?service=my-service` にする。

- front cameraによる上半身認識
- Carry assistantの開始、承諾、積載確認、追従、中断
- 期限付きの監督走行許可
- service状態、人物方向、battery、接続状態
- 通常停止と非常停止

汎用Mission Panel、Simulator詳細、event log、手動joystickは表示しない。独自missionの
選択と試験には`/playground`を使う。これにより、利用者向けservice UIと基盤のdebug UIを
混在させない。

## `/console` — Operator Console

PCで運営・デバッグを行うための画面である。

- Rover fieldと軌跡
- 手動デッドマン・ジョイスティック
- pose、速度、バッテリ
- 操作権、安全状態、イベントログ
- 非常停止

通常は監視に使い、手動操作が必要なときだけ操作権を取得する。

## `/playground` — Playground

最初の体験は[Playground実習](demos/playground-workshop.ja.md)の
`/playground?service=greeting`、`follow`、`receptionist`を使う。挙動と実コードを並べて確認できる。
Simulatorでは仮想入力とmarkerシーン編集、`websocket_rover`では
[実機Playground](demos/hardware-playground.ja.md)のcamera観測とtelemetryを表示する。
実機では挨拶・追従だけを有効にしており、このUIの実機検証は未完了。

実機がない開発時に、service UI、Operator Console、Simulator toolを1画面で確認する
統合表示である。仮想人物、scenario、認識値、Human interaction、汎用Mission Panelを
使った機能開発やdemo確認に利用する。最終的なsmartphone UIの確認には`/service`を使う。

## Control ownership

各ブラウザタブと端末は別のWebSocketクライアントになる。操作権を持てるクライアントは常に1つだけである。

- `/service`がミッションを実行している間、`/console`は監視と非常停止に使う。
- `/console`で手動操作するときは、先に`/service`が操作権を解放する。
- 操作権を持つ画面から別URLへ移動するとWebSocketが切断され、Local Serverがローバーを停止して操作権を解放する。
- 非常停止は操作権を持たない画面からも実行できる。

画面移動は同じタブで行う。実行中のサービスを監視するときは、ConsoleのURLを別タブで開き、操作権は取得しない。
画面を移動しても、実行中の処理や未保存のシーン編集までは引き継がない。

画面の分離は表示と編集範囲を整理するためのものであり、安全制御をブラウザ側へ移すものではない。
