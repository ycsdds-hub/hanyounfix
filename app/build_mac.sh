#!/bin/bash
# HanYoungFix.app 만들기 (macOS에서 실행)
set -euo pipefail
cd "$(dirname "$0")"
python3 -m pip install -r requirements-mac.txt pyinstaller==6.10.0

# 아이콘(.icns)
rm -rf HanYoungFix.iconset && mkdir HanYoungFix.iconset
for s in 16 32 128 256 512; do
  sips -z $s $s ../extension/icons/icon128.png --out "HanYoungFix.iconset/icon_${s}x${s}.png" >/dev/null
  d=$((s * 2))
  sips -z $d $d ../extension/icons/icon128.png --out "HanYoungFix.iconset/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns HanYoungFix.iconset -o icon.icns

python3 -m PyInstaller --noconfirm --windowed --name HanYoungFix --icon icon.icns \
  --osx-bundle-identifier com.hanyoungfix.app \
  --hidden-import HIServices \
  --exclude-module tkinter --exclude-module PIL --exclude-module pystray \
  --exclude-module hanyoung.ui --exclude-module hanyoung.win32 \
  --add-data "../extension/words.txt:." --add-data "../extension/common.txt:." \
  --add-data "../extension/icons/icon32.png:icons" --add-data "../extension/icons/icon128.png:icons" \
  main.py

# 메뉴 막대 전용 앱(Dock 아이콘 없음), 이름·버전
P=dist/HanYoungFix.app/Contents/Info.plist
plutil -replace LSUIElement -bool true "$P"
plutil -replace CFBundleDisplayName -string "HanYoungFix" "$P"
plutil -replace CFBundleShortVersionString -string "0.3.0" "$P"
# Info.plist를 고쳤으니 다시 서명 (애플 실리콘에서는 서명이 맞아야 실행됨, 개인용 임시 서명)
codesign --force --deep -s - dist/HanYoungFix.app
(cd dist && rm -f HanYoungFix-mac.zip && ditto -c -k --keepParent HanYoungFix.app HanYoungFix-mac.zip)
echo "완성: $(pwd)/dist/HanYoungFix.app"
