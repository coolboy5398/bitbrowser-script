@echo off
echo ========================================
echo 比特炉览器自动化脚本器动启动器
echo ========================================
echo.
echo 正在通过 PowerShell 运行脚本启...
echo.
powershell -ExecutionPolicy Bypass -Command "cd '%~dp0'; Write-Host '激活 Conda 环境...' -ForegroundColor Cyan; conda activate base; Write-Host ''; Write-Host '检查 Python 版本...' -ForegroundColor Cyan; python --version; Write-Host ''; Write-Host '运行 Python 脚本启...' -ForegroundColor Cyan; Write-Host ''; python openai_register.py; Write-Host ''; Write-Host '脚本启执行完毕!' -ForegroundColor Green; Write-Host ''; Read-Host '按回车键退出'"
