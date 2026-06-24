@echo off
REM init-project.bat — init-project-files.py 的 Windows 包装
REM 自动查找 Python 可执行文件，用户无需关心路径

set "SCRIPT_DIR=%~dp0"
set "PYTHON="

REM 1. 尝试从用户配置的路径找 Python
if exist "{USER_HOME}\AppData\Local\Programs\Python\Python312\{PYTHON_EXE}" (
    set "PYTHON={USER_HOME}\AppData\Local\Programs\Python\Python312\{PYTHON_EXE}"
    goto :RUN
)

REM 2. 尝试 PATH 中的 python
for %%i in ({PYTHON_EXE}) do set "PYTHON=%%~$PATH:i"
if defined PYTHON goto :RUN

REM 3. 尝试常见安装路径
if exist "%LOCALAPPDATA%\Programs\Python\Python312\{PYTHON_EXE}" (
    set "PYTHON=%LOCALAPPDATA%\Programs\Python\Python312\{PYTHON_EXE}"
    goto :RUN
)
if exist "%LOCALAPPDATA%\Programs\Python\Python311\{PYTHON_EXE}" (
    set "PYTHON=%LOCALAPPDATA%\Programs\Python\Python311\{PYTHON_EXE}"
    goto :RUN
)
if exist "C:\Python312\{PYTHON_EXE}" (
    set "PYTHON=C:\Python312\{PYTHON_EXE}"
    goto :RUN
)

echo [!] 未找到 Python 可执行文件
echo     请将 Python 添加到 PATH 或编辑此 .bat 文件手动设置路径
pause
exit /b 1

:RUN
"%PYTHON%" "%SCRIPT_DIR%init-project-files.py" %*
