// Type-check the viewer scripts that live inline in the replay templates.
//
// The exported replays must stay single self-contained HTML files that open from
// file://, so the scripts cannot move into separate modules or a bundler. This
// check extracts each template's inline script into a temporary file, runs the
// TypeScript compiler over it in checkJs mode, and maps every diagnostic back to
// the original HTML line. It never writes to the templates or to the exports.
"use strict";
const assert = require("node:assert");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const root = path.join(__dirname, "..");
const templates = path.join(root, "robot_reel");
const environment = path.join(__dirname, "viewer-env.d.ts");

// Kept beside the extraction so the checked configuration cannot drift from it.
const CONFIG = {
  compilerOptions: {
    target: "ES2022",
    lib: ["ES2022", "DOM", "DOM.Iterable"],
    module: "ESNext",
    moduleDetection: "force",
    allowJs: true,
    checkJs: true,
    noEmit: true,
    strict: false,
    noImplicitAny: false,
    noUnusedLocals: true,
    noFallthroughCasesInSwitch: true,
    types: [],
  },
  include: ["*.js", "viewer-env.d.ts"],
};

/** Extract the single element-scoped `<script>` block, with its HTML line offset. */
function extract(html, name) {
  const open = "<script>\n";
  const matches = [...html.matchAll(/<script>\n/g)];
  assert.strictEqual(matches.length, 1,
    `${name}: expected exactly one inline <script> block, found ${matches.length}`);
  const start = matches[0].index + open.length;
  const end = html.indexOf("</script>", start);
  assert.ok(end > start, `${name}: unterminated inline <script> block`);
  // JSON payload blocks carry attributes, so they are never picked up here.
  return { source: html.slice(start, end), offset: html.slice(0, start).split("\n").length - 1 };
}

function main() {
  const files = fs.readdirSync(templates).filter(name => name.endsWith(".html")).sort();
  assert.ok(files.length > 0, "no replay templates found");
  const workspace = fs.mkdtempSync(path.join(os.tmpdir(), "robot-reel-viewer-js-"));
  const offsets = new Map();
  try {
    for (const file of files) {
      const { source, offset } = extract(fs.readFileSync(path.join(templates, file), "utf8"), file);
      const script = file.replace(/\.html$/, ".js");
      fs.writeFileSync(path.join(workspace, script), source);
      offsets.set(script, { offset, file });
    }
    fs.copyFileSync(environment, path.join(workspace, "viewer-env.d.ts"));
    fs.writeFileSync(path.join(workspace, "tsconfig.json"), JSON.stringify(CONFIG, null, 2));

    const tsc = path.join(root, "node_modules", "typescript", "bin", "tsc");
    assert.ok(fs.existsSync(tsc), "typescript is not installed; run npm ci");
    const result = spawnSync(process.execPath, [tsc, "-p", workspace], { encoding: "utf8" });
    const output = `${result.stdout || ""}${result.stderr || ""}`;
    // Rewrite "chaos.js(160,42): error TS…" as "robot_reel/chaos.html:319: error TS…".
    const report = output.replace(/(?:[^\s(]*[/\\])?([\w.-]+\.js)\((\d+),(\d+)\)/g, (match, script, line, column) => {
      const source = offsets.get(script);
      return source ? `robot_reel/${source.file}:${Number(line) + source.offset}:${column}` : match;
    });
    if (result.status !== 0) {
      process.stderr.write(report.trim() + "\n");
      console.error(`\nViewer script check failed for ${files.length} templates.`);
      process.exit(1);
    }
    console.log(`Viewer scripts type-check: ${files.length} templates, ` +
      `${[...offsets.keys()].join(", ")}`);
  } finally {
    fs.rmSync(workspace, { recursive: true, force: true });
  }
}

main();
