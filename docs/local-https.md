# Local HTTPS and smartphone setup

[日本語](local-https.ja.md)

This guide assumes a **Windows PC with PowerShell** hosting Kit. macOS/Linux differences
are collapsed below. A phone is only needed for camera trials; desktop Simulator work uses
HTTP and needs no certificate. An iPhone uses Safari on the phone, not on the PC.

The phone connects to Vite over HTTPS/WSS; Vite proxies to FastAPI over HTTP on port 8000.
This does not encrypt the separate rover/gateway WebSocket connection.

## 1. Generate certificates on Windows

Start in the repository root. The certificate script requires OpenSSL in addition to the
normal simulator tools. It uses `OPENSSL` if set, otherwise searches for `openssl`.

```powershell
openssl version
```

If not found, use your institution-approved OpenSSL installation. If your Git for Windows
installation includes OpenSSL, you can point to its actual executable; for example:

```powershell
$env:OPENSSL = "C:\Program Files\Git\usr\bin\openssl.exe"
Test-Path $env:OPENSSL
& $env:OPENSSL version
```

Continue only when the executable exists and the version check succeeds. The path is an
example, not a promise about every Git installation. Generate certificates:

```powershell
npm.cmd run cert:generate
```

The script creates ignored files in `.certs/`: public CA `apris-local-ca.pem`, CA private key
`apris-local-ca-key.pem`, and `localhost.pem` / `localhost-key.pem`. It includes localhost and
current LAN addresses but does not install trust. Use `npm.cmd run cert:generate -- <PC-LAN-IP>`
for another address; replace the placeholder. Regenerate after an address change.

## 2. Trust your CA on Windows

Only trust the CA you generated for this project. Do not import unknown certificates to
bypass warnings. In PowerShell, convert your public CA to DER and import it for the current
Windows user:

```powershell
if (-not $env:OPENSSL) { $env:OPENSSL = "openssl" }
& $env:OPENSSL x509 -in .certs/apris-local-ca.pem -outform DER -out .certs/apris-local-ca.cer
Import-Certificate -FilePath .certs/apris-local-ca.cer -CertStoreLocation Cert:\CurrentUser\Root
```

Check successful conversion before importing. See Microsoft's
[Import-Certificate reference](https://learn.microsoft.com/en-us/powershell/module/pki/import-certificate).
If an institutional policy prevents this, ask the administrator; do not weaken policy.
Use Edge or Chrome to verify the eventual URL without certificate warnings.
Remove this project's CA trust after the project. Never share or commit private keys.

<details>
<summary>macOS / Linux: generation and PC trust</summary>

Use an available OpenSSL executable (`OPENSSL` can specify its path), then
`npm run cert:generate`. On macOS, import only `.certs/apris-local-ca.pem` in Keychain Access
and explicitly trust your development CA. On Linux, use the certificate trust procedure
for your distribution and browser, with administrator guidance where required.
Verify the final URL without warnings; browser certificate stores may differ.

For the startup commands below, use `unset APRIS_DISABLE_HTTPS` and `npm run dev`.
To run only the simulator over HTTP:
`APRIS_ADAPTER=simulator APRIS_DISABLE_HTTPS=1 npm run dev`.

</details>

## 3. Trust the public CA on the phone

Transfer only `apris-local-ca.pem` or its public `.cer` copy through a private channel.
Never transfer `*-key.pem`. PC trust does not automatically configure phone trust.

- **iPhone/iPad:** install the downloaded profile in Settings, then enable this CA under
  Settings > General > About > Certificate Trust Settings. Use Safari on the phone.
- **Android:** install the public CA using the device's certificate settings. Device/browser
  behavior differs; confirm the final URL and camera permission on that device.

Do not proceed through certificate warnings. Resolve trust, expiry or address mismatches.

## 4. Start on the PC and connect from the phone

Stop an existing dev server before changing its settings. Keep the intended adapter settings
from its hardware guide; these commands do not choose a robot or authorize movement.

```powershell
Remove-Item Env:APRIS_DISABLE_HTTPS -ErrorAction SilentlyContinue
npm.cmd run dev
```

Both Vite certificate files must exist. Use the printed HTTPS port (normally 5173) and open
`https://<PC-LAN-IP>:<HTTPS-port>/service?service=carry` on the phone.
Use the PC's address covered by the certificate, not phone localhost or the robot address.
The PC and phone need mutual LAN reachability. Restrict Windows Firewall access to the
trusted trial network and required ports; do not disable the firewall. Guest/client-isolated
Wi-Fi may prevent access regardless of certificate settings.

For desktop-only Simulator work, use the PowerShell commands in [Windows setup](windows-setup.md).
After regeneration restart Vite; if the CA changed, update trust on both PC and phone.
Camera setup alone does not start motion; follow the hardware guide's permission steps.

## Limits

The browser sends structured observations, not video. This is development HTTPS, not a
production deployment recipe. Windows is the primary documented path, but these commands
have not been executed on a Windows machine as part of this edit.
