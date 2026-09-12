import fs from "node:fs/promises";
import http from "node:http";
import path from "node:path";
import { pathToFileURL } from "node:url";

const defaultRoot = path.resolve(import.meta.dirname, "..", "dist");
const contentTypes = {
  ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8", ".json": "application/json; charset=utf-8",
  ".webp": "image/webp", ".jpeg": "image/jpeg", ".jpg": "image/jpeg",
  ".png": "image/png", ".svg": "image/svg+xml", ".avif": "image/avif",
  ".gif": "image/gif", ".ico": "image/x-icon",
};

export function createSiteServer(outputRoot = defaultRoot) {
  const root = path.resolve(outputRoot);
  return http.createServer(async (request, response) => {
    const fail = (status, message) => {
      response.writeHead(status, { "Content-Type": "text/plain; charset=utf-8" });
      response.end(request.method === "HEAD" ? undefined : message);
    };
    if (!["GET", "HEAD"].includes(request.method)) {
      response.setHeader("Allow", "GET, HEAD");
      return fail(405, "Method not allowed");
    }
    let pathname;
    try {
      pathname = decodeURIComponent(new URL(request.url, "http://localhost").pathname);
    } catch {
      return fail(400, "Invalid path");
    }
    if (pathname.includes("\0") || pathname.includes("\\") || pathname.split("/").some((part) => part.startsWith("."))) {
      return fail(404, "Not found");
    }
    if (["/", "/catTrack", "/catTrack/"].includes(pathname)) pathname = "/catTrack/index.html";
    const filename = path.resolve(root, `.${pathname}`);
    if (!filename.startsWith(`${root}${path.sep}`)) return fail(404, "Not found");
    try {
      const actualPath = await fs.realpath(filename);
      if (!actualPath.startsWith(`${root}${path.sep}`) || !(await fs.stat(actualPath)).isFile()) {
        return fail(404, "Not found");
      }
      const body = await fs.readFile(actualPath);
      response.writeHead(200, {
        "Content-Type": contentTypes[path.extname(actualPath).toLowerCase()] ?? "application/octet-stream",
        "Content-Length": body.length,
        "Cache-Control": "no-cache",
        "X-Content-Type-Options": "nosniff",
      });
      response.end(request.method === "HEAD" ? undefined : body);
    } catch (error) {
      if (["ENOENT", "ENOTDIR"].includes(error.code)) return fail(404, "Not found");
      console.error(error);
      fail(500, "Unable to read file");
    }
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  await fs.access(path.join(defaultRoot, "catTrack", "index.html"));
  const port = Number(process.env.PORT ?? 3000);
  if (!Number.isInteger(port) || port < 0 || port > 65535) throw new Error("PORT must be a valid port number");
  const host = process.env.HOST ?? "127.0.0.1";
  const server = createSiteServer();
  server.listen(port, host, () => console.log(`Cat Track: http://${host}:${server.address().port}`));
}
