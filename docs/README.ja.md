# Documentation index

[English](README.md)

APRISRC Kitの資料を、読む人と目的で四層に分ける。初めて使う場合は
**Start here**だけでよい。実装済みの事実は[Platform status](platform-status.ja.md)、今後の
優先順位は[Development roadmap](roadmap.ja.md)、起動・復旧方法は
[Operations runbook](operations/runbook.md)を正本とする。

## Start here

まず[参加者quickstart](challenger-quickstart.ja.md)でMy serviceを試し、`missions/myService.ts`を編集する。低水準行動の追加は[行動追加ガイド](adding-actions.ja.md)を参照。

WebのチャットやAIを使う場合は[AIを使った開発手順](ai-assisted-development.ja.md)から。
[AI向け技術メモ](ai-service-context.ja.md)を現在のソースファイルと一緒に渡す。

音声認識後の文章の解釈設定は[Assistant providers](assistant-providers.ja.md)を参照。

実験的なiron-X接続は[PC・iPhoneでの人追従と復旧](hardware/ironx-follow.ja.md)から。
通常の起動・操作と確認済み範囲をまとめ、個別試験は詳細資料へ分離している。

多くの利用者が最初に読む資料である。

[目的と位置づけ](positioning.ja.md)でAPRIS、APRISRC、Kit、参加者が作るサービスを区別する。
サンプルは開発の出発点で、これらのガイドは競技規則や審査基準ではない。

| やりたいこと | ドキュメント |
| --- | --- |
| Windowsで起動する・Pythonやバックエンドの準備エラーを解決する | [Windowsの起動・トラブル対応](windows-setup.ja.md) |
| 体験・開発・実機引き継ぎの入口を選ぶ | [試す・変更する・引き継ぐ](handoff.ja.md) |
| MVPを動かし、小さな変更の効果を比較する | [Playground実習ガイド](demos/playground-workshop.ja.md) |
| サービスの体験とコードの関係を試す | [Service playground](demos/service-playground.ja.md) |

| 独自の人物反応serviceを作る | [参加者向けquickstart](challenger-quickstart.ja.md) |
| 利用できるmission APIと安全境界を知る | [Mission API and service templates](mission-api.ja.md) |
| 対応UGV02で同じstarterを試す | [UGV02 self-test](hardware/ugv02-self-test.ja.md) |
| 学生PCのKitサーバーからLAN経由でiron-Xへ接続する（実験的） | [iron-Xネットワーク接続](hardware/ironx-network.ja.md) |
| iron-Xで人追従を実行し、停止から復旧する（実験的） | [iron-X人追従](hardware/ironx-follow.ja.md) |
| 現在できることと制約を確認する | [Platform status](platform-status.ja.md) |


公開範囲は[初回公開](release-scope.ja.md)、変更の提案は[開発への参加](../CONTRIBUTING.ja.md)を参照する。

## Reference

特定の機能を使うときに参照する。

| 目的 | ドキュメント |
| --- | --- |
| `/service`、`/console`、`/playground`の役割を知る | [PWA views](pwa-views.ja.md) |
| 共通の安全境界と責務を確認する | [アーキテクチャ](architecture.ja.md) |
| 実験的な実機Playgroundの観測と安全条件を確認する | [Live rover playground](demos/hardware-playground.ja.md) |
| smartphoneからHTTPSで接続する | [Local HTTPS and smartphone setup](local-https.ja.md) |
| 再現可能な入力や故障を使って試験する | [Simulator scenarios, fault injection, and logs](simulator-scenarios.ja.md) |
| 人物・marker認識、odometry、pose補正を理解する | [Perception and pose estimation](perception-and-pose.ja.md) |
| undefined | [Mobile Receptionist demo](demos/mobile-receptionist.ja.md) |
| 旧Carry専用画面の状態遷移を読む | [Autonomous carry service](demos/autonomous-carry-service.ja.md) |
| 想定機材と別機材へ交換する条件を知る | [Service hardware assumptions and porting](hardware/service-hardware-porting.ja.md) |

## Maintainer and operations

platform、firmware、integrationを保守するときに使う。通常のservice開発では不要である。

| 目的 | ドキュメント |
| --- | --- |
| 起動、停止、readiness、log収集、復旧 | [Operations runbook](operations/runbook.md) |
| 次の開発項目と長期scopeを管理する | [Development roadmap](roadmap.ja.md) |
| browser clientとserver間のschemaを調べる | [Client protocol](protocol.md) |
| roverとserver間のmotion contractを調べる | [APRIS Rover WebSocket protocol](rover-protocol.ja.md) |
| APRIS firmwareをbuild、flash、qualificationする | [UGV02 APRIS WebSocket firmware](hardware/ugv02-websocket-firmware.md) |

## Where to update

英語版を正本とする。既定の`.md`が英語版で、日本語訳は`.ja.md`に置く。仕様、挙動、
優先順位を変更するときは英語版を先に更新し、その後で日本語版を同期する。

- 現在できることや既知の制約が変わったら`platform-status.md`を更新する。
- 開発の優先順位やmilestoneが変わったら`roadmap.md`を更新する。
- 起動、停止、診断、復旧手順が変わったら`operations/runbook.md`を更新する。
- 外部へ公開するcontractが変わったら対応するprotocol文書を更新する。
- 設計上の重要な選択をしたらADRを追加する。
- 新しい資料を追加したら、このindexと必要に応じてtop-level READMEへ入口を追加する。
