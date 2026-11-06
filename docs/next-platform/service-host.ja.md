# 統合サービスhostと上限付き通信

[English（正本）](service-host.md) · [activity runner](activity-runner.ja.md) · [統合計画](integration-plan.ja.md)

apps/runner-prototype/service-host.ts の runFakeService に、起動、上限付き JSON-lines 通信、
制御契約による受付、activity 実行、終了処理をまとめた。
既存 myService.ts は変更せず、StudentServiceApi を通して実行する。
起動できるのは既存の Python fake port のみで、実機 adapter の選択肢はない。
これまで結合テスト内で行っていた host の仕事を一つの入口にまとめた。

## 実行例

リポジトリの root で実行する。

~~~sh
uv sync --directory apps/server --frozen
APRIS_PYTHON="$PWD/apps/server/.venv/bin/python" node apps/runner-prototype/host-demo.ts
~~~

人物入力、運用者の在席、質問への回答、人の退避確認はすべて合成入力。
fake-only の結果を出力し、正常終了では moving=false、session=null、closed=true となる。
カメラや実際の人物追従のデモではない。

## 実行と学生向けfacade

1. Python を起動して control epoch を取得し、試験用の前方安全確認を明示的に注入する。
2. 運用者を受け付け、初期の recoveryClearance=true を要求して明示復帰し、run を開始する。
   再接続や移動の自動再送はしない。
3. MotionClient と ActivityRunner を作る。運用者の在席確認がある間だけ操作許可を更新し、
   runner の生存更新とは分ける。
4. scope 付き移動・質問・cleanup で学生サービスを実行する。
   サービス例外、timeout、通信断、runner 失敗ではサービスの待機を中断する。
5. 停止証拠を待つ間は host の生存更新を続け、activity 全体を無効化・join した後に closeRun。
   終了要求が失敗したら globalStop を試みる。診断 snapshot を取得し、通信・stdin を閉じて
   子プロセス終了を待ち、必要ならプロセスを終了する。

子プロセスは exit だけでなく close を監視するので、実行ファイルがない場合も終了待ちで固まらない。
正常終了待ち700 msの後に SIGKILL、最終待機は1.5秒とする。
サービス予算は既定5秒、activity cleanup は既存の1秒。いずれも試験用で、実機向けの実測値ではない。
最終 snapshot は診断用の一時点の状態であり、close や stopPending を停止証拠の代わりにしない。

facade は ask／choose／confirm のラベル・発話候補を引き継ぎ、不正・重複した選択肢を拒否する。
confirm／waitForLoaded では Python の受け渡しguardを取得する。
サービスへの回答だけでなく、入力提供側の humanClear=true が別に必要で、
それが確認できて初めて clearHandover を要求する。取消・失敗時はguardを残す。
普通の質問から無条件の stop は発行しない。

waitForPerson は合成人物入力。approachPerson は0.008 mの有限な fake 移動、
followPerson は0.08 mの有限な fake 移動を使い、到着入力で取消・join する。
到着入力より先に移動目標が終わった場合は追従成功とはせず失敗にする。
greetPerson／guideTo は未対応として拒否する。
末尾の荷降ろし案内も、guard 付き受領確認になったわけではない。
サービスのソースは維持したが、認識・追跡・経路移動・音声実行はまだ提供していない。

入力提供側には activity の AbortSignal を渡す。
提供側が取消に応答しなくても、host 自身の待機は中断できる。
学生コードと入力提供側は Node 内で動くため、CPUを占有する任意コードに対する host の応答性には
プロセス隔離が引き続き必要。Python の期限は独立しているが、Python 喪失後の実機停止は未検証。
役割の認証や通常画面の再接続も後続とする。

## 通信の上限と失敗処理

json-line-rpc.ts の JsonLineRpc は、分割・連結された UTF-8 JSON 行と、応答より先に届くイベントを扱う。
上限は1 frame 64 KiB、未完了要求32件、書込待ち128 KiB、イベント購読16件、応答待ち1秒。
容量超過は受付前に拒否する。形式不正、書込停滞、stream error／EOF、timeout では
未完了要求を不確実として失敗させ、新規要求を止める。自動再送queueは持たない。
stderr と発話記録にも上限を置く。これは信頼されたローカル pipe 用で、認証済み network API ではない。

Python 側の入力にも上限を設け、長すぎる行や改行で終わらない frame は接続を閉じる。
残りの断片を別コマンドとして解釈しない。終了時には既存の権限失効・停止処理を通る。
server 内部のすべてのqueueを本番向けに検証したという意味ではない。

サービス全体の試験で、完了後に遅れて届いた更新要求のエラーが次の処理を中断する競合を検出した。
修正後は、Python は終了処理中の更新を受け付けても TTL・停止期限を延ばさない。
MotionClient は、同じ scope・generation の terminal を既に受け取っている場合に限り、
古い更新・取消へのエラーを無視する。他のエラーは失敗のままとし、古い操作で新所有者を動かさない。

## 検証と次の段階

ローカルで Node 137件、Python 99件、厳密な TypeScript、Ruff、host-demo が成功した。
新規試験は frame 境界、要求・書込容量、timeout／EOF、既存サービスの正常・辞退、
退避確認不足でのguard保持、サービス例外、入力無応答、実行ファイル不在、停止証拠欠落、
運用者の離脱、外部取消を含む。更新競合と Python の巨大frame拒否も回帰試験にした。
CI に統合demoと新規テストを組み込んだ。

次は共有 server の操作権・guard 統合（C）。手動操作・既存経路・runner のすべてが
同じ制約を守るようにする。その後、PortFakeAdapter を実際の位置・オドメトリが変化する
Simulator へ置き換える（D）。現行 PWA の起動経路は変更しておらず、今回のhostは
fake backend を使う統合入口であって、公開済みの運用構成ではない。

続く共通runtime境界の実装は[共通runtimeの移動操作権](shared-authority.ja.md)を参照。

続くSimulator接続は[平面Simulatorとの接続](simulator-integration.ja.md)を参照。
