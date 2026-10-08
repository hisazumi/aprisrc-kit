import { execFileSync } from "node:child_process";
import { chmodSync, existsSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { isIP } from "node:net";
import { networkInterfaces } from "node:os";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const certificateDirectory = resolve(repositoryRoot, ".certs");
const caCertificate = resolve(certificateDirectory, "apris-local-ca.pem");
const caKey = resolve(certificateDirectory, "apris-local-ca-key.pem");
const serverCertificate = resolve(certificateDirectory, "localhost.pem");
const serverKey = resolve(certificateDirectory, "localhost-key.pem");
const requestFile = resolve(certificateDirectory, "localhost.csr");
const extensionFile = resolve(certificateDirectory, "server-ext.cnf");
const serialFile = resolve(certificateDirectory, "apris-local-ca.srl");

function openssl(...args) {
  execFileSync(process.env.OPENSSL ?? "openssl", args, { stdio: "inherit" });
}

function localAddresses() {
  const addresses = new Set(["127.0.0.1", "::1"]);
  for (const interfaces of Object.values(networkInterfaces())) {
    for (const address of interfaces ?? []) {
      if (!address.internal && address.family === "IPv4") addresses.add(address.address);
    }
  }
  for (const argument of process.argv.slice(2)) {
    if (!isIP(argument)) throw new Error(`Not a valid IP address: ${argument}`);
    addresses.add(argument);
  }
  return [...addresses];
}

mkdirSync(certificateDirectory, { recursive: true });

try {
  openssl("version");

  if (!existsSync(caCertificate) || !existsSync(caKey)) {
    openssl(
      "req", "-x509", "-newkey", "rsa:3072", "-nodes", "-sha256", "-days", "3650",
      "-subj", "/CN=APRIS Rover Local Development CA",
      "-keyout", caKey,
      "-out", caCertificate
    );
  }

  const addresses = localAddresses();
  const altNames = ["DNS.1 = localhost"];
  addresses.forEach((address, index) => altNames.push(`IP.${index + 1} = ${address}`));
  writeFileSync(extensionFile, `[req]
distinguished_name = subject
prompt = no

[subject]
CN = localhost

[server_ext]
basicConstraints = critical, CA:FALSE
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
${altNames.join("\n")}
`);

  openssl("genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", serverKey);
  openssl("req", "-new", "-key", serverKey, "-out", requestFile, "-config", extensionFile);
  openssl(
    "x509", "-req", "-in", requestFile,
    "-CA", caCertificate, "-CAkey", caKey, "-CAcreateserial",
    "-out", serverCertificate, "-days", "825", "-sha256",
    "-extfile", extensionFile, "-extensions", "server_ext"
  );

  chmodSync(caKey, 0o600);
  chmodSync(serverKey, 0o600);
  console.log("\nDevelopment certificate created for:");
  addresses.forEach((address) => {
    const host = isIP(address) === 6 ? `[${address}]` : address;
    console.log(`  https://${host}:5173`);
  });
  console.log("  https://localhost:5173");
  console.log("\nThe CA has only been generated, not installed or trusted.");
  console.log("Follow docs/local-https.md before opening the PWA on a phone.");
} finally {
  for (const temporaryFile of [requestFile, extensionFile, serialFile]) {
    rmSync(temporaryFile, { force: true });
  }
}
