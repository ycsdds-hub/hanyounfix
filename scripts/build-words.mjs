// SCOWL 기반 영어 단어 목록을 만듭니다.
//   extension/words.txt   모든 단어 (영어 모드로 친 단어가 영어인지 판단)
//   extension/common.txt  흔한 단어 (한글 모드로 친 글자를 영어로 바꿀지 판단)
// 사용법: npm install && npm run build:words
import { readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const pkgDir = dirname(require.resolve('wordlist-english/package.json'));
const root = join(dirname(fileURLToPath(import.meta.url)), '..');

const ALL_SIZES = [10, 20, 35, 40, 50, 55, 60, 70]; // 숫자가 클수록 드문 단어
const COMMON_MAX = 35;
const DIALECTS = ['english', 'american', 'british', 'canadian'];

function collect(sizes) {
  const words = new Set();
  for (const d of DIALECTS) {
    for (const s of sizes) {
      for (const w of JSON.parse(readFileSync(join(pkgDir, `${d}-words-${s}.json`), 'utf8'))) {
        const lw = w.toLowerCase();
        if (/^[a-z]{2,}$/.test(lw)) words.add(lw);
      }
    }
  }
  return [...words].sort();
}

for (const [file, sizes] of [
  ['words.txt', ALL_SIZES],
  ['common.txt', ALL_SIZES.filter((s) => s <= COMMON_MAX)],
]) {
  const list = collect(sizes);
  const out = list.join('\n') + '\n';
  writeFileSync(join(root, 'extension', file), out);
  console.log(`${file}: ${list.length} words, ${(out.length / 1024).toFixed(0)} KB`);
}
