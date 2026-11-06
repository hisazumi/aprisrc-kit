# サービスの再現シナリオと実行記録

[English（正本）](service-scenarios.md) · [コンソール運用](managed-service.ja.md)

手動で確認した流れを、入力と期待結果のJSON、および実プロセスで動く実行器に整理した。
入力ファイルは `apps/server/scenarios/runner/service-flows.json`。
既存の `myService` と運用APIを使い、シナリオごとに専用のPython Simulatorと管理されたNodeを起動する。
空いているloopback portを割り当て、現在利用中のコンソールや実機には接続しない。

## シナリオ

| ID | 合成入力・操作 | 期待結果 |
| --- | --- | --- |
| normal | 人物検出→利用承諾→積載回答と運用者の退避確認→到着回答を1.8秒遅延 | 正常終了。移動終了後は停止して回答を待つ |
| decline | 人物検出→利用を辞退 | 正常終了。積載・追従には進まない |
| operator-disconnect | 積載guard取得後に運用者のheartbeatと合成前方観測を停止 | 運用者lease失効、サービス中断、guardと移動禁止を保持 |
| service-reconnect | 利用質問中にサービス画面のviewを更新し、古い画面からの回答を送る | 古い回答を拒否。同じrunのまま新しい画面で回答し正常終了 |

各ケースで最終速度ゼロ、run終了、未完了I/Oなし、想定したguard状態を検査する。
最終x位置の許容区間、質問数、最後の案内文も期待値に含める。
再接続ではrun epochが変わらないこと、遅延到着では停止後の位置が変わらないことも確認する。
「辞退」は業務上の正常な分岐として正常終了を期待する。

## 実行

リポジトリのrootで実行する。NodeとPythonの依存環境は従来と同じ。

```sh
uv sync --directory apps/server --frozen
APRIS_PYTHON="$PWD/apps/server/.venv/bin/python" \
  node apps/runner-prototype/scenario-demo.ts /tmp/aprisrc-scenario-traces
```

4ケースのPASS／FAILを表示し、指定ディレクトリにケースIDごとのJSONを保存する。
一件でも失敗したら終了コードは非ゼロ。同じ出力先では前回の同名ケースを置き換える。
通常のテストとして実行する場合は以下。

```sh
APRIS_PYTHON="$PWD/apps/server/.venv/bin/python" \
APRIS_SCENARIO_TRACE_DIR=/tmp/aprisrc-scenario-traces \
  node --test apps/runner-prototype/service-scenarios.test.ts
```

実行記録にはシナリオと期待値、開始日時、相対経過時間、質問・回答、退避確認、
画面再接続、最後のサービス結果・位置・速度・guard・移動イベントを含める。
失敗時も、取得可能ならその時点の状態を残す。tokenや認証headerは記録しない。
入力は最大32ケース、記録はケースごとに最大256項目。未知の操作、重複ID、不正な値、
パスとして使えないIDを起動前に拒否する。

これは**シナリオ入力を新しい環境へ適用する実行器**であり、記録済みモータ命令の再送器ではない。
traceに含まれる過去のoperationやgenerationを使って移動を再実行する機能は設けない。
時刻・UUID・実測位置は実行ごとに変わり、同じ入力に対する期待条件の一致を検証する。

## 検証と範囲

ローカルで4シナリオすべてが成功。入力検証を含め、Node全153件とTypeScriptが成功した。
CIのPython接続jobでもシナリオを実行し、成否にかかわらず実行記録をartifactとして14日保存する設定を追加。
これはローカルで確認した結果であり、CI成功の報告ではない。

今回の通信断は運用者の更新を止めるアプリケーション層の模擬であり、OSのネットワーク遮断ではない。
画面再接続はview／回答APIの再接続で、ブラウザの表示やtimer抑制の再現ではない。
Node強制終了、二重起動、古い停止要求などは既存の結合テストで引き続き確認する。
実機・実カメラ・無線断・プロセス停止中の物理挙動は範囲外。
これを基準ケースとして、次に地図・位置決めや認識providerの入力を追加できる。
