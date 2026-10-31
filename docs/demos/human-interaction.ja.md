[English](human-interaction.md)

# 人とのインタラクション Simulatorデモ

Status: **実装済みの参照デモ**（2026-09-25確認）

この文書は当初の計画を兼ねる実行ガイドです。将来の優先順位は
[Development roadmap](../roadmap.ja.md)で管理します。

このデモは、APRISの公開された安全境界とMission APIを使い、人についていくサービスのMVPを検証します。Simulator上の仮想人物を、スマートフォンのカメラと同じ正規化済み人物観測へ変換してMissionへ渡します。

## 実行

```bash
npm run dev
```

ローカルルールではなくLLMによる意図解釈を使う場合は、サーバ側にAPIキーを設定して同じ構成を起動します。キーはPWAへ送信されません。

```bash
OPENAI_API_KEY='<development key>' npm run dev
```

`http://localhost:5173/lab` を開き、次の順に操作します。

1. **Acquire control**で操作権を取得します。
2. **Virtual person**で`Left`、`Ahead`、`Right`のいずれかを選びます。
3. シーンを開始します。明示的にシミュレーションされた領域について、新鮮で正常な`CLEAR`状態も設定されます。
4. **Human interaction**の**Come here**を押します。
5. Rover表示で移動を確認しながら、`ALIGNING`、`APPROACHING`、`ARRIVED`への遷移を確認します。
6. **Wait here**または**Stop**でサービスを停止できます。

継続追従では**Follow me**を押し、Virtual personパネルで**Start walking**を押します。人物は12秒間の緩やかなS字経路を歩きます。ローバーは人物を中央に保つよう旋回し、人物が離れると前進し、およそ1 mの距離で待機します。**Pause walking**を押すと人物がその場に止まり、距離維持を確認できます。

ブラウザ音声は、応答と安全メッセージに英語のvoiceを使用します。

## 自然言語入力

**Natural language**は、英語または日本語の依頼を許可済みのサービス意図へ変換します。アプリケーション意図、説明、例、ローカルfallbackキーワード、応答はMission定義と同じ場所にあります。PWAがLocal Serverへ送れるのは登録済みtriggerだけです。

`stop`、`wait_here`、`report_status`、`clarify`はプラットフォームが所有します。停止表現はモデル呼び出しより先にローカルで解決します。`APRIS_ASSISTANT_PROVIDER`で`rules`、`openai`、`gemini`を選べます。キー・モデル・従来互換の既定値は[provider設定](../assistant-providers.ja.md)を参照してください。rulesにはAPIキーは不要です。モデル出力から速度、モーター、距離、角度、Rover protocol命令を生成することはできません。

ブラウザが音声認識に対応している場合、**Speak**は日本語の発話を一つ取得し、同じ意図変換境界へ渡します。これはデモ用入力adapterです。本番では、明示的に選定・評価した文字起こしproviderを使いつつ、許可済み意図の契約を維持します。

## 仮想カメラと見失い試験

シーンの実行中、**Camera preview**はLab専用の仮想カメラへ切り替わります。人物silhouetteと検出枠はMissionへ渡す正規化済み観測から描画されるため、水平位置、見かけの大きさ、距離、bearingが追跡入力と一致します。仮想シーンを停止すると、通常のスマートフォンまたは録画映像の操作へ戻ります。

見失い処理を確認するには、**Come here**で走行中に**Stop scene**を押します。人物観測subscriptionが通常停止を直ちに送信し、bounded motionをcancelしてサービスを`LOST`へ遷移させます。観測の期限切れも同じ停止経路を使います。

## モデル値

- 仮想人物の初期距離: 約1.38 m
- 水平視野角: 70度
- 1回のbounded turn: 最大12度
- 1回の接近: 0.05 m/sで0.08 m
- 到着閾値: 人物幅がcamera frameの36%以上
- スマートフォン上半身検出の到着閾値: frame幅の65%以上
- 人物観測間隔: 450 ms
- 観測期限切れ: 1.8 s
- Simulator追従hysteresis: 31%未満で再開、36%で待機
- 上半身追従hysteresis: 52%未満で再開、65%で待機
- 追従step: 0.10 m、指定速度0.15 m/s。短距離の減速制御で実際の速度は低くなることがあります。

インタラクション実装が使うのは`ServiceRover.onPerson()`、`move()`、`turn()`、`stop()`と、任意の権威ある前方障害snapshotだけです。Simulator固有のmotion APIは使いません。そのため、仮想観測をbrowser camera観測へ交換しても、サービス状態機械は変わりません。

## 監視付き実機pilot

PC・iPhoneの準備、開始・停止、非常停止からの復旧は[iron-X人追従](../hardware/ironx-follow.ja.md)を参照してください。PCの実際のHTTPSポートを開き、**Start camera**で認識を確認し、周囲を確認してから**Start service and allow movement**を押します。
Carry helperでは接近・追従中だけ短期限の`path_clearance` heartbeatを送信し、30秒ごとの押し直しは不要です。heartbeatが途絶えるとサーバーは1秒以内にclearanceを失効させます。通信断、操作権喪失、非常停止、画面非表示で許可を取り消し、中断後は明示的に再開します。

Consoleの30秒確認は手動運転用として残ります。いずれも車載センサーによる障害物回避ではありません。browser clientは障害物状態、source、health、confidence、timestampを任意に設定できません。無人運用と一般的な衝突回避は対象外です。

## 確認結果

最初のbrowser試験では人物を左12.5度、距離1.38 mに配置しました。ローバーは向きを合わせ、約0.45 m接近し、人物が距離0.92 m、角度2.8度、frame幅37%の時点で`ARRIVED`になりました。別の見失い試験では実行中の旋回を`person lost`でcancelし、並進・角速度がゼロになりました。

最初の実機契約試験では、motion命令なしでWebSocket Rover Adapterを使用しました。operator確認で`CLEAR/manual/healthy`となり、解放すると`UNKNOWN/manual/unavailable`へ戻りました。接続したUGV02の並進・角速度は全期間ゼロでした。

その後の床上試験では、車載スマートフォンの上半身観測と時間制限付きの**Allow movement**を使用しました。屋内向け追従閾値の調整後、UGV02は人物へ向きを変え、監視付きデモとして十分滑らかに追従しました。応答がやや遅いという定性的な観測は残っています。これは障害物sensorや停止距離の測定による認定を置き換えるものではありません。
