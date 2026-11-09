import fs from "node:fs";
import path from "node:path";
import { parse } from "parse5";

// Only this project's public directory and thumbnail are written.
// This command does not publish or deploy anything.
const projectRoot = path.resolve(import.meta.dirname, "..");
const toddRoot = path.resolve(
  process.argv[2] ?? path.join(projectRoot, "..", "Todd dot sh"),
);
const siteRoot = path.join(projectRoot, "site");
const thumbnail = "cat-track-palette-v2.webp";
const required = [
  path.join(siteRoot, "index.html"),
  path.join(siteRoot, "styles.css"),
  path.join(siteRoot, "app.js"),
  path.join(siteRoot, "data.json"),
  path.join(siteRoot, "assets", thumbnail),
  path.join(toddRoot, "app", "projects.ts"),
];

for (const file of required) {
  if (!fs.existsSync(file)) throw new Error(`Missing required file: ${file}`);
}

const html = fs.readFileSync(path.join(siteRoot, "index.html"), "utf8");
const document = parse(html);
const attr = (node, name) => node.attrs?.find((item) => item.name === name)?.value;
const text = (node) => (node.childNodes ?? [])
  .map((child) => child.nodeName === "#text" ? child.value : text(child))
  .join("").trim();
let title;
let description;
let hasBase = false;

function visit(node) {
  if (node.tagName === "title") title = text(node);
  if (node.tagName === "meta" && attr(node, "name") === "description") {
    description = attr(node, "content");
  }
  if (node.tagName === "base" && attr(node, "href") === "/catTrack/") hasBase = true;
  for (const child of node.childNodes ?? []) visit(child);
}
visit(document);

if (!hasBase || !title || !description) {
  throw new Error("Cat Track needs its base URL and SEO metadata before syncing.");
}

const publicRoot = path.join(toddRoot, "public");
fs.mkdirSync(path.join(publicRoot, "project-previews"), { recursive: true });
fs.cpSync(siteRoot, path.join(publicRoot, "catTrack"), {
  recursive: true,
  filter: (file) => !path.basename(file).startsWith(".") && path.extname(file) !== ".md",
});
fs.copyFileSync(
  path.join(siteRoot, "assets", thumbnail),
  path.join(publicRoot, "project-previews", thumbnail),
);
console.log(`Synced Cat Track to ${path.join(publicRoot, "catTrack")}`);
