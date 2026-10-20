// 把 poster.html 渲染成预览图、印刷 JPG 和 1:1 PDF。
//   node render.mjs            -> poster-preview.png (2000px 宽)
//   node render.mjs --print    -> 另外输出 poster-print-72dpi.jpg（1:1）和 poster-1to10-500x280mm.pdf
// PDF 按喷绘行业惯例做 1:10：按 5000mm 原尺寸导出时 Chromium 生成的 PDF 渲染会出错（整页变成金色渐变），
// 500mm / 2000mm 都正常。矢量文件，印刷时放大 10 倍即可。
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");

const dir = path.dirname(fileURLToPath(import.meta.url));
const url = "file://" + path.join(dir, "poster.html");
const print = process.argv.includes("--print");

const browser = await chromium.launch();

async function shot(scale, out) {
  const page = await browser.newPage({ viewport: { width: 5000, height: 2800 }, deviceScaleFactor: scale });
  await page.goto(url);
  await page.evaluate(() => document.fonts.ready);
  const type = out.endsWith(".jpg") ? { type: "jpeg", quality: 92 } : {};
  await page.screenshot({ path: path.join(dir, out), clip: { x: 0, y: 0, width: 5000, height: 2800 }, ...type });
  await page.close();
  console.log("wrote", out);
}

await shot(0.4, "poster-preview.png");

if (print) {
  // 72dpi：5000mm = 196.85in -> 14173px
  await shot(14173 / 5000, "poster-print-72dpi.jpg");
  const page = await browser.newPage({ viewport: { width: 5000, height: 2800 } });
  await page.goto(url);
  await page.evaluate(() => document.fonts.ready);
  await page.pdf({ path: path.join(dir, "poster-1to10-500x280mm.pdf"), width: "500mm", height: "280mm", printBackground: true, pageRanges: "1" });
  console.log("wrote poster-1to10-500x280mm.pdf");
}

await browser.close();
