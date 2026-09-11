import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import jsQR from "jsqr";
import { PNG } from "pngjs";

const postcards = [
  ["sbdc-postcard-zh.png", "https://sbdc.szlk.uk/about"],
  ["sbdc-postcard-en.png", "https://sbdc.szlk.uk/en/about"],
];

for (const [filename, expectedUrl] of postcards) {
  test(`${filename} 包含可解码且指向对应 About 页的二维码`, async () => {
    const png = PNG.sync.read(await readFile(new URL(`../public/postcards/${filename}`, import.meta.url)));
    const decoded = jsQR(new Uint8ClampedArray(png.data), png.width, png.height);
    assert.ok(decoded, "postcard QR code should be decodable from the final PNG");
    assert.equal(decoded.data, expectedUrl);
  });
}
