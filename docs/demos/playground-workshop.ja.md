# APRISRC Kit Playgroundの実習ガイド

[English](playground-workshop.md)

サンプルを自分のAPRISRCサービスを作る出発点として使います。この実習はKitの開発手順を
紹介するもので、競技課題や審査基準ではありません。サービスの目的とインタラクションは
自分で設計します。[目的と位置づけ](../positioning.ja.md)を参照してください。

20〜30分で「動かす→1か所変える→同じ条件で比較する」を体験します。
ローバー実機・カメラ・スマホ・マイク・LLM APIキーは不要です。
利用者向けの完成アプリではなく、サービス開発用の画面です。

## 起動する

この公開リポジトリを手元にcloneしてください。アクセス権の申請は不要です。
Node.js/npm、Python 3.12（固定）、uvを用意します。
Windowsでは[PowerShellの起動手順](../windows-setup.ja.md)を使ってください。
以下はmacOS/Linux（Bash・zsh）向けで、リポジトリのルートで実行します。

```bash
npm ci
uv python install 3.12
uv sync --directory apps/server --no-dev
APRIS_ADAPTER=simulator APRIS_DISABLE_HTTPS=1 npm run dev
```

ターミナルを起動したまま、[Person greeting](http://localhost:5173/playground?service=greeting)を開きます。
この設定はSimulatorとHTTPを明示し、証明書があってもPCだけで試せます。
実機やスマホカメラの試験にはこの起動方法を使わないでください。
ポートが使用中なら既存のAPRISサーバーを使うか、停止してから起動します。終了はCtrl-Cです。

## 3つのサービスを動かす

| サンプル | 操作 | 確認する結果 |
| --- | --- | --- |
| Person greeting | Start greeting → On the left | 人の方向を向き、一度挨拶する |
| Follow helper | Follow me → Walk ahead | 仮想の人を追従する。Outside viewで停止する |
| Marker guide | DestinationをEntrance、Test sceneをIn view → Guide me | マーカーに接近し、到着を知らせる |

切替は実行終了後、またはStopを押してから行います。制御権は自動取得します。
Emergency stopは停止を保持します。制御権を持った状態でClear E-stopを押すと解除できます。
音声が出なくても発話内容は画面で確認できます。
コード欄は実際のMissionコードです。強調は進捗報告に対応し、全命令の実行位置ではありません。
This runは判断の記録で、繰り返した移動すべての一覧ではありません。

## 同じ試験条件を作る

座標編集はMVPではMarker guideのみです。

1. 行き先をEntranceかDeskにし、Test sceneのBehind roverを選びます。
2. Guide meを押します。人を検出した後、その場で旋回してマーカーを探し、接近します。
3. 終了後、ローバーのx/yと向き、人とマーカーのx/yを変えられます。
   座標はコース上のm、向きは度で反時計回りが正。0度は+x方向です。
4. Save sceneでこのブラウザ内に配置を1件保存し、Load sceneで編集後・再読込後も復元できます。
   読込だけでは走行しません。行き先の選択は別なので、比較時は同じ行き先を選び直します。
5. Guide meは毎回、選んだ開始条件へ戻します。故障設定は解除しますが、非常停止は解除しません。

Not visibleではマーカーを隠して開始します。前進せず探索し、一周または探索上限で停止して再配置を依頼します。
約1分待ってください。人が視野外の場合はマーカー探索に入らず、人の検出を待ちます。30秒でタイムアウトします。

Marker initially hidden / Path initially blockedは保存される開始条件です。
マップ横のHide marker / Other marker / Path blockedは実行途中の入力で、保存されません。
実行中の座標編集は禁止します。コード変更前にシーンを保存し、変更後に読込して比較します。
挨拶・追従には従来の人の配置ボタンを使います。

## 課題1：人の方を向いて挨拶する

**困りごと：挨拶はするが、人の方を向かない。**

1. Person greetingでMaximum turnを0にし、On the left → Start greetingを実行します。
2. Maximum turnを15にします。再びOn the leftを押して、現在のローバーを基準に人を配置し直し、再実行します。
3. 人の方向への旋回と挨拶を確認します。Greetingの文章も変えて試します。
4. 再読込後も変更を残すには、`apps/pwa/src/config/greetingStarter.ts`を編集します。

```ts
export const greetingStarterSettings = {
  greeting: "Welcome. How can I help you?",
  maxTurnDeg: 15,
  minTurnDeg: 3
};
```

0は意図的な試験設定で、不具合ではありません。画面の設定はファイルを書き換えません。
判断のコードは`apps/pwa/src/missions/challengerStarter.ts`にあり、設定ファイルが既定値を供給します。
編集前に試験を止めます。保存するとViteが画面を更新します。必要なら再読込してください。

**成功条件：** 人を向く動きが変わり、再読込しても新しい挨拶が残ること。
Outside viewでは、いない人に挨拶せず検出を待つこと。

## 課題2：机の前に余裕を残して止まる

**困りごと：受付では机に近づきすぎず、少し離れて止まってほしい。**
試験用マーカーの位置や基盤の速度上限ではなく、サービスの到着方針を変えます。

1. Marker guideでDeskとIn viewを選び、Save scene → Guide meを実行します。
2. 机からどのくらい離れて止まるか確認します。現在は0.45m目標、許容幅0.02mです。
   マップの小さい升目は0.5mで、比較用の目安です。精密な計測器ではありません。
3. 実行を止めて、`apps/pwa/src/missions/mobileReceptionist.ts`の1行だけ変えます。

```ts
const ARRIVAL_DISTANCE_M = 0.65; // Previously 0.45
```

4. 画面更新後、Deskを選び直し、Load scene → Guide meを実行します。
5. 約0.2m手前で止まるはずです。比較中はARRIVAL_TOLERANCE_Mや配置などを変えません。
6. Behind roverでも試し、接近中にマーカーを隠す・通路を塞ぐ試験もします。
   探索が動き、危険条件では停止することを確認します。

**成功条件：** 同じシーンで停止位置が変わり、安全停止は維持されること。
変更を採用しないなら0.45に戻します。恒久的に採用する場合は、旧閾値を前提とするテストも見直します。
テストを通すためだけに検証を削除しないでください。

## 変更する場所

| 変更したいこと | 場所 |
| --- | --- |
| 試験配置・開始時の表示と通路状態 | Test scene、ブラウザ内Save/Load |
| 挨拶文・旋回の範囲 | `apps/pwa/src/config/greetingStarter.ts` |
| 挨拶の判断 | `apps/pwa/src/missions/challengerStarter.ts` |
| 追従の判断・距離プリセット | `apps/pwa/src/missions/comeHere.ts` |
| 探索・接近・到着・案内の発話 | `apps/pwa/src/missions/mobileReceptionist.ts` |
| 恒久的なマーカーID・既定座標 | `apps/pwa/src/config/courseMarkers.ts`と`apps/server/config/course-markers.json` |

シーン編集はSimulatorの配置を変更し、コース既定値のファイルは変更しません。
サービスは公開Mission APIを使います。socket・runtime・firmwareを変更したり、制御権・TTL・速度上限・
前方安全・非常停止を回避したりする必要はありません。
コード変更後、ルートで確認します。

```bash
npm test
npm run typecheck
npm run build
```

新しいサービスを作る場合は[Challenger quickstart](../challenger-quickstart.ja.md)と
[Mission API](../mission-api.md)へ進みます。詳しい操作は[Service playground](service-playground.ja.md)にあります。

試作段階の[実機モード](hardware-playground.ja.md)にはカメラ・実機状態の可視化と、
監督下での挨拶・追従開始があります。この実習は引き続きSimulatorのみを使い、新しい実機UIの走行は未検証です。

## 制限とフィードバック

人・マーカーは幾何計算による観測で、カメラ画像認識ではありません。
マーカー案内の人は開始のきっかけだけで、その場に固定されます。同行確認・経路計画・一般的な障害物回避・
実機マーカー案内の検証はまだありません。Simulatorでの成功は実機の動作保証ではありません。
配置編集は数値入力で、マップ上のドラッグではありません。

動かなければLocal Server online、Simulator使用、他の制御者、非常停止を順に確認します。
マーカー探索の開始には視野内の人も必要です。長い接近で回数上限に達したら、上限を削除せず配置を近づけます。
再読込後はLoad sceneで条件を戻してください。

感想にはサンプルと行き先、座標とプリセット、変更した1か所、期待と実際、表示された状態やスクリーンショットを添えます。
特に「変更するコードを自分で見つけられたか」「なぜ動きが変わったか説明できるか」を教えてください。
