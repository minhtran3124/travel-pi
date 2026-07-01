#!/usr/bin/env node
// Render WORKFLOW_DIAGRAM.md's Mermaid blocks into a self-contained, zoomable
// HTML page (SVG inlined — works offline). Titles are taken from each block's
// nearest preceding "## " heading, so the output stays in sync with the doc.
//
// Usage:  node scripts/render-workflow-diagram.mjs [input.md] [output.html]
// Deps:   Node >= 22 and npx (pulls @mermaid-js/mermaid-cli on first run).

import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const IN = process.argv[2] ?? "WORKFLOW_DIAGRAM.md";
const OUT = process.argv[3] ?? "WORKFLOW_DIAGRAM.html";

const md = readFileSync(IN, "utf8");

// Collect each mermaid block together with the heading that precedes it.
const blocks = [];
const re = /```mermaid\n([\s\S]*?)```/g;
let m;
while ((m = re.exec(md)) !== null) {
  const before = md.slice(0, m.index);
  const heads = [...before.matchAll(/^##\s+(.+)$/gm)];
  const title = heads.length ? heads[heads.length - 1][1].trim() : `Diagram ${blocks.length + 1}`;
  blocks.push({ title, src: m[1] });
}
if (blocks.length === 0) {
  console.error(`No \`\`\`mermaid blocks found in ${IN}`);
  process.exit(1);
}

const tmp = mkdtempSync(join(tmpdir(), "wfdiag-"));
const cfg = join(tmp, "mmd.json");
writeFileSync(
  cfg,
  JSON.stringify({
    theme: "default",
    themeVariables: { fontSize: "16px" },
    flowchart: { useMaxWidth: false, htmlLabels: true, nodeSpacing: 45, rankSpacing: 55 },
  }),
);

const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

let sections = "";
blocks.forEach((b, i) => {
  const mmd = join(tmp, `b${i}.mmd`);
  const svgPath = join(tmp, `b${i}.svg`);
  writeFileSync(mmd, b.src);
  execFileSync(
    "npx",
    ["-y", "@mermaid-js/mermaid-cli@latest", "-c", cfg, "-b", "transparent", "-i", mmd, "-o", svgPath],
    { stdio: ["ignore", "ignore", "inherit"] },
  );
  const svg = readFileSync(svgPath, "utf8").replace(/<\?xml[^>]*\?>/, "");
  sections += `<section><h2>${esc(b.title)}</h2><div class="diagram">${svg}</div></section>\n`;
  console.log(`rendered: ${b.title}`);
});

const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Travel Agent — Workflow Diagrams</title>
<style>
  :root{ --bg:#0f1115; --panel:#171a21; --ink:#e6e8ec; --muted:#9aa3b2; --line:#2a2f3a; --accent:#8ad14b; }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
  header{position:sticky;top:0;z-index:5;background:rgba(15,17,21,.9);backdrop-filter:blur(8px);border-bottom:1px solid var(--line);padding:14px 22px}
  header h1{margin:0;font-size:17px;font-weight:650}
  header p{margin:3px 0 0;color:var(--muted);font-size:13px}
  main{max-width:1200px;margin:0 auto;padding:22px}
  section{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px 18px 20px;margin:0 0 22px}
  section h2{margin:0 0 12px;font-size:15px;font-weight:600;color:var(--accent);letter-spacing:.2px}
  .diagram{overflow:auto;border:1px dashed var(--line);border-radius:8px;padding:14px;background:#fbfbfd;text-align:center}
  .diagram svg{max-width:100%;height:auto;cursor:zoom-in}
  .hint{color:var(--muted);font-size:12px;margin:6px 2px 0}
  #lb{position:fixed;inset:0;background:rgba(0,0,0,.85);display:none;align-items:center;justify-content:center;z-index:50;overflow:auto;padding:24px}
  #lb.open{display:flex}
  #lb svg{max-width:none;height:auto;background:#fff;border-radius:8px;padding:20px}
  #lb .close{position:fixed;top:16px;right:22px;color:#fff;font-size:26px;cursor:pointer;user-select:none}
</style></head>
<body>
<header><h1>Travel Agent — Workflow Diagrams</h1>
<p>Generated from ${esc(IN)} · click any diagram to zoom · scroll inside a box to pan</p></header>
<main>${sections}<p class="hint">Self-contained (SVG inlined) — works offline. Regenerate with: make diagram</p></main>
<div id="lb"><span class="close">&times;</span><div id="lbc"></div></div>
<script>
  const lb=document.getElementById("lb"),lbc=document.getElementById("lbc");
  document.querySelectorAll(".diagram svg").forEach(s=>{
    s.addEventListener("click",()=>{lbc.innerHTML="";lbc.appendChild(s.cloneNode(true));lb.classList.add("open");});
  });
  const close=()=>lb.classList.remove("open");
  lb.addEventListener("click",e=>{if(e.target===lb||e.target.classList.contains("close"))close();});
  document.addEventListener("keydown",e=>{if(e.key==="Escape")close();});
</script>
</body></html>`;

writeFileSync(OUT, html);
console.log(`\nWrote ${OUT} (${(html.length / 1024).toFixed(1)}kb, ${blocks.length} diagrams)`);
