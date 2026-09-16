import fs from "node:fs";
import path from "node:path";
import process from "node:process";

import * as ort from "onnxruntime-node";
import sharp from "sharp";

const root = path.resolve(import.meta.dirname, "../..");
const sourceDir = path.resolve(root, process.argv[2] ?? "image/players/local/highres-originals");
const outputDir = path.resolve(root, process.argv[3] ?? "image/players/local/highres-cutouts");
const modelPath = path.resolve(
  root,
  process.argv[4] ?? "image/players/local/models/inspyrenet_base.onnx",
);
const targetWidth = 752;
const targetHeight = 944;
const workSize = 1800;
const modelSize = 1024;
const selectedIds = new Set(
  (process.env.PLAYER_PHOTO_IDS ?? "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean),
);

if (!fs.existsSync(modelPath)) throw new Error(`InSPyReNet model not found: ${modelPath}`);
if (!fs.existsSync(sourceDir)) throw new Error(`Source directory not found: ${sourceDir}`);
fs.mkdirSync(outputDir, { recursive: true });

const session = await ort.InferenceSession.create(modelPath, {
  executionProviders: ["cpu"],
  graphOptimizationLevel: "all",
});
const inputName = session.inputNames[0];
const outputName = session.outputNames[0];
const files = fs
  .readdirSync(sourceDir)
  .filter((name) => /^\d+\.(?:jpe?g|png|webp)$/i.test(name))
  .filter((name) => selectedIds.size === 0 || selectedIds.has(path.parse(name).name))
  .sort((left, right) => left.localeCompare(right, "en", { numeric: true }));
let completed = 0;
let failed = 0;

function normalizedTensor(rgb, width, height) {
  const pixels = width * height;
  const data = new Float32Array(3 * pixels);
  const mean = [0.485, 0.456, 0.406];
  const standardDeviation = [0.229, 0.224, 0.225];
  for (let index = 0; index < pixels; index++) {
    data[index] = (rgb[index * 3] / 255 - mean[0]) / standardDeviation[0];
    data[pixels + index] = (rgb[index * 3 + 1] / 255 - mean[1]) / standardDeviation[1];
    data[pixels * 2 + index] = (rgb[index * 3 + 2] / 255 - mean[2]) / standardDeviation[2];
  }
  return new ort.Tensor("float32", data, [1, 3, height, width]);
}

function alphaBounds(alpha, width, height) {
  let left = width;
  let top = height;
  let right = -1;
  let bottom = -1;
  for (let index = 0; index < alpha.length; index++) {
    if (alpha[index] < 10) continue;
    const x = index % width;
    const y = Math.floor(index / width);
    if (x < left) left = x;
    if (x > right) right = x;
    if (y < top) top = y;
    if (y > bottom) bottom = y;
  }
  if (right < left || bottom < top) throw new Error("No foreground found in alpha matte");

  const subjectWidth = right - left + 1;
  const subjectHeight = bottom - top + 1;
  const horizontalPad = Math.max(6, Math.round(subjectWidth * 0.035));
  const topPad = Math.max(6, Math.round(subjectHeight * 0.025));
  const bottomPad = Math.max(3, Math.round(subjectHeight * 0.01));
  left = Math.max(0, left - horizontalPad);
  right = Math.min(width - 1, right + horizontalPad);
  top = Math.max(0, top - topPad);
  bottom = Math.min(height - 1, bottom + bottomPad);
  return { left, top, width: right - left + 1, height: bottom - top + 1 };
}

async function inspyrenetAlpha(rgb, width, height) {
  const resizedRgb = await sharp(rgb, { raw: { width, height, channels: 3 } })
    .resize(modelSize, modelSize, { fit: "fill", kernel: sharp.kernel.lanczos3 })
    .raw()
    .toBuffer();
  const result = await session.run({
    [inputName]: normalizedTensor(resizedRgb, modelSize, modelSize),
  });
  const output = result[outputName];
  const expectedValues = modelSize * modelSize;
  if (output.data.length !== expectedValues) {
    throw new Error(`Unexpected InSPyReNet output ${output.dims.join("x")} (${output.data.length} values)`);
  }
  const matte = Buffer.alloc(expectedValues);
  for (let index = 0; index < output.data.length; index++) {
    const refined = Math.max(0, Math.min(1, output.data[index]));
    matte[index] = Math.round(refined * 255);
  }
  return sharp(matte, {
    raw: { width: modelSize, height: modelSize, channels: 1 },
  })
    .resize(width, height, { kernel: sharp.kernel.lanczos3 })
    .greyscale()
    .raw()
    .toBuffer();
}

function refineWhiteStudioBackground(rgb, alpha, width, height) {
  const connectedBackground = new Uint8Array(alpha.length);
  const queue = new Int32Array(alpha.length);
  let queueStart = 0;
  let queueEnd = 0;
  const floodHeight = Math.floor(height * 0.82);
  const whiteDistanceAt = (index) => {
    const offset = index * 3;
    const red = 255 - rgb[offset];
    const green = 255 - rgb[offset + 1];
    const blue = 255 - rgb[offset + 2];
    return Math.sqrt(red * red + green * green + blue * blue);
  };
  const enqueueBackground = (index) => {
    if (connectedBackground[index]) return;
    const y = Math.floor(index / width);
    if (y >= floodHeight || whiteDistanceAt(index) >= 58) return;
    connectedBackground[index] = 1;
    queue[queueEnd++] = index;
  };
  for (let x = 0; x < width; x++) enqueueBackground(x);
  for (let y = 0; y < floodHeight; y++) {
    enqueueBackground(y * width);
    enqueueBackground(y * width + width - 1);
  }
  while (queueStart < queueEnd) {
    const index = queue[queueStart++];
    const x = index % width;
    const y = Math.floor(index / width);
    if (x > 0) enqueueBackground(index - 1);
    if (x + 1 < width) enqueueBackground(index + 1);
    if (y > 0) enqueueBackground(index - width);
    if (y + 1 < floodHeight) enqueueBackground(index + width);
  }
  for (let index = 0; index < alpha.length; index++) {
    if (!connectedBackground[index]) continue;
    const keyedAlpha = Math.max(0, Math.min(1, (whiteDistanceAt(index) - 3) / 32));
    alpha[index] = Math.min(alpha[index], Math.round(keyedAlpha * 255));
  }
  return connectedBackground;
}

function composeRgba(rgb, alpha) {
  const rgba = Buffer.alloc(alpha.length * 4);
  for (let index = 0; index < alpha.length; index++) {
    const sourceOffset = index * 3;
    const targetOffset = index * 4;
    const opacity = alpha[index] / 255;
    const shouldRecoverWhiteEdge = opacity > 0.015 && opacity < 0.995;
    for (let channel = 0; channel < 3; channel++) {
      const sourceValue = rgb[sourceOffset + channel];
      const recovered = shouldRecoverWhiteEdge
        ? (sourceValue - 255 * (1 - opacity)) / opacity
        : sourceValue;
      rgba[targetOffset + channel] = Math.round(Math.max(0, Math.min(255, recovered)));
    }
    rgba[targetOffset + 3] = alpha[index];
  }
  return rgba;
}

async function renderFramedCutout(rgba, width, height, target) {
  const alpha = Buffer.alloc(width * height);
  for (let index = 0; index < alpha.length; index++) alpha[index] = rgba[index * 4 + 3];
  const bounds = alphaBounds(alpha, width, height);
  const cropped = await sharp(rgba, { raw: { width, height, channels: 4 } })
    .extract(bounds)
    .png()
    .toBuffer();
  const maximumWidth = Math.round(targetWidth * 0.96);
  const maximumHeight = Math.round(targetHeight * 0.985);
  const { data: resized, info } = await sharp(cropped)
    .resize(maximumWidth, maximumHeight, {
      fit: "inside",
      kernel: sharp.kernel.lanczos3,
      withoutEnlargement: false,
    })
    .png()
    .toBuffer({ resolveWithObject: true });
  const left = Math.round((targetWidth - info.width) / 2);
  const top = targetHeight - info.height;
  await sharp({
    create: {
      width: targetWidth,
      height: targetHeight,
      channels: 4,
      background: { r: 0, g: 0, b: 0, alpha: 0 },
    },
  })
    .composite([{ input: resized, left, top }])
    .png({ compressionLevel: 7, adaptiveFiltering: true })
    .toFile(target);
}

for (const filename of files) {
  const id = path.parse(filename).name;
  const source = path.join(sourceDir, filename);
  const target = path.join(outputDir, `${id}.png`);
  try {
    const { data: workRgba, info } = await sharp(source)
      .rotate()
      .resize(workSize, workSize, {
        fit: "inside",
        withoutEnlargement: true,
        kernel: sharp.kernel.lanczos3,
      })
      .ensureAlpha()
      .raw()
      .toBuffer({ resolveWithObject: true });
    if (info.channels !== 4) throw new Error(`Unexpected working channels: ${info.channels}`);

    const pixels = info.width * info.height;
    const rgb = Buffer.alloc(pixels * 3);
    const embeddedAlpha = Buffer.alloc(pixels);
    let transparentPixels = 0;
    for (let index = 0; index < pixels; index++) {
      rgb[index * 3] = workRgba[index * 4];
      rgb[index * 3 + 1] = workRgba[index * 4 + 1];
      rgb[index * 3 + 2] = workRgba[index * 4 + 2];
      embeddedAlpha[index] = workRgba[index * 4 + 3];
      if (embeddedAlpha[index] < 250) transparentPixels++;
    }

    let rgba;
    if (transparentPixels > pixels * 0.01) {
      rgba = workRgba;
    } else {
      const alpha = await inspyrenetAlpha(rgb, info.width, info.height);
      refineWhiteStudioBackground(rgb, alpha, info.width, info.height);
      rgba = composeRgba(rgb, alpha);
    }
    await renderFramedCutout(rgba, info.width, info.height, target);
    completed++;
  } catch (error) {
    failed++;
    process.stderr.write(`FAILED ${id}: ${error.message}\n`);
  }
  if ((completed + failed) % 25 === 0 || completed + failed === files.length) {
    process.stdout.write(
      `PROGRESS ${completed + failed}/${files.length} completed=${completed} failed=${failed}\n`,
    );
  }
}

process.stdout.write(`COMPLETE total=${files.length} completed=${completed} failed=${failed}\n`);
if (failed) process.exitCode = 1;
