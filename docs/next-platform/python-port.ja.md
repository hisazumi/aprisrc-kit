# runnerとPython Local Server runtimeの接続

[English](python-port.md) · [前段階の実験](process-experiment.ja.md)

状態：fake専用の独立した接続実験、2026-11-05。
既存myServiceとNode workerを変更せず、別Pythonプロセスの既存RoverRuntimeへ接続した。
公開メソッドadd_client/handle_text/remove_clientを通して、登録・制御権取得・移動・
キャンセル・切断時停止を行う。サービスから直接モータ指令を送らない。
既存runtime/adapterのインターフェースは変更していない。FastAPIの公開APIへの組み込みは未実施。

## 実行

既存のuv手順でserver環境を準備する。リポジトリのルートから、POSIX shellで実行する例：

```sh
uv sync --directory apps/server --frozen
APRIS_PYTHON="$PWD/apps/server/.venv/bin/python" node apps/runner-prototype/python-demo.ts
APRIS_PYTHON="$PWD/apps/server/.venv/bin/python" node --test apps/runner-prototype/*.test.ts
uv run --directory apps/server pytest tests/test_runner_port_experiment.py tests/test_runtime.py
```

APRIS_PYTHONはインタープリタを指定するだけで、adapter選択ではない。Python入口は
必ずPortFakeAdapterを生成し、実機選択を持たない。変数未設定ならNodeのテストは
Python接続7件をskipし、従来のNodeだけの試作を維持する。demoを直接実行した場合の
インタープリタ既定値はpython3。

ローカルの接続プログラムが既存service-worker.tsとapris_server.runner_port_experimentを
起動し、要求・応答を中継する。移動の受付とwatchdogはPythonにある。人物・質問は合成入力。
前段階のTypeScript Gatewayは同時には動かさず、安全判断を二重化しない。

## 接続契約

継承したローカルpipe上の改行区切りJSON。要求はid/actionとsession/token、
応答はkind=replyとid/ok/value/error。running/terminal/revokedイベントは非同期に届く。
信頼された試験用接続であり、ネットワーク認証を規定しない。要求IDは応答の照合用で、
永続的な重複排除キーではない。

| 要求 | 契約 |
| --- | --- |
| admit | ランダムなsessionを作成しruntimeへ登録・制御権取得。競合・禁止中は拒否 |
| move(session, duration) | fakeの有界操作を1つ受け付け、session/generationのtokenを返す。その後runtimeが拒否する場合もある |
| heartbeat(session, token?) | 有効sessionのleaseを更新。一致するtokenだけが操作の認可TTLも更新 |
| stop(session, token) | tokenを検証後runtime経由でcancel。別の停止確認を経た終了通知を待つ |
| hold / clear | 停止中の受け渡しに移動禁止を保持。解除にはconfirmed=trueが必要 |
| revoke | runtimeの切断・キャンセルより先にsessionを失効。ローカル操作員の全停止経路 |
| recover | session・移動がない状態で、fake静止と人の離脱を明示的に確認 |
| snapshot | fake対象、session、runtime所有者、操作、禁止、合成動作の状態 |
| fixture | 試験専用の前方状態と停止確認の遅延・欠落。学生向けAPIには公開しない |

受付応答は移動開始を意味しない。runtimeのstartedからrunningを発行する。
終了状態はcompleted/cancelled/failed/interrupted/stop-unconfirmed。
tokenで操作を照合する。到着の停止確認待ちに失効すればcompletedではなくinterruptedにする。
停止確認はfake-stopの証拠であり、runtimeの完了やstop呼び出しの復帰だけでは代用しない。
期限後の確認でstop-unconfirmedを自動解除しない。

試作のdurationを、速度0.1 m/s・距離duration × 0.1 mのMoveCommandへ変換する。
runtimeのスキーマ、所有権、E-stop、接続、pose能力、前方CLEARの判定を通す。
fakeは既存DeviceBoundedMotionAdapterを実装し、受け取ったgoalを記録する。
合成時間を待ち、stopで合成動作を無効化し、別途停止確認を返す。
追跡や実際の移動・オドメトリ精度・物理挙動のシミュレーションではない。

正常試行では接続プログラムが合成CLEARを明示的に投入する。投入しなければ既存runtimeが
前進を拒否する。移動要求から暗黙にCLEARを作らない。荷物積載の合成回答には人の離脱確認も
含める。荷下ろしは既存サービスの最後の発話のままであり、S2全体の受け渡し実装ではない。

## 期限と障害時の扱い

Python側はすべてホスト単調時計：runner lease 400 ms、操作認可TTL 250 ms、
固定の進捗期限1.2秒、停止確認期限200 ms。Nodeは40 ms間隔で更新し、Pythonは10 ms間隔で
確認する。実験値であり、実機で測定した安全値や実時間保証ではない。
認可TTLは追加の制限で、既存runtime・機体の指令TTLを置き換えない。
heartbeatだけでは操作TTLを延長できず、token更新が続いても固定進捗期限は延長できない。
Python側の仮想pause/resetは未実装・未公開。前段階のTypeScriptの検証結果は流用しない。

期限超過やrunnerのIPC切断では、session失効後にruntimeのclientを削除し、操作を終了させる。
停止未確認なら禁止を保持し、明示的なfake復旧まで新しい受付を拒否する。
受け渡しの禁止はsession喪失後も保持する。ただし今回はこのportだけを外部へ公開している。
共有FastAPI serverの任意の外部clientを含む禁止には未統合であり、その場合の全体的な移動禁止を
保証するには、共有server境界に強制処理を入れる必要がある。

合成入力は信頼された試験用であり、UI再接続、操作員session、権限モデルではない。
Pythonプロセス自体の停止と下流watchdogは未検証。この実験モジュールへの実機adapter接続は行わない。

## 検証結果と次の段階

レビュー修正後はNode 33件（Python接続7件を含む）、Python 27件（port 13件＋既存runtime回帰14件）、
strict型チェック、Ruff、Python接続demoが成功した。正常／辞退、runner強制終了・CPU停止・
IPC切断、停止確認遅延・欠落、CLEARなし前進拒否、E-stop拒否、古いtoken、受け渡し禁止保持、
到着と失効の競合、TTLと進捗期限を確認した。CIにもserverのlockを使うPython検証jobを追加した。

次は実際のserver APIへ組み込む前に、この接続契約をレビューする。
mailbox/activityと操作所有権を1つのrunnerへ統合し、共有serverでの禁止・操作員leaseと、
adapter別の停止確認を定める。その後、poseを持つ実際のsimulator adapterで移動を接続する。
実機、観測消失、UI復旧、認証、永続ジョブ、配布環境は引き続き後段。
既存PWA/serverの通常起動経路は変更していない。

## レビュー指摘への回帰テストと修正（2026-11-06）

実装を変更する前に回帰テストを追加し、修正前の版でPython 5件・Node 2件が
指摘どおりに失敗することを確認した。watchdogより先に届く期限切れ更新、
変換後の入力検証、停止・切断I/Oの停止、Python起動失敗、受付と終了通知の一括受信を扱う。
修正中には既存の停止確認遅延テストが早すぎる終了処理を検出したため、
その条件も失敗する単体テストにしてから修正した。

| 境界条件 | 修正後の動作 | 回帰テスト |
| --- | --- | --- |
| 遅れたheartbeat | 要求処理の入口でlease/TTL/進捗期限を検証し、更新より先に失効 | watchdogに実行を渡さずportの時計を進め、更新を試す |
| 変換後の移動入力 | token・操作を確保する前にSI単位のMoveCommandを検証 | duration=1e-12を即時拒否し、TTL切れへ化けない |
| 停止・切断I/Oが戻らない | I/Oを状態ロック外へ移し、受付からI/Oと証拠待ちを含めて200 msで期限判定 | adapter.stopを待機させたまま、snapshotの応答と停止未確認の終了通知を確認 |
| 停止確認だけが遅れる | cancel I/Oの復帰後も、同じ期限の残り時間で証拠を待つ | 100 ms後の証拠でcancelledとなる |
| Python起動失敗 | spawn失敗時にも届くcloseを待ち、両子プロセスの後始末にも上限を設ける | 存在しない実行ファイルで速やかにENOENTを返す |
| 終了通知が受付より先に届く | 受付待ちの間だけ、session内の終了通知を上限付きで保持しgenerationと照合 | 受付とfailed通知を1回のstdout書込で送り、timeoutに化けない |

stop/revokeの応答は受付であり、I/O完了ではない。snapshot.pendingIoで残るI/Oを示す。
古いI/Oが残る間は新しい受付と復旧を拒否し、遅い後始末が次の所有者へ干渉しないようにする。
期限超過では終了通知を一度だけ返し、遅れて停止確認が届いても禁止を自動解除しない。
終了処理の待ち時間にも上限を設けた。ただしタスクキャンセル自体を無視するバックエンドは、
所有するプロセス側で終了させる必要がある。実時間保証・実機の停止保証ではない。

Pythonの回帰テストはtests/test_runner_port_experiment.py、Node側は
apps/runner-prototype/review-regressions.test.tsにあり、既存CIのテスト対象に含まれる。
起動失敗・一括受信のNodeテストはPython導入不要。一括受信の実行ファイルfixtureは
POSIXのshebangを使うためWindowsでは明示的にskipし、Linux CIで実行する。
