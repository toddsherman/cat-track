import fs from "node:fs";
import path from "node:path";
import { parse } from "parse5";

// Only this project's public directory, thumbnail, and content seed are written.
// This command neither publishes a site nor imports anything into Sanity.
const projectRoot = path.resolve(import.meta.dirname, "..");
const toddRoot = path.resolve(
  process.argv[2] ?? path.join(projectRoot, "..", "Todd dot sh"),
);
const siteRoot = path.join(projectRoot, "site");
const thumbnail = "cat-track-palette.webp";
const required = [
  path.join(siteRoot, "index.html"),
  path.join(siteRoot, "styles.css"),
  path.join(siteRoot, "app.js"),
  path.join(siteRoot, "data.json"),
  path.join(siteRoot, "assets", thumbnail),
  path.join(toddRoot, "app", "projects.ts"),
  path.join(toddRoot, "public", "project-content-loader.js"),
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
const copy = [];
const keys = new Set();
const documentKeys = new Set();
let title;
let description;
let hasBase = false;
let hasLoader = false;

function visit(node) {
  if (node.tagName === "title") title = text(node);
  if (node.tagName === "meta" && attr(node, "name") === "description") {
    description = attr(node, "content");
  }
  if (node.tagName === "base" && attr(node, "href") === "/catTrack/") hasBase = true;
  if (node.tagName === "script" &&
      attr(node, "data-project-content-id") === "cat-track" &&
      attr(node, "src") === "/project-content-loader.js") hasLoader = true;

  const key = attr(node, "data-sanity-copy");
  if (key) {
    const documentKey = key.replaceAll("_", "-");
    if (!/^[a-zA-Z][a-zA-Z0-9_-]*$/.test(key) || keys.has(key) || documentKeys.has(documentKey)) {
      throw new Error(`Invalid or duplicate copy slot: ${key}`);
    }
    if ((node.childNodes ?? []).some((child) => child.tagName)) {
      throw new Error(`Copy slot ${key} must contain plain text only.`);
    }
    const value = text(node);
    if (!value) throw new Error(`Copy slot ${key} is empty.`);
    keys.add(key);
    documentKeys.add(documentKey);
    copy.push({
      _key: documentKey,
      _type: "copySlot",
      key,
      label: attr(node, "data-sanity-label") ?? `${node.tagName}: ${value.slice(0, 64)}`,
      value,
    });
  }
  for (const child of node.childNodes ?? []) visit(child);
}
visit(document);

if (!hasBase || !hasLoader || !title || !description || !copy.length) {
  throw new Error("Cat Track needs its base URL, shared content loader, SEO metadata, and copy slots before syncing.");
}

const seed = {
  _id: "page-cat-track",
  _type: "projectPage",
  title: "Cat Track",
  contentId: "cat-track",
  path: "/catTrack",
  // The shared loader adds the site-name suffix itself.
  seoTitle: title.replace(/\s+[—|]\s+(?:Todd Sherman|todd\.sh)$/i, ""),
  seoDescription: description,
  copy,
};

const publicRoot = path.join(toddRoot, "public");
const contentRoot = path.join(toddRoot, "sanity", "content");
fs.mkdirSync(path.join(publicRoot, "project-previews"), { recursive: true });
fs.mkdirSync(contentRoot, { recursive: true });
fs.cpSync(siteRoot, path.join(publicRoot, "catTrack"), {
  recursive: true,
  filter: (file) => !path.basename(file).startsWith(".") && path.extname(file) !== ".md",
});
fs.copyFileSync(
  path.join(siteRoot, "assets", thumbnail),
  path.join(publicRoot, "project-previews", thumbnail),
);
fs.writeFileSync(
  path.join(contentRoot, "cat-track.json"),
  `${JSON.stringify(seed, null, 2)}\n`,
);
console.log(`Synced Cat Track to ${path.join(publicRoot, "catTrack")}`);
console.log(`Generated ${copy.length} fixed copy slots in sanity/content/cat-track.json`);
