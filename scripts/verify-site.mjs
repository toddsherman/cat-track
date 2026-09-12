import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { once } from "node:events";
import { parse } from "parse5";
import { createSiteServer } from "./serve-site.mjs";

const root = path.resolve(import.meta.dirname, "..", "dist");
const pageRoot = path.join(root, "catTrack");
const html = await fs.readFile(path.join(pageRoot, "index.html"), "utf8");
const document = parse(html);
const attr = (node, name) => node.attrs?.find((item) => item.name === name)?.value;
const references = new Set();
const ids = new Set();
let portfolioLinks = 0;
let scripts = 0;
function inspect(node) {
  const id = attr(node, "id");
  if (id) {
    assert(!ids.has(id), `Duplicate HTML ID: ${id}`);
    ids.add(id);
  }
  if (node.tagName === "a" && attr(node, "href") === "https://www.todd.sh/") portfolioLinks++;
  if (node.tagName === "script") {
    scripts++;
    assert.equal(attr(node, "src"), "app.js", "Standalone page must not depend on todd.sh's CMS runtime");
  }
  assert.notEqual(node.tagName, "video", "The removed video must not return to the public page");
  if (node.tagName !== "base") {
    for (const name of ["src", "href"]) {
      const ref = attr(node, name);
      if (ref) references.add(ref);
    }
  }
  const srcset = attr(node, "srcset");
  if (srcset) for (const part of srcset.split(",")) references.add(part.trim().split(/\s+/)[0]);
  for (const child of node.childNodes ?? []) inspect(child);
}
inspect(document);
assert.equal(portfolioLinks, 2);
assert.equal(scripts, 1);
const localFiles = new Set(["/catTrack/index.html", "/catTrack/data.json"]);
for (const ref of references) {
  const url = new URL(ref, "https://example.test/catTrack/");
  if (url.origin !== "https://example.test") continue;
  if (url.hash) assert(ids.has(decodeURIComponent(url.hash.slice(1))), `Unknown fragment: ${ref}`);
  if (ref.startsWith("#")) continue;
  const file = path.resolve(root, `.${url.pathname}`);
  assert(file.startsWith(`${root}${path.sep}`), `Reference escapes output root: ${ref}`);
  assert((await fs.stat(file)).isFile(), `Missing local asset: ${ref}`);
  localFiles.add(url.pathname);
}
const files = await fs.readdir(root, { recursive: true });
assert(files.every((file) => !file.split(path.sep).some((part) => part.startsWith("."))), "Hidden files must not be deployed");
assert(files.every((file) => !/\.(?:md|cwa|mov|mp4|py|pyc|env|toml|csv|gz)$/i.test(file)), "Private source or removed video in public output");

const data = JSON.parse(await fs.readFile(path.join(pageRoot, "data.json"), "utf8"));
assert.equal(data.days.length, 6);
assert.equal(data.overlap.runWindow.startMinute, 0);
assert.equal(data.overlap.runWindow.endMinute, 1440);
for (const day of data.days) {
  assert.equal(day.movement5s.length, 17280, `${day.date}: full five-second movement series`);
  for (let hour=0;hour<24;hour++) {
    const valid = day.movement5s.slice(hour*720,(hour+1)*720).filter(pair=>pair[0]!==null);
    for (const [column,cat] of [[0,"peach"],[1,"toast"]]) {
      assert(valid.every(pair=>Number.isFinite(pair[column]) && pair[column]>=0));
      const mean = valid.reduce((sum,pair)=>sum+pair[column],0)/valid.length;
      assert(Math.abs(mean-day.hourly[hour][cat])<=0.0051, `${day.date}/${hour}/${cat}: detailed data changed hourly mean`);
    }
  }
  assert.equal(day.timeline.length, 288, `${day.date}: expected every five-minute interval of 24 hours`);
  day.timeline.forEach((bin, index) => assert.equal(bin.minute, index * 5));
  const runs = data.overlap.runs.find((item) => item.date === day.date);
  assert(runs, `Missing rest timeline: ${day.date}`);
  let cursor = 0, bothMinutes = 0, observedMinutes = 0;
  for (const [start, end, state] of runs.segments) {
    assert(Math.abs(start - cursor) < 0.000002 && end > start, `${day.date}: rest timeline has a gap or overlap`);
    assert([0, 1, 2, 3, 4].includes(state), `${day.date}: unknown rest state`);
    for(let bin=Math.round(start*12);bin<Math.round(end*12);bin++) {
      assert.equal(day.movement5s[bin][0]===null,state===4, "Movement gap must match missing rest data");
      assert.equal(day.movement5s[bin][1]===null,state===4, "Both cats must share the missing-data mask");
    }
    if (state !== 4) observedMinutes += end - start;
    if (state === 3) bothMinutes += end - start;
    cursor = end;
  }
  assert.equal(cursor, 1440);
  const summary = data.daily.find((item) => item.date === day.date);
  assert(Math.abs((bothMinutes / observedMinutes) * 24 - summary.bothRestHours24h) < 0.0001,
    `${day.date}: shared rest total does not match its plotted intervals`);
}

// Exercise the same static routing used by the local preview, including missing
// assets. A broken URL must return a 404 rather than an apparently valid page.
const server = createSiteServer(root);
server.listen(0, "127.0.0.1");
await once(server, "listening");
const origin = `http://127.0.0.1:${server.address().port}`;
try {
  for (const route of ["/", "/catTrack", "/catTrack/"]) {
    const response = await fetch(`${origin}${route}`);
    assert.equal(response.status, 200, route);
    assert.equal(await response.text(), html, `${route}: wrong entry point`);
  }
  for (const route of localFiles) {
    const response = await fetch(`${origin}${route}`);
    assert.equal(response.status, 200, `Asset route failed: ${route}`);
    await response.arrayBuffer();
  }
  for (const route of ["/missing", "/catTrack/missing.js", "/catTrack/assets/README.md", "/.env", "/catTrack/%2e%2e%2f%2e%2e%2fpackage.json"]) {
    const response = await fetch(`${origin}${route}`);
    assert.equal(response.status, 404, `Nonpublic route must not be served: ${route}`);
    await response.text();
  }
  const head = await fetch(`${origin}/catTrack/app.js`, { method: "HEAD" });
  assert.equal(head.status, 200);
  assert.match(head.headers.get("content-type"), /javascript/);
  assert.equal(await head.text(), "");
} finally {
  await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
}
console.log(`Verified standalone routes, ${localFiles.size} linked assets, and six complete 24-hour rest timelines.`);
