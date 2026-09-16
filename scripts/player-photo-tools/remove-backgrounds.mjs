import fs from "node:fs";
import path from "node:path";
import process from "node:process";

import * as ort from "onnxruntime-node";
import sharp from "sharp";

const root = path.resolve(import.meta.dirname, "../..");
const sourceDir = path.resolve(root, process.argv[2] ?? "image/players/local/originals");
const outputDir = path.resolve(root, process.argv[3] ?? "image/players/local");
const modelPath = path.resolve(root, process.argv[4] ?? "image/players/local/models/u2netp.onnx");
const matteLow = Number(process.argv[5] ?? 0.18);
const matteHigh = Number(process.argv[6] ?? 0.82);
const targetWidth = 376;
const targetHeight = 472;

if (!(matteLow >= 0 && matteLow < matteHigh && matteHigh <= 1)) {
  throw new Error(`Invalid matte range: ${matteLow}..${matteHigh}`);
}

if (!fs.existsSync(modelPath)) throw new Error(`ONNX model not found: ${modelPath}`);
if (!fs.existsSync(sourceDir)) throw new Error(`Source directory not found: ${sourceDir}`);
fs.mkdirSync(outputDir, { recursive: true });

const sessionOptions = {
  executionProviders: ["cpu"],
  graphOptimizationLevel: "all",
  intraOpNumThreads: 1,
  interOpNumThreads: 1,
};
const session = await ort.InferenceSession.create(modelPath, sessionOptions);
const inputName = session.inputNames[0];
const outputName = session.outputNames[0];
const files = fs.readdirSync(sourceDir).filter((name) => /^\d+\.jpe?g$/i.test(name)).sort();
let completed = 0;
let failed = 0;

function normalizedTensor(rgb) {
  const pixels = 320 * 320;
  const data = new Float32Array(3 * pixels);
  const mean = [0.485, 0.456, 0.406];
  const std = [0.229, 0.224, 0.225];
  for (let index = 0; index < pixels; index++) {
    for (let channel = 0; channel < 3; channel++) {
      data[channel * pixels + index] = (rgb[index * 3 + channel] / 255 - mean[channel]) / std[channel];
    }
  }
  return new ort.Tensor("float32", data, [1, 3, 320, 320]);
}

function alphaFromOutput(output) {
  const expectedPixels = 320 * 320;
  if (output.data.length !== expectedPixels) {
    throw new Error(
      `Unexpected model output ${output.dims.join("x")} (${output.data.length} values); expected ${expectedPixels}`,
    );
  }
  const values = output.data;
  let minimum = Infinity;
  let maximum = -Infinity;
  for (const value of values) {
    if (value < minimum) minimum = value;
    if (value > maximum) maximum = value;
  }
  const range = Math.max(1e-6, maximum - minimum);
  const alpha = Buffer.alloc(values.length);
  for (let index = 0; index < values.length; index++) {
    const normalized = (values[index] - minimum) / range;
    const refined = Math.max(0, Math.min(1, (normalized - matteLow) / (matteHigh - matteLow)));
    alpha[index] = Math.round(refined * 255);
  }
  return alpha;
}

async function processFile(filename, inferenceSession) {
  const id = path.parse(filename).name;
  const source = path.join(sourceDir, filename);
  const target = path.join(outputDir, `${id}.png`);
  try {
    const metadata = await sharp(source).metadata();
    const { data: rgb } = await sharp(source)
      .removeAlpha()
      .resize(320, 320, { fit: "fill" })
      .raw()
      .toBuffer({ resolveWithObject: true });
    const result = await inferenceSession.run({ [inputName]: normalizedTensor(rgb) });
    const alpha320 = alphaFromOutput(result[outputName]);
    const { data: alpha, info: alphaInfo } = await sharp(alpha320, {
      raw: { width: 320, height: 320, channels: 1 },
    })
      .resize(metadata.width, metadata.height, { kernel: sharp.kernel.lanczos3 })
      .blur(0.35)
      .greyscale()
      .raw()
      .toBuffer({ resolveWithObject: true });
    const expectedAlphaBytes = metadata.width * metadata.height;
    if (alphaInfo.channels !== 1 || alpha.length !== expectedAlphaBytes) {
      throw new Error(
        `Unexpected alpha buffer ${alphaInfo.width}x${alphaInfo.height}x${alphaInfo.channels} (${alpha.length} bytes)`,
      );
    }
    const { data: sourceRgb, info: sourceInfo } = await sharp(source)
      .removeAlpha()
      .raw()
      .toBuffer({ resolveWithObject: true });
    if (sourceInfo.channels !== 3 || sourceRgb.length !== expectedAlphaBytes * 3) {
      throw new Error(`Unexpected source RGB buffer (${sourceRgb.length} bytes, ${sourceInfo.channels} channels)`);
    }
    // KBO profile portraits use a near-white studio background. Combining a
    // white-background key with the neural matte removes the broad white halo
    // that a low-resolution portrait model otherwise leaves around caps and shoulders.
    for (let index = 0; index < alpha.length; index++) {
      const offset = index * 3;
      const redDistance = 255 - sourceRgb[offset];
      const greenDistance = 255 - sourceRgb[offset + 1];
      const blueDistance = 255 - sourceRgb[offset + 2];
      const whiteDistance = Math.sqrt(
        redDistance * redDistance + greenDistance * greenDistance + blueDistance * blueDistance,
      );
      const keyedAlpha = Math.max(0, Math.min(1, (whiteDistance - 5) / 34));
      const verticalPosition = Math.floor(index / metadata.width) / Math.max(1, metadata.height - 1);
      const keyStrength = Math.max(0, Math.min(1, (0.82 - verticalPosition) / 0.14));
      const neuralAlpha = alpha[index];
      const combinedAlpha = Math.min(neuralAlpha, Math.round(keyedAlpha * 255));
      alpha[index] = Math.round(neuralAlpha * (1 - keyStrength) + combinedAlpha * keyStrength);
    }
    const rgbaMask = Buffer.alloc(alpha.length * 4, 255);
    for (let index = 0; index < alpha.length; index++) rgbaMask[index * 4 + 3] = alpha[index];
    const alphaPng = await sharp(rgbaMask, {
      raw: { width: metadata.width, height: metadata.height, channels: 4 },
    }).png().toBuffer();
    const transparent = await sharp(source)
      .ensureAlpha()
      .composite([{ input: alphaPng, blend: "dest-in" }])
      .png()
      .toBuffer();
    await sharp(transparent)
      .resize(targetWidth, targetHeight, {
        fit: "contain",
        kernel: sharp.kernel.lanczos3,
        background: { r: 0, g: 0, b: 0, alpha: 0 },
        withoutEnlargement: false,
      })
      .png({ compressionLevel: 6, adaptiveFiltering: false })
      .toFile(target);
    completed++;
  } catch (error) {
    failed++;
    process.stderr.write(`FAILED ${id}: ${error.message}\n`);
  }
  const processed = completed + failed;
  if (processed % 25 === 0 || processed === files.length) {
    process.stdout.write(`PROGRESS ${processed}/${files.length} completed=${completed} failed=${failed}\n`);
  }
}

const pendingFiles = files.filter((filename) => !fs.existsSync(path.join(outputDir, `${path.parse(filename).name}.png`)));
const skipped = files.length - pendingFiles.length;
completed = skipped;
let nextIndex = 0;
const concurrency = Math.max(1, Math.min(4, Number(process.env.PLAYER_PHOTO_WORKERS ?? 4)));

async function worker(inferenceSession) {
  while (true) {
    const index = nextIndex++;
    if (index >= pendingFiles.length) return;
    await processFile(pendingFiles[index], inferenceSession);
  }
}

process.stdout.write(`START total=${files.length} pending=${pendingFiles.length} skipped=${skipped} workers=${concurrency}\n`);
const sessions = [
  session,
  ...(await Promise.all(
    Array.from({ length: concurrency - 1 }, () => ort.InferenceSession.create(modelPath, sessionOptions)),
  )),
];
await Promise.all(sessions.map((inferenceSession) => worker(inferenceSession)));

process.stdout.write(`COMPLETE total=${files.length} completed=${completed} failed=${failed} skipped=${skipped}\n`);
if (failed) process.exitCode = 1;
