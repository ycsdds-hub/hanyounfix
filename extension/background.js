// 영어 사전 조회, 단축키, 툴바 배지 처리
const DEFAULTS = { enabled: true, disabledSites: [] };

const readList = (file) =>
  fetch(chrome.runtime.getURL(file))
    .then((r) => r.text())
    .then((t) => t.split(/\r?\n/).filter(Boolean));

let dictPromise = null;
function loadDict() {
  dictPromise ??= Promise.all([readList('words.txt'), readList('common.txt')]).then(([all, common]) => ({
    sorted: all, // build-words.mjs가 정렬해 둠
    all: new Set(all),
    common: new Set(common),
  }));
  dictPromise.catch(() => { dictPromise = null; });
  return dictPromise;
}

/** w로 시작하는 더 긴 단어가 있는가 (이진 탐색) */
function isPrefix(sorted, w) {
  let lo = 0;
  let hi = sorted.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (sorted[mid] < w) lo = mid + 1;
    else hi = mid;
  }
  for (let i = lo; i < sorted.length && sorted[i].startsWith(w); i++) {
    if (sorted[i].length > w.length) return true;
  }
  return false;
}

// Windows/Mac 앱(HanYoungFix)이 켜져 있는지. 켜져 있으면 앱이 주소창까지 고치므로 확장은 쉼 (같은 글자를 두 번 고치지 않게)
let appCache = { t: 0, on: false };
async function appActive() {
  if (Date.now() - appCache.t < 3000) return appCache.on;
  let on = false;
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 500);
    const r = await fetch('http://127.0.0.1:47321/status', { signal: ctrl.signal, cache: 'no-store' });
    clearTimeout(timer);
    const j = await r.json();
    on = j?.app === 'HanYoungFix' && j.enabled === true;
  } catch {
    on = false; // 앱이 꺼져 있음
  }
  appCache = { t: Date.now(), on };
  return on;
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type === 'appActive') {
    appActive().then(sendResponse);
    return true; // 비동기 응답
  }
  if (msg?.type === 'lookup' && Array.isArray(msg.words)) {
    loadDict()
      .then((d) => sendResponse(msg.words.map((w) => ({ w: d.all.has(w), c: d.common.has(w), p: isPrefix(d.sorted, w) }))))
      .catch(() => sendResponse(null));
    return true; // 비동기 응답
  }
  return false;
});

chrome.commands.onCommand.addListener(async (command) => {
  if (command !== 'toggle-enabled') return;
  const { enabled } = await chrome.storage.sync.get(DEFAULTS);
  await chrome.storage.sync.set({ enabled: !enabled });
});

async function updateBadge() {
  const { enabled } = await chrome.storage.sync.get(DEFAULTS);
  await chrome.action.setBadgeText({ text: enabled ? '' : 'OFF' });
  await chrome.action.setBadgeBackgroundColor({ color: '#6e7781' });
}
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === 'sync' && 'enabled' in changes) updateBadge();
});
chrome.runtime.onStartup.addListener(updateBadge);
chrome.runtime.onInstalled.addListener(updateBadge);
