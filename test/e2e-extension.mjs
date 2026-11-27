// 확장 실제 동작 시험: 격리된 Chrome에 확장을 올리고 입력칸에 키를 쳐서 교정 결과를 본다.
// 실행: npm run test:ext   (Chrome 경로가 다르면 CHROME 환경 변수로)
// 브랜드 Chrome은 --load-extension 을 막으므로 CDP Extensions.loadUnpacked 를 쓴다 (pipe 연결 필요).
import { spawn } from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const EXT = path.join(ROOT, 'extension');
const CHROME = process.env.CHROME || [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome',
].find((p) => fs.existsSync(p));
if (!CHROME) { console.log('Chrome을 찾지 못함 (CHROME 환경 변수로 지정)'); process.exit(2); }

const sleep = (ms) => new Promise((ok) => setTimeout(ok, ms));
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'hy-ext-'));

const server = http.createServer((_q, r) => {
  r.setHeader('content-type', 'text/html; charset=utf-8');
  r.end('<textarea id=t></textarea><div id=c contenteditable style="border:1px solid;min-height:2em"></div>');
}).listen(0, '127.0.0.1');
await new Promise((ok) => server.once('listening', ok));
const pageUrl = `http://127.0.0.1:${server.address().port}/`;

const chrome = spawn(CHROME, [
  `--user-data-dir=${profile}`, '--remote-debugging-pipe', '--enable-unsafe-extension-debugging',
  '--no-first-run', '--no-default-browser-check', '--headless=new', 'about:blank',
], { stdio: ['ignore', 'ignore', 'ignore', 'pipe', 'pipe'] });

let nextId = 0, buf = '';
const waiters = new Map();
chrome.stdio[4].on('data', (d) => {
  buf += d.toString();
  let i;
  while ((i = buf.indexOf('\0')) >= 0) {
    const m = JSON.parse(buf.slice(0, i));
    buf = buf.slice(i + 1);
    if (m.id && waiters.has(m.id)) { waiters.get(m.id)(m); waiters.delete(m.id); }
  }
});
const send = (method, params = {}, sessionId) => new Promise((ok, bad) => {
  const n = ++nextId;
  waiters.set(n, (m) => (m.error ? bad(new Error(`${method}: ${m.error.message}`)) : ok(m.result)));
  chrome.stdio[3].write(JSON.stringify({ id: n, method, params, sessionId }) + '\0');
});
const evaluate = async (sessionId, expression) => {
  const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }, sessionId);
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
  return r.result.value;
};

async function workerSession(extId) {
  for (let i = 0; i < 100; i++) {
    const { targetInfos } = await send('Target.getTargets');
    const sw = targetInfos.find((t) => t.type === 'service_worker' && t.url.includes(extId));
    if (sw) return (await send('Target.attachToTarget', { targetId: sw.targetId, flatten: true })).sessionId;
    await sleep(100);
  }
  throw new Error('서비스 워커를 찾지 못함');
}

async function openPage() {
  const { targetId } = await send('Target.createTarget', { url: pageUrl });
  const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
  await sleep(1500); // document_idle 뒤 콘텐츠 스크립트가 붙을 시간
  return { targetId, sessionId };
}

async function typeInto(sessionId, sel, text, gap) {
  await evaluate(sessionId, `document.querySelector('${sel}').focus()`);
  await sleep(300);
  for (const ch of text) {
    await send('Input.dispatchKeyEvent', { type: 'keyDown', key: ch, text: ch, unmodifiedText: ch }, sessionId);
    await send('Input.dispatchKeyEvent', { type: 'keyUp', key: ch }, sessionId);
    await sleep(gap);
  }
}
const valueOf = (sessionId, sel) =>
  evaluate(sessionId, `(()=>{const e=document.querySelector('${sel}'); return (e.value ?? e.textContent).replace(/\\u00a0/g, ' ')})()`);

const cases = [
  { name: '보통 속도', delay: 0 },
  // 사전 조회 답이 늦게 오는 경우 (서비스 워커가 막 깨어나 사전을 읽는 중)
  { name: '사전 조회가 2초 늦음', delay: 2000 },
];
const WORDS = 'dkssudgktpdy ';
const WANT = '안녕하세요 ';

let failed = 0;
try {
  const { id: extId } = await send('Extensions.loadUnpacked', { path: EXT });
  let sw = null; // 서비스 워커는 페이지가 메시지를 보내야 깨어나므로 첫 페이지를 연 뒤 찾음
  for (const c of cases) {
    for (const sel of ['#t', '#c']) {
      const page = await openPage();
      sw ??= await workerSession(extId);
      if (c.delay) {
        // 다음 사전 조회를 늦춤: 불러온 사전 대신 c.delay 뒤에 불러오는 약속을 넣어 둠
        await evaluate(sw, `dictPromise = new Promise((r) => setTimeout(r, ${c.delay})).then(() => { dictPromise = null; return loadDict(); }); true`);
      }
      await typeInto(page.sessionId, sel, WORDS, 60);
      await sleep(c.delay + 3000);
      const got = await valueOf(page.sessionId, sel);
      const ok = got === WANT;
      if (!ok) failed++;
      console.log(`${ok ? '통과' : '실패'}  ${c.name} · ${sel === '#t' ? 'textarea' : 'contenteditable'}: ${JSON.stringify(got)}`);
      await send('Target.closeTarget', { targetId: page.targetId });
    }
  }
} catch (e) {
  failed++;
  console.log('오류', e.message);
} finally {
  chrome.kill();
  server.close();
}
console.log(failed ? `실패 ${failed}개` : '모두 통과');
process.exit(failed ? 1 : 0);
