#!/bin/bash
# 1. プロジェクトフォルダに移動
cd /home/takeo/tracking-gimbal
# 2. 仮想環境（venv）を起動
source venv/bin/activate
# 3. 親GUIを実行
python gui_manager.py
