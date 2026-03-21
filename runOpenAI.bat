@echo off
echo.
echo 正在通过 PowerShell 运行脚本...
echo.
powershell -ExecutionPolicy Bypass -Command "cd '%~dp0'; Write-Host '激活 Conda 环境...' -ForegroundColor Cyan; conda activate base; Write-Host ''; Write-Host '检查 Python 版本...' -ForegroundColor Cyan; python --version; Write-Host ''; Write-Host '运行 Python 脚本...' -ForegroundColor Cyan; Write-Host ''; python openai_register_v2.py; Write-Host ''; Write-Host '脚本执行完毕!' -ForegroundColor Green; Write-Host ''; Read-Host '按回车键退出'"
