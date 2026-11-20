/*
 * 웹페이지 입력창에서 한영 오타를 감지해 바로 고쳐 씁니다.
 * - 띄어쓰기/문장부호를 칠 때 직전 단어를 검사
 * - 영어 모드로 한글을 길게 치는 중이면 N글자마다 미리 교정
 * - Enter를 칠 때도 (영어 모드라면) 마지막 단어를 교정
 */
(() => {
  'use strict';
  if (window.__hanyoungFixLoaded) return;
  window.__hanyoungFixLoaded = true;

  const HY = globalThis.HanYoung;
  const DEFAULTS = { enabled: true, disabledSites: [], userWords: [], showToast: true, checkLength: 6 };
  const BOUNDARY = /^[\s.,!?;:)\]}"”…~]$/;
  const BLOCKED_BEFORE = /[0-9_@#/\\.:\-=+&%$]/;
  const CODE_EDITORS = '.monaco-editor, .cm-editor, .CodeMirror, .ace_editor';
  const TEXT_INPUT_TYPES = new Set(['text', 'search', '']);

  let settings = { ...DEFAULTS };
  let userWords = new Set();
  const host = location.hostname;

  chrome.storage.sync.get(DEFAULTS, (s) => applySettings(s));
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== 'sync') return;
    const next = { ...settings };
    for (const [k, { newValue }] of Object.entries(changes)) next[k] = newValue ?? DEFAULTS[k];
    applySettings(next);
  });
  function applySettings(s) {
    settings = { ...DEFAULTS, ...s };
    userWords = new Set(settings.userWords.map((w) => w.toLowerCase()));
  }
  const active = () => settings.enabled && !settings.disabledSites.includes(host);

  // ---------- 사전 조회 (background에 위임, 결과 캐시) ----------
  // cache: 단어 → { w: 사전에 있음, c: 흔한 단어, p: 더 긴 단어의 앞부분 }
  const cache = new Map();
  const pending = new Map();
  function lookup(words) {
    const missing = words.filter((w) => !cache.has(w) && !pending.has(w));
    if (missing.length) {
      const p = chrome.runtime
        .sendMessage({ type: 'lookup', words: missing })
        .then((res) => {
          if (!Array.isArray(res)) return; // 응답 실패 시 캐시하지 않고 다음에 다시 조회
          missing.forEach((w, i) => cache.set(w, res[i] || { w: false, c: false, p: false }));
        })
        .catch(() => {})
        .finally(() => missing.forEach((w) => pending.delete(w)));
      missing.forEach((w) => pending.set(w, p));
    }
    return Promise.all(words.map((w) => pending.get(w))).then(() => undefined);
  }
  const candidates = (token) =>
    /^[A-Za-z]+$/.test(token) ? [token.toLowerCase()] : [HY.hangulToEng(token).toLowerCase()];
  const dict = {
    isWord: (w) => userWords.has(w) || cache.get(w)?.w === true,
    isCommon: (w) => userWords.has(w) || cache.get(w)?.c === true,
    isPrefix: (w) => cache.get(w)?.p === true,
  };

  /** 동기 판단. 사전 결과가 아직 없으면 undefined */
  function judge(tok, cont, midWord) {
    const { token } = tok;
    if (userWords.has(token.toLowerCase())) return null;
    if (cont && /^[A-Za-z]+$/.test(token)) {
      // 직전에 우리가 고친 한글 바로 뒤에 이어 친 영문 → 사전/길이 검사 없이 한글로
      const h = HY.engToHangul(token);
      return [...h].every(HY.isSyllable) ? h : null;
    }
    if (candidates(token).some((w) => !cache.has(w) && !userWords.has(w))) return undefined;
    return HY.decide(token, dict, { midWord });
  }

  // ---------- 입력창 다루기 ----------
  function editableOf(el) {
    if (!el || el.closest?.(CODE_EDITORS)) return null;
    if (el instanceof HTMLTextAreaElement) return el;
    if (el instanceof HTMLInputElement) return TEXT_INPUT_TYPES.has(el.type) ? el : null;
    return el.isContentEditable ? el : null;
  }

  function readContext(el) {
    if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
      if (el.selectionStart == null || el.selectionStart !== el.selectionEnd) return null;
      return { kind: 'input', el, text: el.value, caret: el.selectionStart };
    }
    const sel = el.ownerDocument.getSelection();
    if (!sel || !sel.isCollapsed || sel.focusNode?.nodeType !== Node.TEXT_NODE) return null;
    return { kind: 'ce', el, node: sel.focusNode, text: sel.focusNode.data, caret: sel.focusOffset };
  }

  /** end 바로 앞에서 끝나는, 한 가지 문자 종류로만 된 단어 */
  function findToken(text, end) {
    const isEng = (c) => /[A-Za-z]/.test(c);
    const isKo = (c) => /[가-힣ㄱ-ㅣ]/.test(c);
    if (end <= 0) return null;
    const test = isEng(text[end - 1]) ? isEng : isKo(text[end - 1]) ? isKo : null;
    if (!test) return null;
    let start = end;
    while (start > 0 && test(text[start - 1])) start--;
    const before = text[start - 1] || '';
    if (BLOCKED_BEFORE.test(before)) return null;
    if (test === isKo && /[A-Za-z]/.test(before)) return null;
    return { start, end, token: text.slice(start, end) };
  }

  let selfEdit = false;
  function replaceRange(ctx, start, end, text) {
    const { el } = ctx;
    selfEdit = true;
    try {
      if (ctx.kind === 'input') {
        const caret = el.selectionStart;
        el.setSelectionRange(start, end);
        if (!el.ownerDocument.execCommand('insertText', false, text)) {
          el.setRangeText(text, start, end, 'end');
          el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertReplacementText', data: text }));
        }
        const pos = caret >= end ? caret + text.length - (end - start) : caret;
        el.setSelectionRange(pos, pos);
      } else {
        const sel = el.ownerDocument.getSelection();
        const after = sel.focusNode === ctx.node && sel.focusOffset >= end ? sel.focusOffset - end : 0;
        const r = el.ownerDocument.createRange();
        r.setStart(ctx.node, start);
        r.setEnd(ctx.node, end);
        sel.removeAllRanges();
        sel.addRange(r);
        el.ownerDocument.execCommand('insertText', false, text);
        for (let i = 0; i < after; i++) sel.modify('move', 'forward', 'character');
      }
    } finally {
      selfEdit = false;
    }
  }

  // ---------- 교정 ----------
  const lastFix = new WeakMap(); // el → { contAt, start, original, fixed, learn, time }
  let composing = false;
  let afterComposition = [];

  function isContinuation(el, tok) {
    const f = lastFix.get(el);
    return !!f && f.contAt === tok.start && Date.now() - f.time < 10000;
  }

  // ---------- 다시 쓰면 그대로 두기 ----------
  // 고친 단어를 지우고 RETYPE_MS 안에 똑같이 다시 쓰면 일부러 쓴 것으로 보고 그대로 둠
  const RETYPE_MS = 60000;
  const recentFixes = new WeakMap(); // el → [{ w: 고치기 전 단어(소문자), t }]
  const erased = new WeakMap();      // el → 마지막 교정 뒤에 지운 적이 있는지

  // 일부러 다시 쓴 단어: 같은 창(탭)에서는 10분, 다른 탭에서는 1분 동안 그대로 둠 (영구히 배우지는 않음)
  // 다른 탭도 알 수 있게 chrome.storage.local 에 둠
  const KEEP_SAME_MS = 10 * 60000;
  const KEEP_OTHER_MS = 60000;
  const PAGE_ID = Math.random().toString(36).slice(2) + Date.now().toString(36);
  let kept = []; // [{ w, t, page }]
  chrome.storage.local.get({ kept: [] }, (r) => { kept = r?.kept || []; });
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === 'local' && changes.kept) kept = changes.kept.newValue || [];
  });

  function keepWord(token) {
    const w = token.toLowerCase();
    const now = Date.now();
    kept = [...kept.filter((k) => now - k.t < KEEP_SAME_MS && !(k.w === w && k.page === PAGE_ID)), { w, t: now, page: PAGE_ID }];
    chrome.storage.local.set({ kept });
  }

  /** 일부러 다시 쓴 단어라 아직 그대로 둘 기간인지 (prefix: 치는 중인 앞부분) */
  function isKept(token, prefix = false) {
    const w = token.toLowerCase();
    const now = Date.now();
    for (const k of kept) {
      if (!(k.w === w || (prefix && k.w.startsWith(w)))) continue;
      const same = k.page === PAGE_ID;
      if (now - k.t < (same ? KEEP_SAME_MS : KEEP_OTHER_MS)) {
        if (same && k.w === w) keepWord(token); // 같은 탭에서 또 쓰면 10분 연장
        return true;
      }
    }
    return false;
  }

  /** 방금 고친 단어를 지우고 그 자리에 똑같이 다시 썼으면 그 기록의 위치, 아니면 -1 */
  function retypeIndex(el, token, prefix = false) {
    if (!erased.get(el)) return -1; // 지우지 않고 또 친 것은 같은 실수를 반복한 것으로 봄
    const now = Date.now();
    const list = (recentFixes.get(el) || []).filter((r) => now - r.t < RETYPE_MS);
    recentFixes.set(el, list);
    const w = token.toLowerCase();
    return list.findIndex((r) => r.w === w || (prefix && (r.w.startsWith(w) || w.startsWith(r.w))));
  }
  const retyped = (el, token, prefix = false) => retypeIndex(el, token, prefix) >= 0;

  function rememberFix(el, words, replaceLast) {
    const list = recentFixes.get(el) || [];
    if (replaceLast && list.length) list.pop();
    const t = Date.now();
    for (const w of words) list.push({ w: w.toLowerCase(), t });
    recentFixes.set(el, list);
    erased.set(el, false);
  }

  function learnWord(word, message) {
    const w = word.toLowerCase();
    if (userWords.has(w)) return;
    userWords.add(w);
    chrome.storage.sync.set({ userWords: [...settings.userWords, w] });
    toast(null, null, message);
  }

  // ---------- 문맥 교정 ----------
  const CONTEXT_WORDS = 3;
  const SPACE = /^[  ]$/;

  /**
   * start 바로 앞에 띄어쓰기 하나씩으로 이어진 단어 중, 이번 교정과 같은 방향으로 함께 고칠 단어들.
   * 혼자서는 건너뛴 짧은 단어(한글 모드로 친 go → '해')를 뒤 단어(job)가 고쳐질 때 같이 고침.
   */
  function contextBefore(el, text, start, toEnglish) {
    const out = [];
    let pos = start;
    for (let i = 0; i < CONTEXT_WORDS; i++) {
      // contenteditable은 띄어쓰기를 &nbsp;(U+00A0)로 넣기도 함
      if (!SPACE.test(text[pos - 1] || '') || SPACE.test(text[pos - 2] || '')) break;
      const t = findToken(text, pos - 1);
      if (!t) break;
      const lower = t.token.toLowerCase();
      if (userWords.has(lower) || retyped(el, t.token) || isKept(t.token)) break;
      // 영문 → 한글은 '영어 단어가 아님'을 확인해야 하므로 사전 결과가 꼭 있어야 함
      if (!toEnglish && !cache.has(lower)) break;
      // 혼자서도 고쳐질 단어가 그대로 남아 있다면 일부러 둔 것(다시 쓰기, 되돌리기 등) → 문맥으로 끌어오지 않음
      if (HY.decide(t.token, dict)) break;
      const fixed = HY.decideContext(t.token, dict, toEnglish);
      if (!fixed) break;
      out.unshift({ start: t.start, token: t.token, fixed });
      pos = t.start;
    }
    return out;
  }

  /** 동기적으로 판단 가능하면 바로 고치고 true */
  function tryFix(ctx, tok, { midWord = false } = {}) {
    const cont = isContinuation(ctx.el, tok);
    if (!cont) {
      const idx = retypeIndex(ctx.el, tok.token, midWord);
      if (idx >= 0) {
        // 고친 단어를 지우고 그 자리에 다시 씀 → 이번만 그대로 (배우지 않으므로 다음 같은 실수는 다시 고침)
        if (!midWord) {
          recentFixes.get(ctx.el).splice(idx, 1);
          keepWord(tok.token);
          toast(null, null, `다시 쓰셔서 ‘${tok.token}’은(는) 이 탭에서 10분 동안 그대로 둘게요`);
        }
        return true;
      }
      // 다른 단어를 끝까지 썼으면 '그 자리에 다시 쓰기'는 끝남
      if (!midWord) recentFixes.set(ctx.el, []);
      if (isKept(tok.token, midWord)) return true; // 일부러 다시 썼던 단어

    }
    // 길이 제한은 decide()가 키 개수로 판단 (한글 2글자도 키는 4개 이상일 수 있음)
    if (!cont && tok.token.length < 2) {
      lookup(candidates(tok.token)); // 뒤 단어가 고쳐질 때 문맥 교정에 쓰도록 미리 조회
      return true;
    }
    const fixed = judge(tok, cont, midWord);
    if (fixed === undefined) return false;
    if (!fixed) return true;

    let { start, end } = tok;
    let replacement = fixed;
    let contAt = null;
    let context = [];
    if (midWord) {
      // 아직 치고 있는 마지막 글자는 남겨 두고 앞부분만 교정
      const last = [...fixed].pop();
      end = tok.end - HY.hangulToEng(last).length;
      replacement = fixed.slice(0, -1);
      if (end <= start || !replacement) return true;
    }
    if (!cont) {
      // 문맥 교정: 앞의 짧은 단어도 같은 방향으로 함께 (띄어쓰기 전 중간 교정 포함)
      context = contextBefore(ctx.el, ctx.text, tok.start, /^[A-Za-z]+$/.test(fixed));
      if (context.length) {
        start = context[0].start;
        replacement = [...context.map((w) => w.fixed), replacement].join(' ');
      }
    }
    if (midWord) contAt = start + replacement.length;
    const word = tok.token.slice(0, end - tok.start);
    const original = ctx.text.slice(start, end);
    replaceRange(ctx, start, end, replacement);
    // 이어서 친 글자를 고친 경우에도 되돌리기 학습은 단어 전체(처음 원문)를 기준으로
    const prev = cont ? lastFix.get(ctx.el) : null;
    const learn = prev ? prev.learn + word : word;
    lastFix.set(ctx.el, {
      contAt, start: prev ? prev.start : start,
      original: prev ? prev.original + original : original,
      fixed: prev ? prev.fixed + replacement : replacement,
      learn,
      time: Date.now(),
    });
    rememberFix(ctx.el, [...context.map((w) => w.token), learn], !!prev);
    if (!cont) toast(original, replacement);
    return true;
  }

  function checkAsync(el, end, opts) {
    const ctx = readContext(el);
    if (!ctx) return;
    const tok = findToken(ctx.text, end);
    if (!tok) return;
    if (tryFix(ctx, tok, opts)) return;
    lookup(candidates(tok.token)).then(() => {
      const run = () => {
        if (el.ownerDocument.activeElement !== el && !el.contains(el.ownerDocument.activeElement)) return;
        const now = readContext(el);
        if (!now || (now.kind === 'ce' && now.node !== ctx.node && !ctx.node.isConnected)) return;
        const text = now.kind === 'ce' ? ctx.node.data : now.text;
        if (text.slice(tok.start, tok.end) !== tok.token) return; // 그 사이 내용이 바뀜
        tryFix({ ...now, node: ctx.node ?? now.node }, tok, opts);
      };
      if (composing) afterComposition.push(run);
      else run();
    });
  }

  // ---------- 이벤트 ----------
  window.addEventListener('compositionstart', () => { composing = true; }, true);
  window.addEventListener('compositionend', () => {
    composing = false;
    const jobs = afterComposition;
    afterComposition = [];
    setTimeout(() => jobs.forEach((f) => f()), 0);
  }, true);

  window.addEventListener('input', (e) => {
    if (selfEdit || e.isComposing || !active()) return;
    const el = editableOf(e.target);
    if (el && e.inputType?.startsWith('delete')) erased.set(el, true);
    if (!el || e.inputType !== 'insertText' || !e.data) return;
    const ctx = readContext(el);
    if (!ctx) return;

    if (BOUNDARY.test(e.data)) {
      // contenteditable에서는 끝에 친 띄어쓰기 직후 커서가 띄어쓰기 앞으로 보고될 때가 있음 →
      // 커서 바로 앞이 경계 문자일 때만 그만큼 빼서 단어 끝을 찾음
      const end = ctx.caret > 0 && BOUNDARY.test(ctx.text[ctx.caret - 1]) ? ctx.caret - 1 : ctx.caret;
      checkAsync(el, end);
      return;
    }
    const tok = findToken(ctx.text, ctx.caret);
    if (!tok) return;
    lookup(candidates(tok.token)); // Enter 대비 미리 조회
    // 기준 글자 수 이상이면 글자를 칠 때마다 검사 (영어 단어의 앞부분처럼 보이면 다음 글자에서 다시 판단)
    if (/^[A-Za-z]$/.test(e.data) && tok.token.length >= settings.checkLength) {
      checkAsync(el, ctx.caret, { midWord: true });
    }
  }, true);

  window.addEventListener('keydown', (e) => {
    if (!active()) return;
    const el = editableOf(e.target);
    if (!el) return;

    // 고친 직후 되돌리면 그 단어는 앞으로 고치지 않음
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === 'z') {
      const f = lastFix.get(el);
      const ctx = f && readContext(el);
      // 고친 글자가 아직 그 자리에 있을 때만 (다른 편집을 되돌리는 경우는 학습하지 않음)
      const stillThere = ctx && ctx.text.slice(f.start, f.start + f.fixed.length) === f.fixed;
      if (f && stillThere && Date.now() - f.time < 8000) {
        lastFix.delete(el);
        // 문맥 교정으로 함께 고친 경우에도 배우는 것은 마지막 단어만
        learnWord(f.learn || f.original, `‘${f.learn || f.original}’은(는) 앞으로 고치지 않을게요`);
      }
      return;
    }
    // Enter: 이미 사전 결과가 있으면 기본 동작(전송 등) 전에 동기로 교정
    if (e.key === 'Enter' && !e.isComposing && e.keyCode !== 229) {
      const ctx = readContext(el);
      const tok = ctx && findToken(ctx.text, ctx.caret);
      if (tok) tryFix(ctx, tok);
    }
  }, true);

  // ---------- 알림 ----------
  let toastHost = null;
  let toastTimer = null;
  function toast(from, to, message) {
    if (!settings.showToast || window.top !== window && !document.hasFocus()) return;
    if (!toastHost) {
      toastHost = document.createElement('div');
      toastHost.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:2147483647;pointer-events:none;';
      const shadow = toastHost.attachShadow({ mode: 'open' });
      shadow.innerHTML = `
        <style>
          .t{font:13px/1.45 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;
             background:#1f2328;color:#f6f8fa;padding:9px 13px;border-radius:10px;max-width:320px;
             box-shadow:0 6px 24px rgba(0,0,0,.25);opacity:0;transform:translateY(6px);transition:.18s}
          .t.on{opacity:1;transform:none}
          b{color:#7ee2a8;font-weight:600} s{color:#9aa4ae} .h{color:#9aa4ae;font-size:12px}
        </style><div class="t"></div>`;
      document.documentElement.appendChild(toastHost);
    }
    const box = toastHost.shadowRoot.querySelector('.t');
    const esc = (s) => s.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[c]);
    box.innerHTML = message
      ? esc(message)
      : `<s>${esc(from)}</s> → <b>${esc(to)}</b><div class="h">한/영 키를 확인하세요 · Ctrl+Z로 되돌리기</div>`;
    box.classList.add('on');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => box.classList.remove('on'), 2600);
  }
})();
