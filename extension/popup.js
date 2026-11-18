const DEFAULTS = { enabled: true, disabledSites: [], userWords: [], showToast: true, checkLength: 6 };
const $ = (id) => document.getElementById(id);

(async () => {
  const s = await chrome.storage.sync.get(DEFAULTS);
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  let host = '';
  try {
    const url = new URL(tab?.url || '');
    if (url.protocol.startsWith('http')) host = url.hostname;
  } catch {}

  $('enabled').checked = s.enabled;
  $('showToast').checked = s.showToast;
  $('checkLength').value = s.checkLength;
  $('userWords').value = s.userWords.join('\n');
  if (host) {
    $('host').textContent = host;
    $('siteOff').checked = s.disabledSites.includes(host);
  } else {
    $('siteOff').disabled = true;
    $('host').textContent = '이 페이지에서는 설정할 수 없어요';
  }

  $('enabled').addEventListener('change', (e) => chrome.storage.sync.set({ enabled: e.target.checked }));
  $('showToast').addEventListener('change', (e) => chrome.storage.sync.set({ showToast: e.target.checked }));
  $('checkLength').addEventListener('change', (e) => {
    const n = Math.min(30, Math.max(4, parseInt(e.target.value, 10) || DEFAULTS.checkLength));
    e.target.value = n;
    chrome.storage.sync.set({ checkLength: n });
  });
  $('siteOff').addEventListener('change', async (e) => {
    const { disabledSites } = await chrome.storage.sync.get(DEFAULTS);
    const set = new Set(disabledSites);
    e.target.checked ? set.add(host) : set.delete(host);
    chrome.storage.sync.set({ disabledSites: [...set] });
  });

  let timer;
  $('userWords').addEventListener('input', (e) => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      const words = [...new Set(e.target.value.split('\n').map((w) => w.trim()).filter(Boolean))];
      chrome.storage.sync.set({ userWords: words });
    }, 400);
  });
})();
