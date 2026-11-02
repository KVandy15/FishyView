Set-Location $PSScriptRoot
python -m pip install pyinstaller
python tools\make_icon.py
python -m PyInstaller --noconfirm --windowed --name FishyView --icon assets\FishyView.ico --collect-all av --collect-all moderngl --collect-all glcontext run.py
