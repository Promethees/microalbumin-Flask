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

const MANUAL_RESERVED_NAMES = [
  // Core App State & Data Fetching
  'AppState', 'fetchJSON', 'fetchJSONContent', 'fetchData', 'fetchDataFromServer',
  
  // Mode Switching
  'switchingModes', 'switchingCalModes', 'kineticsModeBehaviour', 'pointModeBehaviour', 'calModeBehaviour',
  
  // File/Table Interactions
  'selectFile', 'deleteFile', 'editFile', 'deselectFile', 'updateFileTable', 'updateJSONTable', 'updateDirectory',
  
  // File Operations
  'copyFile', 'uploadFile', 'downloadFile', 'merge_csv', 'showMergeModal',
  
  // UI Helpers & Formatting
  'blinkingItem', 'scrollWhenVisible', 'adjustInputWidth', 'shrinkButtonTextToFit', 'shrinkAllButtonsToFit',
  'createToggleButton', 'formatAnalysisHtml', 'formatAnalysisInfo', 'formatCoefficient',
  
  // Calculation & Logic
  'processDataDisplay', 'processResponse', 'handleResponse', 'handleError', 'handleFetchError',
  'getMetaUnit', 'getTimeUnitValue', 'getTimeUnitMultiplier', 'getBtnChecked', 'getValInt', 'getValFloat',
  'arraysEqual', 'checkMeasHeader', 'buildMeasHeaders', 'filterFiles',
  
  // Charting
  'generateChart', 'updatePlot', 'updatePlotBasedOnMode', 'drawMeasurementChart', 'destroyCharts',
  'splitMultiSourceRoutine', 'groupMultiSourceRoutine', 'calibrateRoutine',
  'updatePlotBasedOnMode', 'updateRefCalPoint', 'processPointMode', 'populateDropdown',
  'settingDerivedCon', 'updateDerivedSections', 'updateMultiSourceExportOptions',
  
  // External Libraries
  'Chart', 'Swal', 'MathJax', 'jQuery', '$',

  // AI Assistant
  'OkapiAI',
];

function getReservedNames() {
  const reserved = new Set(MANUAL_RESERVED_NAMES);
  
  // 1. Scan templates
  const templatesDir = path.join(__dirname, 'templates');
  if (fs.existsSync(templatesDir)) {
    const htmlFiles = fs.readdirSync(templatesDir).filter(f => f.endsWith('.html'));
    htmlFiles.forEach(file => {
      const html = fs.readFileSync(path.join(templatesDir, file), 'utf8');
      // Scan onclick/onchange attributes
      html.replace(/(?:onclick|onchange|oninput|onblur)=["']([^"']+)["']/g, (_, inner) => {
        inner.match(/([a-zA-Z0-9_$]+)\s*\(/g)?.forEach(f => reserved.add(f.replace('(', '').trim()));
      });
      // Scan script tags
      html.replace(/<script[^>]*>([\s\S]*?)<\/script>/gi, (_, script) => {
        script.match(/\b([a-zA-Z_$][\w$]*)\s*\(/g)?.forEach(m => {
          const name = m.replace('(', '').trim();
          if (!['console', 'alert', 'setTimeout', 'setInterval'].includes(name)) reserved.add(name);
        });
      });
    });
  }

  // 2. Scan JS files for dynamic handler strings
  if (fs.existsSync(SRC_JS_DIR)) {
    const jsFiles = fs.readdirSync(SRC_JS_DIR).filter(f => f.endsWith('.js') && !f.endsWith('.min.js'));
    jsFiles.forEach(file => {
      const content = fs.readFileSync(path.join(SRC_JS_DIR, file), 'utf8');
      content.replace(/(?:onclick|onchange|oninput|onblur)=["']([^"']+)["']/g, (_, inner) => {
        inner.match(/([a-zA-Z0-9_$]+)\s*\(/g)?.forEach(f => reserved.add(f.replace('(', '').trim()));
      });
    });
  }

  console.log(`  Total reserved names protected: ${reserved.size}`);
  return Array.from(reserved).sort();
}

// ---------- OBFUSCATOR SETTINGS ----------
const OBFUSCATOR_OPTIONS = {
  compact: true,
  controlFlowFlattening: false,
  deadCodeInjection: false,
  renameGlobals: false,
  reservedNames: getReservedNames(),
  stringArray: false,           // Disabled to prevent stack overflow on large files
  identifierNamesGenerator: 'mangled', // More efficient than 'hexadecimal'
  transformObjectKeys: false,
  unicodeEscapeSequence: false,
  selfDefending: false,
};

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
    // Disable mangle in terser because obfuscator already handled renaming/obfuscation.
    // We only want terser for compression and dead code removal.
    const minified = await minify(obf, { 
      mangle: false, 
      compress: true,
      output: { comments: false }
    });
    
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