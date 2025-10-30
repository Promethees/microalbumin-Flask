// build.js
const fs = require('fs');
const path = require('path');
const { minify } = require('terser');
const CleanCSS = require('clean-css');
const Obfuscator = require('javascript-obfuscator');

// ---------- CONFIG ----------
const SRC_JS_DIR   = path.join(__dirname, 'static', 'script');   // <-- your folder
const SRC_CSS_DIR  = path.join(__dirname, 'static');              // root static (for CSS)
const DIST_DIR     = path.join(__dirname, 'static', 'dist');

// Ensure output folder exists
fs.mkdirSync(DIST_DIR, { recursive: true });

// ---------- OBFUSCATOR SETTINGS ----------
const OBFUSCATOR_OPTIONS = {
  compact: true,
  controlFlowFlattening: true,
  controlFlowFlatteningThreshold: 0.75,
  deadCodeInjection: true,
  deadCodeInjectionThreshold: 0.4,
  renameGlobals: true,
  stringArray: true,
  stringArrayThreshold: 1,
  transformObjectKeys: true,
  unicodeEscapeSequence: true,
  selfDefending: true,
};

// ---------- HELPER: Process one JS file ----------
async function processJS(filePath) {
  const filename = path.basename(filePath);
  const raw = fs.readFileSync(filePath, 'utf8');

  console.log(`Obfuscating ${filename}...`);

  // 1. Obfuscate
  const obf = Obfuscator.obfuscate(raw, OBFUSCATOR_OPTIONS).getObfuscatedCode();

  // 2. Minify
  const { code } = await minify(obf, {
    mangle: true,
    compress: { pure_funcs: ['console.log'] },
  });

  const outName = filename.replace(/\.js$/, '.min.js');
  const outPath = path.join(DIST_DIR, outName);
  fs.writeFileSync(outPath, code || '');
  console.log(`→ ${outName}`);
}

// ---------- HELPER: Process one CSS file ----------
function processCSS(filePath) {
  const filename = path.basename(filePath);
  const input = fs.readFileSync(filePath, 'utf8');

  console.log(`Minifying ${filename}...`);

  const output = new CleanCSS({ level: 2 }).minify(input).styles;
  const outName = filename.replace(/\.css$/, '.min.css');
  const outPath = path.join(DIST_DIR, outName);
  fs.writeFileSync(outPath, output);
  console.log(`→ ${outName}`);
}

// ---------- MAIN ----------
(async () => {
  // === Process all .js files in static/script/ ===
  const jsFiles = fs.readdirSync(SRC_JS_DIR)
    .filter(f => f.endsWith('.js'))
    .map(f => path.join(SRC_JS_DIR, f));

  for (const file of jsFiles) {
    await processJS(file);
  }

  // === Process all .css files in static/ (you can narrow this if needed) ===
  const cssFiles = fs.readdirSync(SRC_CSS_DIR)
    .filter(f => f.endsWith('.css') && !f.endsWith('.min.css'))
    .map(f => path.join(SRC_CSS_DIR, f));

  for (const file of cssFiles) {
    processCSS(file);
  }

  console.log('\nBuild complete! All files → static/dist/');
})();