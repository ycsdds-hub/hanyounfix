"""macOS 키 코드 ↔ 엔진이 쓰는 키 번호(Windows 가상 키 코드) 변환, 입력 소스 판별.

macOS에 의존하지 않는 순수 코드라 Windows/Linux에서도 테스트합니다.
엔진(engine.py)은 Windows 가상 키 코드(VK)로 판단하므로, Mac의 키 코드를 VK로 바꿔 넘기고
교정할 때는 다시 Mac 키 코드로 바꿔 보냅니다.
"""
from __future__ import annotations

# macOS ANSI 키 코드 (HIToolbox/Events.h kVK_*) → VK
_LETTERS = {
    'A': 0x00, 'S': 0x01, 'D': 0x02, 'F': 0x03, 'H': 0x04, 'G': 0x05, 'Z': 0x06, 'X': 0x07,
    'C': 0x08, 'V': 0x09, 'B': 0x0B, 'Q': 0x0C, 'W': 0x0D, 'E': 0x0E, 'R': 0x0F, 'Y': 0x10,
    'T': 0x11, 'O': 0x1F, 'U': 0x20, 'I': 0x22, 'P': 0x23, 'L': 0x25, 'J': 0x26, 'K': 0x28,
    'N': 0x2D, 'M': 0x2E,
}
_DIGITS = {'1': 0x12, '2': 0x13, '3': 0x14, '4': 0x15, '6': 0x16, '5': 0x17, '9': 0x19,
           '7': 0x1A, '8': 0x1C, '0': 0x1D}

MAC_TO_VK: dict[int, int] = {}
for ch, code in _LETTERS.items():
    MAC_TO_VK[code] = ord(ch)
for ch, code in _DIGITS.items():
    MAC_TO_VK[code] = ord(ch)
MAC_TO_VK.update({
    0x31: 0x20,  # Space
    0x24: 0x0D,  # Return
    0x4C: 0x0D,  # Keypad Enter
    0x33: 0x08,  # Delete(백스페이스)
    0x75: 0x2E,  # Forward Delete
    0x30: 0x09,  # Tab
    0x35: 0x1B,  # Escape
    0x2B: 0xBC,  # ,
    0x2F: 0xBE,  # .
    0x29: 0xBA,  # ;
    0x2C: 0xBF,  # /
    0x27: 0xDE,  # '
    0x1B: 0xBD,  # -
    0x18: 0xBB,  # =
    0x21: 0xDB,  # [
    0x1E: 0xDD,  # ]
    0x2A: 0xDC,  # backslash
    0x32: 0xC0,  # `
    0x38: 0xA0, 0x3C: 0xA1,  # Shift L/R
    0x3B: 0xA2, 0x3E: 0xA3,  # Control L/R
    0x3A: 0xA4, 0x3D: 0xA5,  # Option L/R
    0x37: 0x5B, 0x36: 0x5C,  # Command L/R
    0x39: 0x14,  # Caps Lock
    0x7B: 0x25, 0x7E: 0x26, 0x7C: 0x27, 0x7D: 0x28,  # ← ↑ → ↓
    0x73: 0x24, 0x77: 0x23, 0x74: 0x21, 0x79: 0x22,  # Home End PageUp PageDown
})
# 숫자 키패드 0~9
for i, code in enumerate((0x52, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59, 0x5B, 0x5C)):
    MAC_TO_VK[code] = 0x60 + i

VK_TO_MAC: dict[int, int] = {}
for mac, vk in MAC_TO_VK.items():
    VK_TO_MAC.setdefault(vk, mac)

OTHER_VK = 0xFF  # 표에 없는 키(F키 등): 엔진에서 '단어가 끊김'으로 처리됨


def to_vk(mac_keycode: int) -> int:
    return MAC_TO_VK.get(mac_keycode, OTHER_VK)


def to_mac(vk: int) -> int | None:
    return VK_TO_MAC.get(vk)


# ---------- 입력 소스 ----------
def mode_of_source(source_id: str | None) -> str | None:
    """입력 소스 ID → 'ko' / 'en' / None(알 수 없음, 교정하지 않음)

    - 한국어 두벌식: com.apple.inputmethod.Korean.2SetKorean 등 → 'ko'
      (세벌식 등 다른 자판은 키 배치가 달라 교정하면 안 되므로 None)
    - 영문 자판: com.apple.keylayout.ABC / US / British 등 → 'en'
      (Dvorak, Colemak 등 배치가 다른 영문 자판은 None)
    """
    if not source_id:
        return None
    s = source_id
    if s.startswith('com.apple.inputmethod.Korean'):
        if s.endswith('.Roman'):
            return 'en'
        return 'ko' if '2Set' in s else None
    if s.startswith('com.apple.keylayout.'):
        name = s.rsplit('.', 1)[-1]
        if any(x in name for x in ('Dvorak', 'Colemak', 'Workman')):
            return None
        return 'en'
    return None


def pick_source(source_ids: list[str], mode: str, preferred_en: str | None = None) -> str | None:
    """설치된 입력 소스 중 mode로 바꿀 때 고를 소스 ID"""
    if mode == 'ko':
        for s in source_ids:
            if mode_of_source(s) == 'ko':
                return s
        return None
    if preferred_en and preferred_en in source_ids and mode_of_source(preferred_en) == 'en':
        return preferred_en
    for want in ('com.apple.keylayout.ABC', 'com.apple.keylayout.US'):
        if want in source_ids:
            return want
    for s in source_ids:
        if mode_of_source(s) == 'en':
            return s
    return None
