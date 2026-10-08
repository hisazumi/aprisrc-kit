[English](mobile-receptionist.md)

# Mobile Receptionistデモ

Status: **共通Service Appへ実装済み、監督付きUGV02 walkthrough待ち**

初めてのPC体験は[Playground実習](playground-workshop.ja.md)を使う。
この文書は別のService App経路を説明する。実機marker接近は未検証で、実機Playgroundでは
意図的に無効にしている。その開始制限を迂回するためにこの経路を使わない。

このサービスは、見えている来訪者へ挨拶し、allowlist済みの目的地を受け取り、設定された
destination markerを探してbounded stepで接近し、到着を知らせる。公開Mission APIだけで
複数の入力を組み合わせる例である。

## Service Appで決定的デモを実行する

```bash
npm run dev
```

`http://localhost:5173/app?service=receptionist`を開き、次の順に操作する。

1. statusが**Simulator connected**であることを確認する。
2. **Run simulated service**を押す。アプリが操作権取得、Mission開始、決定的scenario開始を
   この順序で行う。
3. 来訪者への挨拶、Kitchen markerの無視、Entrance marker 1への整列、bounded stepでの接近、
   到着停止を確認する。
4. アプリに**Destination reached**と表示され、Operator Consoleでrover速度がゼロであることを
   確認する。

Service Appが、必要なMission開始後のscenario起動を行う。scenarioは、明示的にsimulationされた
領域について新鮮な前方`CLEAR`状態も設定する。`/lab`は個々のeventやfaultの調査用に残すが、
別のservice applicationではない。

同じmissionは**Human interaction**の**Guide me**、または`Guide me to the entrance`のような
依頼からも開始できる。自然言語入力では`desk`、`kitchen`、`entrance`を指定できる。
mission selectorから開始した場合は`entrance`を既定値にする。

## Service boundary

missionが使うのは次だけである。

- `onPerson()`と`onMarker()`の観測
- `turn()`と`move()`のbounded motion
- 到着時とすべてのunsafe exitでの`stop()`
- 来訪者へのfeedbackを行う`say()`
- read-onlyな権威ある前方障害snapshot

Simulator操作、wheel velocity、command TTL、Rover protocolにはアクセスしない。別marker IDは
無視する。目的地markerがlostまたはstaleになるとactive motionを停止する。前方移動は権威ある
状態が`CLEAR`の間だけ行い、`BLOCKED`と`UNKNOWN`ではどちらも停止する。
到着距離は0.45 mとし、移動の完了許容差より小さい指示を繰り返さないよう0.02 mの許容幅を設ける。

## 目的地を設定する

参加者向けmarker labelとdestination keyは`apps/pwa/src/config/courseMarkers.ts`、server側の
pose補正に使うcourse poseは`apps/server/config/course-markers.json`にある。

参照設定は次のとおりである。

| Destination | Marker ID |
|---|---:|
| Entrance | 1 |
| Desk | 2 |
| Kitchen | 3 |

IDは重複させず、二つのファイルを一緒に更新する。service codeはdestination keyを選ぶだけで、
物理座標をhard-codeしない。

A4印刷用マーカーとして、[Entrance](../../output/pdf/apris-marker-1-entrance-a4.pdf)と
[Desk](../../output/pdf/apris-marker-2-desk-a4.pdf)を用意している。**100% / 実際のサイズ**で
印刷する。黒いQR領域は幅160 mmである。**用紙に合わせる**は使用せず、白い余白を隠さない
よう用紙全体を平らに垂直設置する。

## 同じアプリをUGV02で実行する

Local Serverを`APRIS_ADAPTER=websocket_rover`で起動し、車載smartphoneで同じ
`/app?service=receptionist`を開く。**Start receptionist**を押すと、まずfront cameraで来訪者を
確認し、目的地QR markerを探す段階でrear cameraを要求する。前進には
**Allow movement for 30 s**が必要で、取消または期限切れになると権威ある前方状態は`UNKNOWN`へ戻る。

Simulator scenarioは決定的な入力harnessであり、物理navigationそのものではない。床上試験の前に、
車輪を浮かせてmarker 1を確認し、その後に短い監督付きapproachを行う。印刷marker size、camera
range、停止距離、course layoutは実機で確認する変数として残る。
