# Autonomous carry service MVP

[English](autonomous-carry-service.md)

Status: **Implemented reference service** (verified 2026-09-25)

この文書は実装済みCarry assistantの振る舞いと試験scenarioを記録する。未実装項目だけを
長期計画として扱い、現在の優先順位は[Development roadmap](../roadmap.md)で管理する。

## Purpose

スマートフォンをローバー前面に載せ、カメラ、音声対話、利用者向け表示を担当させる。ローバーは人物を安定して認識すると自分から荷物運びを提案し、承諾後に既存の`Carry helper`ミッションで人物を追従する。

高度な自律航法ではなく、サービスを自分から開始し、安全に中断し、次の利用者を待つ一連の振る舞いをMVPの自律性とする。

## User flow

```text
PAUSED
  -> READY
  -> NOTICING
  -> APPROACHING
  -> OFFERING HELP
  -> LOADING
  -> FOLLOWING
  -> ARRIVED
  -> READY
```

- `Start service`で操作権を取得し、人物待機を開始する。
- 同じ人物を3回連続で観測した場合だけ支援を提案する。
- 安定検出後は低速で人物に接近し、会話距離で停止してから支援を提案する。
- 承諾はボタン、文字入力、または日本語音声入力で受け付ける。
- 承諾後は停止したまま荷物の積載を待ち、積載確認後に`carryHelperMission`を実行する。
- `We have arrived`、停止発話、通常停止、非常停止で追従を中断する。
- 辞退または無応答の人物には、フレームから退出するまで再提案しない。
- 人物を見失った場合は停止し、自動で別の対象へ乗り換えない。

## Screen ownership

- `/app`: 利用者向けService画面。状態、人物方向、対話、停止、カメラ起動を表示する。
- `/lab`: 仮想人物、再現シナリオ、認識値、同じService画面を表示する。
- `/console`: 手動運転、安全状態、軌跡、運用監視を表示する。

スマホのService画面ではフロントカメラを既定にし、`Start vision`でカメラと人物認識を同時に開始する。映像は端末内で処理し、正規化した観測だけをLocal Serverへ送る。

## Scenario matrix

| Situation | Expected behavior | Automated coverage |
| --- | --- | --- |
| 人物がフレーム外にいる | `READY`のまま移動しない | reducer test |
| 人物がフレームへ入る | 3回の安定観測後に提案する | reducer test + `service-person-enters-frame` |
| 通行人が短時間だけ映る | `NOTICING`から`READY`へ戻り、提案しない | reducer test + `service-passerby` |
| 別の人物へ切り替わる | 安定観測カウントを1からやり直す | reducer test |
| 利用者が辞退する | 再提案せず、退出を待つ | reducer test + component test |
| 12秒間返答がない | 提案を取り下げ、退出を待つ | reducer test |
| 人物を安定検出する | 低速接近し、会話距離で停止して提案する | reducer test + component test + Lab test |
| 利用者が承諾する | 停止したまま荷物の積載確認を待つ | reducer test + component test |
| 荷物の積載を確認する | 既存の追従ミッションを開始する | reducer test + component test + Lab test |
| 追従中に人物を見失う | 停止して`TARGET LOST`を表示する | reducer test + component test |
| 追従中に停止される | 進行中ミッションをabortし、通常停止する | reducer test + component test |
| 非常停止が有効になる | ミッションをabortし、再開を禁止する | component behavior |
| 到着操作を行う | 停止して`ARRIVED`を表示する | component test + Lab test |
| Serviceを終了する | 停止後に操作権を解放する | component test + Lab test |

## Reproducible Lab test

1. `/lab`を開き、Carry assistantの`Start service`を押す。
2. `Service: passerby leaves quickly`を実行し、`NOTICING`から`READY`へ戻ることを確認する。
3. `Service: person enters the frame`を実行し、`APPROACHING`、停止、`OFFERING HELP`の順に遷移することを確認する。
4. `Yes, help me`を押し、`LOADING`の間は停止していることを確認する。
5. Virtual Personを正面に置いて歩行を開始し、`Items are loaded`を押す。
6. `FOLLOWING`表示とSimulator上の前進を確認する。
7. `We have arrived`を押し、速度が0になり`ARRIVED`へ遷移することを確認する。
8. `End service`を押し、操作権が解放されることを確認する。

## MVP limitations

- 一度に一人だけを対象とし、人物の再識別は`personId`に依存する。
- 人物が荷物を持っているかどうかは認識しない。必ず提案と承諾を挟む。
- 待機位置への自動復帰、経路計画、障害物回避はまだ行わない。
- ブラウザのカメラと音声認識にはHTTPSと利用者の権限許可が必要である。人物認識はMediaPipe Pose Landmarker Liteで左右の肩を追跡し、足元や腰がフレーム外でも上半身観測を生成する。
- 初回認識時はversion固定した配布元からPoseモデルとWASMを取得するため、オフライン運用前に自己ホスト化またはキャッシュ方針を決める。
- 実機ではカメラ画角、観測周期、検知信頼度、停止距離を再調整する。
