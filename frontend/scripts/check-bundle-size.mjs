#!/usr/bin/env node
/**
 * Bundle budget gate. Fails CI when the gzipped JS payload of the
 * built SPA exceeds the configured budget. Run after `vite build`.
 *
 * Tweak via env:
 *   BUNDLE_BUDGET_KB    — total gzipped JS budget (default: 350)
 *   BUNDLE_DIR          — dist dir (default: dist/assets)
 */
import { readdirSync, statSync, readFileSync } from 'node:fs'
import { gzipSync } from 'node:zlib'
import { join, extname } from 'node:path'

const BUDGET_KB = Number(process.env.BUNDLE_BUDGET_KB ?? 350)
const DIR = process.env.BUNDLE_DIR ?? 'dist/assets'

function listJs(dir) {
  return readdirSync(dir)
    .map((name) => join(dir, name))
    .filter((p) => statSync(p).isFile() && extname(p) === '.js')
}

let totalRaw = 0
let totalGz = 0
const rows = []
try {
  for (const file of listJs(DIR)) {
    const buf = readFileSync(file)
    const gz = gzipSync(buf).length
    totalRaw += buf.length
    totalGz += gz
    rows.push({ file, raw: buf.length, gz })
  }
} catch (e) {
  console.error(`Cannot read ${DIR}: ${e.message}`)
  process.exit(2)
}

rows.sort((a, b) => b.gz - a.gz)
console.log('  size (gz) | size (raw) | file')
console.log('  ----------+------------+----------------------------------')
for (const r of rows) {
  console.log(
    `  ${(r.gz / 1024).toFixed(1).padStart(7)} kB | ${(r.raw / 1024).toFixed(1).padStart(8)} kB | ${r.file}`
  )
}
console.log('  ----------+------------+----------------------------------')
console.log(`  TOTAL gzipped: ${(totalGz / 1024).toFixed(1)} kB  (budget: ${BUDGET_KB} kB)`)

if (totalGz / 1024 > BUDGET_KB) {
  console.error(`\nFAIL: gzipped JS (${(totalGz / 1024).toFixed(1)} kB) exceeds budget (${BUDGET_KB} kB).`)
  process.exit(1)
}
console.log('OK')
