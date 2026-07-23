#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { createRequire } from "node:module";
import Ajv2020 from "ajv/dist/2020.js";

const require = createRequire(path.join(process.cwd(), "aq-contract-validator-runtime.mjs"));

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.exit(1);
}

function base64url(value) {
  if (typeof value !== "string" || value.includes("=") || !/^[A-Za-z0-9_-]*$/.test(value)) {
    throw new Error("invalid base64url without padding");
  }
  return Buffer.from(value, "base64url");
}

function u64be(value) {
  const output = Buffer.alloc(8);
  output.writeBigUInt64BE(BigInt(value));
  return output;
}

function canonical(value) {
  if (value === null || typeof value === "boolean" || typeof value === "string") {
    return JSON.stringify(value);
  }
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value)) throw new Error("canonical input must contain safe integers only");
    return String(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  const keys = Object.keys(value).sort((a, b) => Buffer.compare(Buffer.from(a), Buffer.from(b)));
  return `{${keys.map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
}

function hashFile(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

function packageTreeDigest(packageRoot) {
  const files = [];
  function walk(directory, prefix = "") {
    const entries = fs.readdirSync(directory, { withFileTypes: true });
    entries.sort((left, right) => Buffer.compare(Buffer.from(left.name), Buffer.from(right.name)));
    for (const entry of entries) {
      const absolute = path.join(directory, entry.name);
      const relative = prefix ? `${prefix}/${entry.name}` : entry.name;
      if (entry.isSymbolicLink()) throw new Error(`dependency tree contains symlink: ${relative}`);
      if (entry.isDirectory()) walk(absolute, relative);
      else if (entry.isFile()) files.push([relative, fs.readFileSync(absolute)]);
      else throw new Error(`dependency tree contains unsupported file type: ${relative}`);
    }
  }
  walk(packageRoot);
  const digest = crypto.createHash("sha256");
  for (const [relative, bytes] of files) {
    const name = Buffer.from(relative, "utf8");
    const nameLength = Buffer.alloc(4);
    nameLength.writeUInt32BE(name.length);
    const byteLength = Buffer.alloc(8);
    byteLength.writeBigUInt64BE(BigInt(bytes.length));
    digest.update(nameLength).update(name).update(byteLength).update(bytes);
  }
  return digest.digest("hex");
}

function runtimeEvidence(expectedPackageNames) {
  const ajvPackagePath = fs.realpathSync(require.resolve("ajv/package.json"));
  const ajvEntryPath = fs.realpathSync(require.resolve("ajv/dist/2020.js"));
  const dependencyRoot = fs.realpathSync(path.dirname(ajvPackagePath));
  const nodeModulesRoot = fs.realpathSync(path.dirname(dependencyRoot));
  const packageTrees = {};
  const packageVersions = {};
  for (const name of expectedPackageNames) {
    const packagePath = fs.realpathSync(require.resolve(`${name}/package.json`));
    const packageRoot = fs.realpathSync(path.dirname(packagePath));
    if (path.dirname(packageRoot) !== nodeModulesRoot) throw new Error(`dependency resolved outside fixed node_modules root: ${name}`);
    packageTrees[name] = packageTreeDigest(packageRoot);
    packageVersions[name] = JSON.parse(fs.readFileSync(packagePath, "utf8")).version;
  }
  const ajvPackage = JSON.parse(fs.readFileSync(ajvPackagePath, "utf8"));
  return {
    node_version: process.version,
    node_exec_path: fs.realpathSync(process.execPath),
    node_binary_sha256: hashFile(fs.realpathSync(process.execPath)),
    ajv_version: ajvPackage.version,
    ajv_package_path: ajvPackagePath,
    ajv_entry_path: ajvEntryPath,
    node_modules_root: nodeModulesRoot,
    package_tree_sha256: packageTrees,
    package_versions: packageVersions,
  };
}

function validateGoldenCrypto(localKeyArtifact) {
  const wire = localKeyArtifact.local_keyring_wire;
  const primitive = wire.golden_primitive_vector;
  const primitiveKey = base64url(primitive.key_base64url);
  const primitiveNonce = base64url(primitive.nonce_base64url);
  const primitiveAad = Buffer.from(primitive.aad_utf8_hex, "hex");
  const primitivePlaintext = Buffer.from(primitive.plaintext_utf8_hex, "hex");
  const primitiveCombined = base64url(primitive.ciphertext_and_tag_base64url);
  const primitiveCiphertext = primitiveCombined.subarray(0, -16);
  const primitiveTag = primitiveCombined.subarray(-16);
  const primitiveDecipher = crypto.createDecipheriv("aes-256-gcm", primitiveKey, primitiveNonce);
  primitiveDecipher.setAAD(primitiveAad);
  primitiveDecipher.setAuthTag(primitiveTag);
  const primitiveActual = Buffer.concat([primitiveDecipher.update(primitiveCiphertext), primitiveDecipher.final()]);
  if (!crypto.timingSafeEqual(primitiveActual, primitivePlaintext)) throw new Error("primitive AES-256-GCM vector mismatch");

  const golden = wire.golden_payload_envelope;
  const envelope = golden.envelope;
  const nonceKey = base64url(golden.nonce_key_base64url);
  const expectedNonce = crypto
    .createHmac("sha256", nonceKey)
    .update(Buffer.from("agent-quota:keyring-envelope:v1\0", "ascii"))
    .update(u64be(envelope.envelope_sequence))
    .digest()
    .subarray(0, 12);
  const nonce = base64url(envelope.nonce);
  if (nonce.length !== 12 || !crypto.timingSafeEqual(nonce, expectedNonce)) throw new Error("golden envelope nonce mismatch");

  const aadObject = {
    schema: envelope.schema,
    installation_id: envelope.installation_id,
    binding_key_id: envelope.binding_key_id,
    aead_generation: envelope.aead_generation,
    envelope_sequence: envelope.envelope_sequence,
  };
  const aad = Buffer.concat([
    Buffer.from("agent-quota:keyring:v1\0", "ascii"),
    Buffer.from(canonical(aadObject), "utf8"),
  ]);
  const combined = base64url(envelope.ciphertext_and_tag);
  if (combined.length < 16) throw new Error("golden ciphertext is shorter than the GCM tag");
  const decipher = crypto.createDecipheriv("aes-256-gcm", base64url(golden.aead_key_base64url), nonce);
  decipher.setAAD(aad);
  decipher.setAuthTag(combined.subarray(-16));
  const plaintext = Buffer.concat([decipher.update(combined.subarray(0, -16)), decipher.final()]);
  const expectedPlaintext = Buffer.from(canonical(golden.payload), "utf8");
  if (plaintext.length !== expectedPlaintext.length || !crypto.timingSafeEqual(plaintext, expectedPlaintext)) {
    throw new Error("golden payload envelope plaintext mismatch");
  }
}

let input = "";
process.stdin.setEncoding("utf8");
for await (const chunk of process.stdin) input += chunk;

try {
  const payload = JSON.parse(input);
  const runtimeBefore = runtimeEvidence(payload.expected_package_names);
  const ajv = new Ajv2020({
    allErrors: true,
    strict: true,
    strictRequired: false,
    strictTypes: false,
    validateSchema: true,
  });
  ajv.addKeyword({ keyword: "x-aq-array-order", schemaType: "object", valid: true });

  for (const schema of payload.schemas) {
    if (!ajv.validateSchema(schema.document)) {
      throw new Error(`Draft 2020-12 meta-validation failed for ${schema.path}: ${ajv.errorsText(ajv.errors)}`);
    }
    ajv.addSchema(schema.document);
  }

  for (const instance of payload.instances) {
    const validate = ajv.getSchema(instance.schema_uri);
    if (!validate) throw new Error(`bound schema URI is unavailable: ${instance.schema_uri}`);
    if (!validate(instance.document)) {
      throw new Error(`instance validation failed for ${instance.path}: ${ajv.errorsText(validate.errors)}`);
    }
  }

  validateGoldenCrypto(payload.local_key_artifact);
  const runtimeAfter = runtimeEvidence(payload.expected_package_names);
  if (canonical(runtimeBefore) !== canonical(runtimeAfter)) throw new Error("validation dependency identity or bytes changed during execution");
  process.stdout.write(JSON.stringify({
    meta_validated: payload.schemas.length,
    instances_validated: payload.instances.length,
    golden_crypto: "ok",
    runtime: runtimeBefore,
  }));
} catch (error) {
  fail(error instanceof Error ? error.message : String(error));
}
