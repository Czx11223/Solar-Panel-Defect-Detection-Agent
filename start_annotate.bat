@echo off
REM 启动 LabelImg 标注工具（光伏缺陷检测数据集标注用）
REM 自动打开 data/images 并加载六类预置标签
start "" "C:\Users\20454\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\vm\tools\python\Scripts\labelImg.exe" "d:\peixunwenjian\2026.9.14-9.28\algorithm\data\images" "d:\peixunwenjian\2026.9.14-9.28\algorithm\data\predefined_classes.txt"
