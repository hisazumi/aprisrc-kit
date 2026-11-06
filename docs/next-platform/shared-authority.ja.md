# 共通runtimeの移動操作権

[English（正本）](shared-authority.md) · [サービスhost](service-host.ja.md) · [統合計画](integration-plan.ja.md)

統合計画Cのruntime境界を実装した。`RoverRuntime` が移動禁止の状態を持ち、
手動・既存コマンドと試作runner portが共有する。既存の所有者確認、速度上限、TTL、
E-stopの確認も引き続き適用する。

## 動作

- runnerの受け渡しguard・移動禁止は、所有者が変わっても手動とrunner双方の
  drive／move／turnを禁止する。stopとE-stopは実行できる。
- 禁止理由ごとに内部tokenを持つ。一つを解除しても別の禁止理由は消えず、
  E-stopの解除でも受け渡しguardは消えない。
- 非同期処理の前にinterlockのepochを取得する。禁止の設定・解除でepochが変わるため、
  解除後に古い待機中の要求が移動を発行することを防ぐ。
  このepochは通信のconnection epochや操作のgenerationとは別物。
- 受け渡しguardの取得時には、既存のfake停止証拠に加え、adapterへの未完了の移動処理、
  実行中の移動task、有効なcommand deadlineがないことを確認する。
- runnerのcleanupだけでなく、既存経路の停止、操作権解放、切断、E-stop、operator-stop、
  drive失敗後の停止処理も、停止I/Oが完了するまで移動を禁止する。
  途中で新しい所有者が操作権を取得しても、その間は移動できない。
- `status.control.motion_interlock` に禁止理由・epoch・未完了処理数を出す。
  内部tokenは公開しない。

`RunnerPortExperiment(runtime=...)` で、起動済みruntimeを共有できる。
portを閉じても共有runtimeや別の手動clientは閉じない。
注入できるadapterは厳密に `PortFakeAdapter` のみで、実機adapterは有効化していない。
既定の子プロセスhostは、従来どおり専用のfake runtimeを起動する。

## 検証

新規回帰試験は9件。受け渡し中の手動drive／move／turn、独立した禁止理由、
禁止・解除をまたぐ遅延driveと有限turn、adapter処理中のguard取得拒否、
共有runtimeの寿命、runner切断と既存client切断それぞれの停止I/O待ち、
未認定adapterの拒否を確認した。
切断試験では、古い所有者の停止完了前に新しい所有者が動かせる不具合を再現して修正した。

ローカルでPython server全386件、Node runner全137件、厳密なTypeScript、Ruffが成功。
CIもserver全テストを実行するように変更した。この件数はローカル検証の結果であり、
CIの成功を確認したという意味ではない。

## 制約と次の段階

interlockは新規の移動発行を防ぐ。設定自体が停止命令や物理的な停止証拠になるわけではなく、
既に発行した移動には取消・停止と証拠確認が必要。一つのevent loop内で使う仕組みで、
プロセス間mutexではない。

認証済みrunner endpoint、復帰UI、guardの永続化はまだ追加していない。
共有portを閉じても、保持中のguardは同じruntimeに残る。
交換後のportからそのguardを運用者が回復する手順は未実装。
既存経路の停止失敗は従来の処理を引き継いでおり、実機の停止失敗時の方針まで
今回新たに検証したわけではない。プロセス再起動・実機については別途設計と検証が必要。

次はDとして、実際に位置・オドメトリが変化するSimulatorを同じ境界につなぐ。
現在のfake adapterは有限操作の所要時間を模擬するもので、物理的な移動の検証ではない。
