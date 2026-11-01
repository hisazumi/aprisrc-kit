# Local HTTPS and smartphone setup

[日本語](local-https.ja.md)

Smartphone camera access requires a secure context. The development setup terminates HTTPS
and WSS at Vite while proxying `/api` and `/ws` to local FastAPI.

```text
Phone browser
  https://PC-LAN-IP:5173/service
  wss://PC-LAN-IP:5173/ws
            |
            v
Vite development server
            |
            +-- ws://localhost:8000/ws
            +-- http://localhost:8000/api
```

FastAPI port 8000 uses HTTP. In Rover mode the UGV02 also needs LAN access to port 8000;
restrict access to the trusted private LAN. Phone-facing Vite uses HTTPS/WSS, but this does
not encrypt the firmware's separate plain WebSocket connection.

## 1. Generate a development CA and certificate

From the repository root:

```bash
npm run cert:generate
```

The script writes the ignored `.certs/localhost.pem` and `.certs/localhost-key.pem` files and
includes localhost plus current private LAN addresses. Regenerate after the PC LAN address
changes.

The script requires OpenSSL and generates `.certs/apris-local-ca.pem` plus the private
`.certs/apris-local-ca-key.pem`. It does not use mkcert or install trust automatically.
An additional address can be included with `npm run cert:generate -- <PC-LAN-IP>`.

## 2. Trust the CA on the development PC

On macOS, manually import `.certs/apris-local-ca.pem` into Keychain Access and configure
trust for this development CA. On other PCs use the operating system's certificate store.
Only trust your own intended development CA. Never commit either private key or copy it into
a diagnostic bundle. Remove the development CA trust after the project.

## 3. Trust the CA on a phone

Transfer only `.certs/apris-local-ca.pem` to the phone through a private channel, never either
`*-key.pem` file. Do not continue through a certificate warning; fix trust/address mismatch first.

### iPhone / iPad

1. Install the downloaded profile in Settings.
2. Open **Settings > General > About > Certificate Trust Settings**.
3. Enable full trust for the development root CA.

### Android

Install the CA certificate as a VPN and apps certificate using the device's security settings.
Browser and vendor behavior varies; verify the final URL without a certificate warning.

## 4. Start and connect

```bash
npm run dev
```

When both certificate files exist, Vite starts in HTTPS mode. Connect the PC and phone to the
same LAN, then open `https://<PC-LAN-IP>:<HTTPS-port>/service` on the phone. The usual
port is 5173; a separate HTTPS instance may use 5174. Use the actual startup URL,
not an HTTP instance's port, and the exact IP included in
the generated certificate.

For PC-only Simulator work use `APRIS_ADAPTER=simulator APRIS_DISABLE_HTTPS=1 npm run dev`.
Leave `APRIS_DISABLE_HTTPS` unset for smartphone trials. Do not use an insecure context for
smartphone camera validation. Restart Vite after certificate regeneration; if the CA itself
was replaced, trust the new public CA certificate on each test device.

## Operational notes

- The browser sends only structured perception observations, not camera video.
- A changed LAN address normally requires certificate regeneration.
- Client-isolating guest Wi-Fi prevents the phone, PC, and rover from communicating.
- Treat the development CA as a credential and remove it from devices after the project.
- Production deployment requires a separately managed certificate and trust model.
