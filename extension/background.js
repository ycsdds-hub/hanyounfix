// 영어 사전 조회, 단축키, 툴바 배지 처리
const DEFAULTS = { enabled: true, disabledSites: [] };

let wordsPromise = null;
function loadWords() {
  wordsPromise ??= fetch(chrome.runtime.getURL('words.txt'))
    .then((r) => r.text())
    .then((t) => new Set(t.split('\n')));
  return wordsPromise;
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type === 'lookup' && Array.isArray(msg.words)) {
    loadWords().then((set) => sendResponse(msg.words.map((w) => set.has(w))));
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
