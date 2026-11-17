// SCOWL 기반 영어 단어 목록(extension/words.txt)을 만듭니다.
// 사용법: npm install && npm run build:words
import { readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const pkgDir = dirname(require.resolve('wordlist-english/package.json'));
const root = join(dirname(fileURLToPath(import.meta.url)), '..');

// 숫자가 클수록 드문 단어까지 포함 (10 ~ 70)
const SIZES = [10, 20, 35, 40, 50, 55, 60, 70];
const DIALECTS = ['english', 'american', 'british', 'canadian'];

const words = new Set();
for (const d of DIALECTS) {
  for (const s of SIZES) {
    const list = JSON.parse(readFileSync(join(pkgDir, `${d}-words-${s}.json`), 'utf8'));
    for (const w of list) {
      const lw = w.toLowerCase();
      if (/^[a-z]{2,}$/.test(lw)) words.add(lw);
    }
  }
}

const out = [...words].sort().join('\n') + '\n';
writeFileSync(join(root, 'extension', 'words.txt'), out);
console.log(`words.txt: ${words.size} words, ${(out.length / 1024).toFixed(0)} KB`);
