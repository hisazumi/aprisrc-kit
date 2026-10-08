# 初回公開の範囲

[English](release-scope.md)

このrepoは確認した現行ファイルのsnapshot一つから開始し、private repoのcommit履歴・branch・
PR・issue・Actions logを引き継ぎません。

含むもの: service/runtimeコードと自己完結したテスト、Simulator scenario、protocol schema、
参加者ガイド、公開用アーキテクチャ/安全境界の要約、印刷マーカー、既存権利表示を維持したGPLの
firmware source。compiled firmwareは提供しません。

含まないもの: 内部計画、統合/実験の詳細履歴、pilot評価資料、生の録画、local credential/設定、
flash backup、motor診断script、別管理のPhysiCode provider contract bundle/supervisor。
実機の安全上の制約と未検証事項は公開ガイドに要約し、個別試験の履歴は公開しません。
技術上の設定名やfirmware識別子は維持します。

今後のコード貢献はこちらで行い、検討・個別評価は別に管理します。この公開はAPRISRCの規則や
公式/必須の位置づけを定めるものではありません。[目的と位置づけ](positioning.ja.md)と
[ライセンス](../LICENSING.md)を参照してください。

## 検証

独立した公開checkoutでPWA 122件、server 112件、型チェック、production build、Ruffが成功しました。
外部provider contractの3件は、そのbundleとともに初回公開から除外しています。
互換範囲の依存更新とVitest 4.1.11への移行後、npm auditは0件です。
包括的なsecurity auditではなく、今回の実機試験やfirmware build検証は行っていません。
