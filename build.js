// build.js
const fs = require('fs');
const path = require('path');
const { minify } = require('terser');
const CleanCSS = require('clean-css');
const Obfuscator = require('javascript-obfuscator');

// ---------- CONFIG ----------
const SRC_JS_DIR   = path.join(__dirname, 'static', 'script');   // your JS folder
const SRC_STATIC   = path.join(__dirname, 'static');              // root static/
const DIST_DIR     = path.join(__dirname, 'static', 'dist');

// Ensure dist exists
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

// ---------- 1. COPY ALL NON-JS/CSS FILES ----------
function copyStaticAssets() {
  console.log('Copying static assets (images, fonts, etc.)...');

  const exclude = ['.js', '.css', '.min.js', '.min.css'];
  const files = fs.readdirSync(SRC_STATIC)
    .filter(f => !exclude.some(ext => f.endsWith(ext)))
    .filter(f => fs.statSync(path.join(SRC_STATIC, f)).isFile());

  for (const file of files) {
    const src = path.join(SRC_STATIC, file);
    const dest = path.join(DIST_DIR, file);
    fs.copyFileSync(src, dest);
    console.log(`Copied: ${file}`);
  }

  // Also copy from subfolders like static/images/, static/fonts/, etc.
  const subfolders = ['images', 'fonts', 'icons', 'assets'];
  for (const folder of subfolders) {
    const srcFolder = path.join(SRC_STATIC, folder);
    const distFolder = path.join(DIST_DIR, folder);
    if (fs.existsSync(srcFolder)) {
      fs.mkdirSync(distFolder, { recursive: true });
      const items = fs.readdirSync(srcFolder);
      for (const item of items) {
        const srcItem = path.join(srcFolder, item);
        const destItem = path.join(distFolder, item);
        if (fs.statSync(srcItem).isFile()) {
          fs.copyFileSync(srcItem, destItem);
          console.log(`Copied: ${folder}/${item}`);
        }
      }
    }
  }
}

// ---------- 2. PROCESS JS ----------
async function processJS(filePath) {
  const filename = path.basename(filePath);
  const raw = fs.readFileSync(filePath, 'utf8');

  console.log(`Obfuscating ${filename}...`);
  const obf = Obfuscator.obfuscate(raw, OBFUSCATOR_OPTIONS).getObfuscatedCode();
  const { code } = await minify(obf, { mangle: true, compress: true });

  const outName = filename.replace(/\.js$/, '.min.js');
  const outPath = path.join(DIST_DIR, outName);
  fs.writeFileSync(outPath, code || '');
  console.log(`→ ${outName}`);
}

// ---------- 3. PROCESS CSS ----------
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
  // 1. Copy images, fonts, etc. FIRST
  copyStaticAssets();

  // 2. Process JS
  if (fs.existsSync(SRC_JS_DIR)) {
    const jsFiles = fs.readdirSync(SRC_JS_DIR)
      .filter(f => f.endsWith('.js'))
      .map(f => path.join(SRC_JS_DIR, f));

    for (const file of jsFiles) {
      await processJS(file);
    }
  }

  // 3. Process CSS (from static/ root)
  const cssFiles = fs.readdirSync(SRC_STATIC)
    .filter(f => f.endsWith('.css') && !f.endsWith('.min.css'))
    .map(f => path.join(SRC_STATIC, f));

  for (const file of cssFiles) {
    processCSS(file);
  }

  console.log('\nBuild complete! static/dist/ is ready (with .png preserved)');
})();