import fs from "node:fs";
import path from "node:path";
import process from "node:process";

import sharp from "sharp";

const root = path.resolve(import.meta.dirname, "../..");
const sourceDir = path.resolve(
  root,
  process.argv[2] ?? "image/players/local/highres-originals",
);
const outputDir = path.resolve(
  root,
  process.argv[3] ?? "image/players/local/game-ready",
);
const files = fs
  .readdirSync(sourceDir)
  .filter((name) => /^\d+\.(?:jpe?g|png|webp)$/i.test(name))
  .sort((left, right) => left.localeCompare(right, "en", { numeric: true }));

fs.mkdirSync(outputDir, { recursive: true });
let completed = 0;
let failed = 0;
let nextIndex = 0;
const concurrency = 4;

async function preparePhoto(filename) {
  const source = path.join(sourceDir, filename);
  const extension = path.extname(filename).toLowerCase();
  const targetExtension = extension === ".png" ? ".png" : ".jpg";
  const target = path.join(outputDir, `${path.parse(filename).name}${targetExtension}`);
  try {
    if (fs.existsSync(target)) {
      completed++;
      return;
    }
    let pipeline = sharp(source)
      .rotate()
      .resize(1600, 1600, {
        fit: "inside",
        withoutEnlargement: true,
        kernel: sharp.kernel.lanczos3,
      });
    pipeline = targetExtension === ".png"
      ? pipeline.png({ compressionLevel: 7, adaptiveFiltering: true })
      : pipeline.jpeg({ quality: 92, chromaSubsampling: "4:4:4", mozjpeg: true });
    await pipeline.toFile(target);
    completed++;
  } catch (error) {
    failed++;
    process.stderr.write(`FAILED ${filename}: ${error.message}\n`);
  }
}

async function worker() {
  while (nextIndex < files.length) {
    const filename = files[nextIndex++];
    await preparePhoto(filename);
    const processed = completed + failed;
    if (processed % 100 === 0 || processed === files.length) {
      process.stdout.write(
        `PROGRESS ${processed}/${files.length} completed=${completed} failed=${failed}\n`,
      );
    }
  }
}

await Promise.all(Array.from({ length: concurrency }, () => worker()));

process.stdout.write(`COMPLETE total=${files.length} completed=${completed} failed=${failed}\n`);
if (failed) process.exitCode = 1;
