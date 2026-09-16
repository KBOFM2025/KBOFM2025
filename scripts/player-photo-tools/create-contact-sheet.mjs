import fs from "node:fs";
import path from "node:path";
import process from "node:process";

import sharp from "sharp";

const sourceDir = path.resolve(process.argv[2] ?? "image/players/local/highres-samples");
const target = path.resolve(process.argv[3] ?? "tmp/player-photo-contact-sheet.png");
const selectedIds = new Set(
  (process.env.PLAYER_PHOTO_IDS ?? "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean),
);
const files = fs
  .readdirSync(sourceDir)
  .filter((name) => /^\d+\.(?:png|jpe?g|webp)$/i.test(name))
  .filter((name) => selectedIds.size === 0 || selectedIds.has(path.parse(name).name))
  .sort((left, right) => left.localeCompare(right, "en", { numeric: true }));
const columns = Math.min(3, Math.max(1, files.length));
const rows = Math.ceil(files.length / columns);
const tileWidth = 376;
const tileHeight = 510;
const composites = [];

for (let index = 0; index < files.length; index++) {
  const filename = files[index];
  const image = await sharp(path.join(sourceDir, filename))
    .resize(tileWidth, 472, { fit: "contain" })
    .png()
    .toBuffer();
  const label = Buffer.from(
    `<svg width="${tileWidth}" height="38"><rect width="100%" height="100%" fill="#111923"/><text x="16" y="25" font-family="Arial" font-size="19" fill="#e8f4ff">${path.parse(filename).name}</text></svg>`,
  );
  const left = (index % columns) * tileWidth;
  const top = Math.floor(index / columns) * tileHeight;
  composites.push({ input: image, left, top });
  composites.push({ input: label, left, top: top + 472 });
}

await sharp({
  create: {
    width: columns * tileWidth,
    height: rows * tileHeight,
    channels: 4,
    background: { r: 9, g: 18, b: 25, alpha: 1 },
  },
})
  .composite(composites)
  .png()
  .toFile(target);

process.stdout.write(`${target}\n`);
