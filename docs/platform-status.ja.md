# Platform status

[English](platform-status.md)

共通画面の文書確認：2026-11-01。実機試験の追加はありません。
APRISRC Kitは参加者がサービスを作る基盤であり、サンプルは指定課題や競技規則ではありません。

## 現在使えるもの

- Service / Playground / Consoleの共通ヘッダーとサービスを保持するURL。
- My service、Carry helper、Person greeting、Mobile receptionistの共通実行・質問回答パネル。
- Simulator Playgroundの人物手動操作、発話模擬、シナリオJSON、マーカー入力。
- 読み取り専用のImplementation。`missions/myService.ts`を編集して試せる。
- 全サービス共通のマーカー入力。Markers visibleの既定はオフ。
- Advanced controls内の汎用missionと文章・音声intent処理。rules / OpenAI / Geminiは別の解釈経路。
- サーバーの操作権、速度上限、指令TTL、切断停止、latched E-stop。
- Simulator、UGV02 WebSocket、診断用factory HTTP、実験的iron-X local/network Adapter。

## 現在の制約

- 共通Service・実機Playgroundは別途30秒の手動走行確認が必要。サービス開始では延長しない。
  旧Carry専用画面の自動更新が引き継がれていない既知の制約である。
  自動更新はSimulatorのPlaygroundだけ。詳しくは[実機操作](demos/hardware-playground.ja.md)。
- 共通UIの実機検証は未完了。過去のUGV02・iron-X追従試験は旧構成での記録である。
- 実機マーカー案内はService・Playgroundとも無効。旧URLから別経路には入れない。
- 専用プレビュースライダー、実行行強調、旧Carry画面の専用音声・LLM操作は共通UIにない。
- シミュレータ観測は幾何学的な模擬入力で、実カメラの精度を検証しない。
- 前方手動確認はセンサーによる空間確認ではない。後方・側方保護、一般的障害物回避、
  LiDAR安全統合、SLAM、経路計画、同行監視、実停止距離の保証はない。
- サービス状態はブラウザ側にあり、再接続だけでは再開しない。無人運用向けではない。

## 検証と次の作業

共通化のブラウザ試験で4サービスのシミュレータフロー、マーカー初期値、デスクトップ・
スマホ幅を確認した。myServiceへの改名後はPWA 183テスト・ビルドが成功した。
これは実機やWindows起動の検証ではない。

次は[参加者quickstart](challenger-quickstart.ja.md)と
[引き継ぎ](handoff.ja.md)で他の人が試せることを確認する。
実機利用前には走行許可方式の見直しと共通UIの再検証が必要。
長期計画は[ロードマップ](roadmap.ja.md)、起動・復旧は[運用](operations/runbook.md)。
過去のハードウェア試験は各機体ガイドを参照し、新UIの保証と混同しない。
