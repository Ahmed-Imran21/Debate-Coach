#!/usr/bin/env node
/**
 * Stages the MediaPipe WASM runtime and task models under
 * public/mediapipe/, so the browser loads them from our own
 * origin instead of a CDN (required by CSP and by §4.1 of the
 * video-analysis task: never load WASM or models from a CDN at
 * runtime).
 *
 * Idempotent: skips work that is already done. Run via
 * `npm install` (wired as "postinstall"), or by hand:
 *   node scripts/setup-mediapipe.mjs
 *
 * On a version bump of @mediapipe/tasks-vision, delete
 * public/mediapipe/ and reinstall to force a clean regenerate.
 */

import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { copyFile, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const WEB_ROOT = path.resolve(__dirname, "..");

const PKG_DIR = path.join(WEB_ROOT, "node_modules", "@mediapipe", "tasks-vision");
const WASM_SRC = path.join(PKG_DIR, "wasm");
const OUT_DIR = path.join(WEB_ROOT, "public", "mediapipe");
const WASM_OUT = path.join(OUT_DIR, "wasm");
const MODELS_OUT = path.join(OUT_DIR, "models");
const MANIFEST_PATH = path.join(OUT_DIR, "manifest.json");

// Do not substitute other model URLs if a download fails; stop
// and surface it instead (§4.1.3).
const MODEL_SOURCES = [
  {
    task: "face_landmarker",
    filename: "face_landmarker.task",
    url: "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
  },
  {
    task: "hand_landmarker",
    filename: "hand_landmarker.task",
    url: "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task",
  },
];

async function readRuntimeVersion() {
  const pkgJson = JSON.parse(await readFile(path.join(PKG_DIR, "package.json"), "utf-8"));
  return pkgJson.version;
}

async function copyWasmAssets() {
  if (!existsSync(WASM_SRC)) {
    throw new Error(
      `@mediapipe/tasks-vision is not installed (expected ${WASM_SRC}). ` +
        "Run npm install first.",
    );
  }

  await mkdir(WASM_OUT, { recursive: true });

  const entries = await readdir(WASM_SRC);
  for (const name of entries) {
    await copyFile(path.join(WASM_SRC, name), path.join(WASM_OUT, name));
  }

  return entries.length;
}

function sha256(buffer) {
  return createHash("sha256").update(buffer).digest("hex");
}

async function ensureModel({ task, filename, url }) {
  await mkdir(MODELS_OUT, { recursive: true });
  const dest = path.join(MODELS_OUT, filename);

  if (!existsSync(dest)) {
    console.log(`[setup-mediapipe] downloading ${task} from ${url}`);

    let response;
    try {
      response = await fetch(url);
    } catch (cause) {
      throw new Error(`Failed to download ${task} model from ${url}: ${cause.message}`, { cause });
    }

    if (!response.ok) {
      throw new Error(`Failed to download ${task} model from ${url}: HTTP ${response.status}`);
    }

    const buffer = Buffer.from(await response.arrayBuffer());
    await writeFile(dest, buffer);
  }

  const bytes = await readFile(dest);

  return {
    task,
    model_id: filename,
    sha256: sha256(bytes),
    path: `/mediapipe/models/${filename}`,
  };
}

async function main() {
  const [runtimeVersion, wasmFileCount] = await Promise.all([
    readRuntimeVersion(),
    copyWasmAssets(),
  ]);

  console.log(`[setup-mediapipe] copied ${wasmFileCount} wasm asset(s)`);

  const models = [];
  for (const source of MODEL_SOURCES) {
    // Sequential, not Promise.all: a failure on the first model
    // should not leave the second half-downloaded.
    models.push(await ensureModel(source));
  }

  const manifest = { runtime_version: runtimeVersion, models };
  await writeFile(MANIFEST_PATH, JSON.stringify(manifest, null, 2) + "\n", "utf-8");

  console.log(`[setup-mediapipe] wrote ${path.relative(WEB_ROOT, MANIFEST_PATH)}`);
  for (const model of models) {
    console.log(`  ${model.task}: ${model.path} (${model.sha256.slice(0, 12)}...)`);
  }
}

main().catch((error) => {
  console.error(`[setup-mediapipe] ${error.message}`);
  process.exitCode = 1;
});
