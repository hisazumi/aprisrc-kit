# 平面Simulatorとの接続

[English（正本）](simulator-integration.md) · [共通操作権](shared-authority.ja.md) · [統合計画](integration-plan.ja.md)

統合計画Dの最小構成を実装した。Nodeのサービスhostから、共通のPython portとruntimeの
移動禁止を通して、既存の平面Simulatorを実行できる。
時間待ちで完了するfakeとは異なり、位置・車輪/IMUオドメトリが実際に変化する。

## 実行

リポジトリのrootで実行する。

```sh
uv sync --directory apps/server --frozen
APRIS_PYTHON="$PWD/apps/server/.venv/bin/python" node apps/runner-prototype/simulator-demo.ts
```

結果には `snapshot.backend`、`snapshot.state.pose`、速度、位置推定品質が含まれる。
正常終了時には前進した位置が残り、速度がゼロとなり、サービスと子プロセスが終了する。
backend単独の起動は以下。

```sh
uv run --directory apps/server python -m apris_server.runner_port_experiment --backend simulator
```

上限付きJSON-linesの契約は共通。既定は `--backend fake` のまま。
既存の関数名 `runFakeService` は互換性のため維持し、
`{ backend: 'simulator' }` で平面Simulatorを選択する。
選べるのはこの2種類のみで、実機adapterは読み込めない。
通信上のrobot IDは互換性のため `fake-only` のままなので、backendの識別には
`snapshot.backend` を使う。

## 移動と停止証拠

`PortSimulatorAdapter` は既存の `DifferentialDriveSimulator` を拡張し、
機体側の有限移動インターフェースは実装しない。このためruntimeの既存の
オドメトリフィードバック経路で移動・旋回の到達を判定する。制御器は追加していない。
Simulatorは50 Hz、runtimeのフィードバックは既定20 Hz。
既存の許容誤差は移動1.5 cm、旋回1.5度。
fake版の接近目標0.8 cmでは最初から許容誤差内になるため、Simulator版の合成接近目標は
4 cmとした。fake版の動作は変更していない。

Simulatorのstopは、lock内で最後の区間を積分し、速度をゼロにする。
その完了後にのみシミュレーション上の停止証拠を出す。新しいdriveでは処理を待つ前に
古い証拠を消す。未完了処理と共通の移動禁止の確認も引き続き適用する。
証拠のkindは `simulated` で、epochにbackend名を含める。物理的な停止証拠ではない。

## 検証

Pythonで7ケースを追加。前進・後退・左右旋回、取消、command TTL切れ、
前方状態UNKNOWNでの拒否と受け渡しguardによる新しい手動所有者の移動禁止を確認した。
実際のオドメトリ変位に加え、停止後に位置が変化しないことも検査する。
Nodeでは既存の学生サービスを子プロセスhost経由で実行し、変位・速度ゼロ・終了を確認する。

ローカルでは最後の追加ケース前にserver全392件が成功し、その後最終版のSimulator試験7件が成功。
Node全138件、厳密なTypeScript、Ruff、Simulatorデモも成功した。
CIにも新規ファイルとデモを追加した。これらはローカル検証の結果であり、CI実行結果ではない。

## 範囲と残課題

人物認識、運用者の在席、回答、前方CLEARは合成入力のまま。
`approachPerson` は固定距離の移動、`followPerson` は取消可能な有限目標であり、
認識結果に基づく追跡ではない。マップ・衝突形状・Godot・MuJoCo・箱庭はまだ接続していない。
既存Simulatorは理想的な平面運動モデルであり、encoder/IMU故障、古い・雑音を含む観測、
コマンド遅延、プロセス喪失は別途検証が必要。
fake専用の停止証拠遅延の注入はSimulatorでは明示的に拒否する。

lease、進捗・停止期限は既存の試験値を維持している。進捗期限は1.2秒なので、
長い目標は進んでいても中断される。期限の方針、観測品質による移動制限、故障シナリオは
明示的な残課題とする。計画上の次段階は、guard・復帰状態を含む最小の運用UI（E）。
実機の有効化は別途扱う。
