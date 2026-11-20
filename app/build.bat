@echo off
rem HanYoungFix.exe 만들기 (Windows에서 실행)
cd /d %~dp0
python -m pip install -r requirements.txt pyinstaller==6.10.0 || exit /b 1
python -c "from PIL import Image; Image.open('../extension/icons/icon128.png').save('icon.ico', sizes=[(16,16),(32,32),(48,48),(128,128)])"
python -m PyInstaller --noconfirm --onefile --windowed --name HanYoungFix --icon icon.ico ^
  --add-data "../extension/words.txt;." --add-data "../extension/common.txt;." ^
  --add-data "../extension/icons/icon128.png;icons" main.py || exit /b 1
echo.
echo 완성: %~dp0dist\HanYoungFix.exe
