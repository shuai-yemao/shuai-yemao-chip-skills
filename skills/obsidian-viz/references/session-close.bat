@echo off
REM session-close.bat — 开发会话收尾包装器
REM 自动查找 Python，链式执行：devlog + dashboard --update

set "SCRIPT_DIR=%~dp0"
set "PYTHON="

REM 查找 Python（与 init-project.bat 共用逻辑）
if exist "{USER_HOME}\AppData\Local\Programs\Python\Python312\{PYTHON_EXE}" (
    set "PYTHON={USER_HOME}\AppData\Local\Programs\Python\Python312\{PYTHON_EXE}"
    goto :RUN
)
for %%i in ({PYTHON_EXE}) do set "PYTHON=%%~$PATH:i"
if defined PYTHON goto :RUN
if exist "%LOCALAPPDATA%\Programs\Python\Python312\{PYTHON_EXE}" (
    set "PYTHON=%LOCALAPPDATA%\Programs\Python\Python312\{PYTHON_EXE}"
    goto :RUN
)

echo [!] 未找到 Python 可执行文件
pause
exit /b 1

:RUN
"%PYTHON%" "%SCRIPT_DIR%session-close.py" %*
