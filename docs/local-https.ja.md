# Local HTTPS and smartphone setup

[English](local-https.md)

スマートフォンのカメラ API は、`localhost` を除き secure context でのみ利用できる。そのため、スマートフォンから PC Local Server へ Wi-Fi 経由で接続するときは、PWA を HTTPS で配信する。

## Connection path

```text
Smartphone browser
  https://PC-LAN-IP:5173/app
  wss://PC-LAN-IP:5173/ws
           │
           ▼
Vite HTTPS server / WebSocket proxy
           │ ws://localhost:8000/ws
           ▼
FastAPI Local Server
```

phoneから見える接続はHTTPS/WSSになる。FastAPIの8000はHTTPだが、Rover modeでは
UGV02もLANから接続するため、trusted private LANだけにアクセスを制限する。
phone側のHTTPSは、firmwareの別のplain WebSocket接続を暗号化するものではない。

## 1. Generate a development CA and certificate

PC ごとに一度実行する。

OpenSSLが必要で、mkcertは使わない。IP変更時は再生成する。

```bash
npm run cert:generate
```

実行時に利用中のローカル IPv4 アドレスを自動検出し、証明書の SAN に加える。必要な IPv4/IPv6 アドレスを明示的に追加することもできる。

```bash
npm run cert:generate -- 192.168.1.50
```

生成物は `.certs/` に保存され、Git には追加されない。`apris-local-ca-key.pem` と `localhost-key.pem` は秘密鍵なので共有してはならない。スマートフォンへ渡すのは公開証明書 `apris-local-ca.pem` だけである。

証明書生成だけでは信頼設定は変更されない。以下の操作は利用者が対象を確認して手動で行う。

## 2. Trust the CA on the development PC

macOS の「キーチェーンアクセス」で `.certs/apris-local-ca.pem` を「システム」キーチェーンへ追加し、証明書の「信頼」を「常に信頼」に設定する。管理者パスワードが必要になる場合がある。

イベント終了後に信頼を解除する場合は、同じ証明書をキーチェーンアクセスから削除する。

## 3. Trust the CA on a phone

### iPhone / iPad

1. `.certs/apris-local-ca.pem` を AirDrop などで端末へ渡し、構成プロファイルとしてインストールする。
2. 「設定 → 一般 → VPNとデバイス管理」でプロファイルを確認する。
3. 「設定 → 一般 → 情報 → 証明書信頼設定」で `APRIS Rover Local Development CA` を有効にする。

### Android

端末のセキュリティ設定から CA 証明書として `.certs/apris-local-ca.pem` を追加する。メニュー名や、ユーザー CA を利用できるかどうかは端末の管理ポリシーによって異なる。

## 4. Start and connect

```bash
npm run dev
```

`.certs/localhost.pem` と `.certs/localhost-key.pem` が揃っている場合、Vite は自動的に HTTPS で起動する。PC とスマートフォンを同じネットワークへ接続し、起動ログに表示されたホストの `/app`、例えば `https://<PCのIPアドレス>:5173/app` をスマートフォンで開く。

HTTP に一時的に戻す場合は、PWA の起動時に `APRIS_DISABLE_HTTPS=1` を指定する。

```bash
APRIS_ADAPTER=simulator APRIS_DISABLE_HTTPS=1 npm run dev
```

## Operational notes

- 上のHTTP起動はPC専用Simulator試験向け。phone試験では`APRIS_DISABLE_HTTPS`を未設定にする。
- 証明書の再生成後はViteを再起動する。CA自体を変えた場合は各端末で新しい公開CAを信頼し直す。
- Wi-Fi が変わって PC の IP アドレスが変化した場合は、証明書を再生成する。
- CA 証明書の警告を無視して進む運用にはしない。カメラ API や PWA が正常に動かないことがある。
- 不特定多数の端末へ個人 PC の開発用 CA を配布しない。イベント運用では、専用 PC と専用 CA を用意して対象端末を管理する。
- PWA から見える WebSocket URL はページと同じ origin から自動生成されるため、HTTPS では自動的に WSS になる。
