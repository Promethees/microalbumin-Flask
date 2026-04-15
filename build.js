// build.js
const fs = require('fs');
const path = require('path');

// Move requires into try-catch to provide better error messages on Heroku
let minify, CleanCSS, Obfuscator;
try {
  minify = require('terser').minify;
  CleanCSS = require('clean-css');
  Obfuscator = require('javascript-obfuscator');
} catch (e) {
  console.error('[FATAL ERROR] Missing build dependencies. Ensure clean-css, terser, and javascript-obfuscator are in "dependencies" in package.json.');
  console.error(e);
  process.exit(1);
}

// ---------- CONFIG ----------
const SRC_JS_DIR   = path.join(__dirname, 'static', 'script');
const SRC_STATIC   = path.join(__dirname, 'static');
const DIST_DIR     = path.join(__dirname, 'static', 'dist');

console.log('--- STARTING BUILD PROCESS ---');

// Ensure dist exists
if (!fs.existsSync(DIST_DIR)) {
  fs.mkdirSync(DIST_DIR, { recursive: true });
  console.log('Created directory:', DIST_DIR);
}

// ---------- OBFUSCATOR SETTINGS ----------
const OBFUSCATOR_OPTIONS = {
  compact: true,
  controlFlowFlattening: true,
  controlFlowFlatteningThreshold: 0.75,
  deadCodeInjection: true,
  deadCodeInjectionThreshold: 0.4,
  renameGlobals: false,
  reservedNames: getReservedNamesFromHTML(),
  stringArray: true,
  stringArrayThreshold: 1,
  transformObjectKeys: false,
  unicodeEscapeSequence: true,
  selfDefending: true,
};

function getReservedNamesFromHTML() {
  const templatesDir = path.join(__dirname, 'templates');
  if (!fs.existsSync(templatesDir)) return [];

  const htmlFiles = fs.readdirSync(templatesDir)
    .filter(f => f.endsWith('.html'))
    .map(f => path.join(templatesDir, f));

  const reserved = new Set();
  htmlFiles.forEach(htmlPath => {
    const html = fs.readFileSync(htmlPath, 'utf8');
    html.replace(/onclick=["']([^"')]+)["']/g, (_, fn) => {
      const name = fn.split('(')[0].trim();
      if (name && !name.startsWith('window.') && !name.includes('.')) reserved.add(name);
    });
    html.replace(/data-action=["']([^"']+)["']/g, (_, action) => reserved.add(action));
    html.replace(/<script[^>]*>([\s\S]*?)<\/script>/gi, (_, script) => {
      script.replace(/\b([a-zA-Z_$][\w$]*)\s*\(/g, (match, name) => {
        if (name && !name.startsWith('_') && !name.includes('.') && 
            !['console', 'alert', 'confirm', 'prompt', 'setTimeout', 'setInterval'].includes(name)) {
          reserved.add(name);
        }
        return match;
      });
    });
  });
  return Array.from(reserved).sort();
}

// ---------- 1. COPY STATIC ASSETS ----------
function copyStaticAssets() {
  console.log('[1/3] Copying static assets (images, fonts, icons)...');
  const exclude = ['.js', '.css', '.min.js', '.min.css'];
  const files = fs.readdirSync(SRC_STATIC)
    .filter(f => !exclude.some(ext => f.endsWith(ext)))
    .filter(f => fs.statSync(path.join(SRC_STATIC, f)).isFile());

  for (const file of files) {
    fs.copyFileSync(path.join(SRC_STATIC, file), path.join(DIST_DIR, file));
    console.log(`  Copied: ${file}`);
  }

  const subfolders = ['images', 'fonts', 'icons', 'assets'];
  for (const folder of subfolders) {
    const srcFolder = path.join(SRC_STATIC, folder);
    const distFolder = path.join(DIST_DIR, folder);
    if (fs.existsSync(srcFolder)) {
      if (!fs.existsSync(distFolder)) fs.mkdirSync(distFolder, { recursive: true });
      fs.readdirSync(srcFolder).forEach(item => {
        const srcItem = path.join(srcFolder, item);
        const destItem = path.join(distFolder, item);
        if (fs.statSync(srcItem).isFile()) {
          fs.copyFileSync(srcItem, destItem);
          console.log(`  Copied: ${folder}/${item}`);
        }
      });
    }
  }
}

// ---------- 2. PROCESS JS ----------
async function processJS(filePath) {
  const filename = path.basename(filePath);
  const raw = fs.readFileSync(filePath, 'utf8');

  try {
    console.log(`[2/3] Processing JS: ${filename}`);
    console.log(`  - Obfuscating...`);
    const obf = Obfuscator.obfuscate(raw, OBFUSCATOR_OPTIONS).getObfuscatedCode();
    
    console.log(`  - Minifying...`);
    const minified = await minify(obf, { mangle: true, compress: true });
    
    if (!minified || !minified.code) {
        throw new Error(`Minification resulted in empty code for ${filename}`);
    }

    const outName = filename.replace(/\.js$/, '.min.js');
    fs.writeFileSync(path.join(DIST_DIR, outName), minified.code);
    console.log(`  OK -> ${outName} (${(minified.code.length / 1024).toFixed(2)} KB)`);
  } catch (err) {
    console.error(`[ERROR] Failed to process JS ${filename}:`, err);
    process.exit(1); // Fail the build on error
  }
}

// ---------- 3. PROCESS CSS ----------
function processCSS(filePath) {
  const filename = path.basename(filePath);
  const input = fs.readFileSync(filePath, 'utf8');

  try {
    console.log(`[3/3] Processing CSS: ${filename}`);
    const output = new CleanCSS({ level: 2 }).minify(input).styles;
    const outName = filename.replace(/\.css$/, '.min.css');
    fs.writeFileSync(path.join(DIST_DIR, outName), output);
    console.log(`  OK -> ${outName} (${(output.length / 1024).toFixed(2)} KB)`);
  } catch (err) {
    console.error(`[ERROR] Failed to process CSS ${filename}:`, err);
    process.exit(1);
  }
}

// ---------- MAIN ----------
(async () => {
  try {
    copyStaticAssets();

    if (fs.existsSync(SRC_JS_DIR)) {
      const jsFiles = fs.readdirSync(SRC_JS_DIR)
        .filter(f => f.endsWith('.js'))
        .map(f => path.join(SRC_JS_DIR, f));

      for (const file of jsFiles) {
        await processJS(file);
      }
    } else {
      console.warn('[WARN] No JS source folder found at:', SRC_JS_DIR);
    }

    const cssFiles = fs.readdirSync(SRC_STATIC)
      .filter(f => f.endsWith('.css') && !f.endsWith('.min.css'))
      .map(f => path.join(SRC_STATIC, f));

    for (const file of cssFiles) {
      processCSS(file);
    }

    console.log('\n--- BUILD SUCCESSFUL! ---');
    console.log('Static assets are ready in static/dist/');
  } catch (err) {
    console.error('[FATAL ERROR] Build process failed:', err);
    process.exit(1);
  }
})();