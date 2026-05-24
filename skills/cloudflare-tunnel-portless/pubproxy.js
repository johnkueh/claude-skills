#!/usr/bin/env node
// Host-preserving dispatcher that sits in front of portless.
//
// Replaces Caddy in the cloudflare-tunnel-portless chain. Caddy was
// rewriting the public Host header (`<name>.<TLD>` -> `<name>.localhost`)
// so portless could dispatch by its hardcoded `.localhost` matcher;
// that rewrite breaks downstream URL building (Clerk dev handshake,
// metadataBase, redirect URLs, etc.).
//
// pubproxy reads portless's own routes file directly, looks up the
// underlying dev-server port by name, and forwards to it WITHOUT
// touching the Host header. Local browsing via `<name>.localhost:1355`
// (portless on its native path) is unaffected.
//
// Env:
//   PUBPROXY_PORT   listen port (default 1354)
//   PUBPROXY_TLD    public TLD to strip (default example.dev)
//   PUBPROXY_ROUTES portless routes.json path (default ~/.portless/routes.json)

const http = require("node:http");
const net = require("node:net");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");

const PORT = Number.parseInt(process.env.PUBPROXY_PORT ?? "1354", 10);
const TLD = process.env.PUBPROXY_TLD ?? "example.dev";
const ROUTES =
  process.env.PUBPROXY_ROUTES ??
  path.join(os.homedir(), ".portless", "routes.json");

const TLD_SUFFIX = "." + TLD;

function readRoutes() {
  try {
    return JSON.parse(fs.readFileSync(ROUTES, "utf8"));
  } catch {
    return [];
  }
}

function lookupPort(hostHeader) {
  const host = (hostHeader || "").split(":")[0].toLowerCase();
  if (!host.endsWith(TLD_SUFFIX)) return null;
  const name = host.slice(0, -TLD_SUFFIX.length);
  if (!name) return null;
  const target = name + ".localhost";
  const r = readRoutes().find((r) => r.hostname === target);
  return r ? r.port : null;
}

const server = http.createServer((req, res) => {
  const port = lookupPort(req.headers.host);
  if (!port) {
    res.writeHead(404, { "content-type": "text/plain" });
    res.end(`pubproxy: no portless route for host "${req.headers.host}"\n`);
    return;
  }
  const upstream = http.request(
    {
      host: "127.0.0.1",
      port,
      method: req.method,
      path: req.url,
      headers: req.headers,
    },
    (upRes) => {
      const h = { ...upRes.headers };
      h["cache-control"] = "no-store, must-revalidate";
      delete h["etag"];
      delete h["last-modified"];
      res.writeHead(upRes.statusCode || 502, h);
      upRes.pipe(res);
    },
  );
  upstream.on("error", (err) => {
    if (!res.headersSent) res.writeHead(502, { "content-type": "text/plain" });
    res.end(`pubproxy: upstream error: ${err.message}\n`);
  });
  req.pipe(upstream);
});

server.on("upgrade", (req, sock, head) => {
  const port = lookupPort(req.headers.host);
  if (!port) {
    sock.end("HTTP/1.1 404 Not Found\r\n\r\n");
    return;
  }
  const upstream = net.connect(port, "127.0.0.1", () => {
    const headers = Object.entries(req.headers)
      .map(([k, v]) => `${k}: ${v}`)
      .join("\r\n");
    upstream.write(
      `${req.method} ${req.url} HTTP/1.1\r\n${headers}\r\n\r\n`,
    );
    if (head && head.length) upstream.write(head);
    sock.pipe(upstream).pipe(sock);
  });
  upstream.on("error", () => sock.destroy());
  sock.on("error", () => upstream.destroy());
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(
    `pubproxy listening on :${PORT}, stripping .${TLD}, routes from ${ROUTES}`,
  );
});
