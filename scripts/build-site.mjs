import fs from "node:fs/promises";
import path from "node:path";
import { parse, serialize } from "parse5";

const root = path.resolve(import.meta.dirname, "..");
const source = path.join(root, "site");
const output = path.join(root, "dist", "catTrack");
const publicFiles = ["index.html", "styles.css", "app.js", "data.json"];
const imageExtensions = new Set([".webp", ".jpeg", ".jpg", ".png", ".svg", ".avif", ".gif", ".ico"]);

// The public build is intentionally a small allowlist. Raw recordings, source
// photos, analysis outputs, documentation, and local configuration stay out.
await fs.rm(path.join(root, "dist"), { recursive: true, force: true });
await fs.mkdir(path.join(output, "assets"), { recursive: true });
for (const filename of publicFiles) {
  const file = path.join(source, filename);
  if (!(await fs.lstat(file)).isFile()) throw new Error(`Expected a regular file: ${filename}`);
  await fs.copyFile(file, path.join(output, filename));
}
let imageCount = 0;
for (const entry of await fs.readdir(path.join(source, "assets"), { withFileTypes: true })) {
  if (entry.name.startsWith(".") || !imageExtensions.has(path.extname(entry.name).toLowerCase())) continue;
  if (!entry.isFile()) throw new Error(`Expected a regular image file: ${entry.name}`);
  await fs.copyFile(path.join(source, "assets", entry.name), path.join(output, "assets", entry.name));
  imageCount++;
}

// Canonical source also runs inside todd.sh. This deployment uses its checked-in
// copy and sends portfolio navigation back to todd.sh instead of its own root.
const document = parse(await fs.readFile(path.join(output, "index.html"), "utf8"));
const attr = (node, name) => node.attrs?.find((item) => item.name === name);
let returnLinks = 0;
let sharedLoaders = 0;
let hasBase = false;
function adapt(node) {
  if (node.tagName === "base" && attr(node, "href")?.value === "/catTrack/") hasBase = true;
  if (node.tagName === "a" && attr(node, "href")?.value === "/") {
    attr(node, "href").value = "https://www.todd.sh/";
    returnLinks++;
  }
  if (!node.childNodes) return;
  node.childNodes = node.childNodes.filter((child) => {
    const shared = child.tagName === "script" &&
      attr(child, "src")?.value === "/project-content-loader.js" &&
      attr(child, "data-project-content-id")?.value === "cat-track";
    if (shared) sharedLoaders++;
    return !shared;
  });
  for (const child of node.childNodes) adapt(child);
}
adapt(document);
if (!hasBase || returnLinks !== 2 || sharedLoaders !== 1) {
  throw new Error(`Unexpected source conventions: base=${hasBase}, portfolio links=${returnLinks}, shared loaders=${sharedLoaders}`);
}
await fs.writeFile(path.join(output, "index.html"), `${serialize(document)}\n`);
console.log(`Built dist/catTrack: ${publicFiles.length} page files and ${imageCount} images.`);
