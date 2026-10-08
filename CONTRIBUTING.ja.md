# 開発への参加

[English](CONTRIBUTING.md)

[引き継ぎガイド](docs/handoff.ja.md)と[目的と位置づけ](docs/positioning.ja.md)から始めます。
featureブランチで変更し、この公開repoの`main`宛てにPRを作ります。期待する挙動、実際の結果、
試験環境と未検証事項を記載します。Simulator/mockの成功を実機検証とは記載しません。

サービス変更はmission・設定・テスト・登録を中心に行います。操作権、期限、速度上限、前方安全、
切断停止、E-stopを迂回しません。runtime変更前に`AGENTS.md`を読み、root READMEの標準チェックを実行します。

credential、CA秘密鍵、生の録画、参加者評価、flash backupをcommitやissueに載せません。
push前にstaged fileを確認します。再現可能な問題報告には仮想観測を使い、sample、シーン/設定、
commit、秘密情報を除いたerror/statusを記載します。

この公開repoをAPRISRC Kitのコード開発の正本とします。privateの検討・個別評価記録は別管理で、
そのGit履歴のmirrorではありません。[ライセンス](LICENSING.md)に従い、変更対象に適合する権利で
貢献してください。firmware変更は既存GPLの条件を維持します。
