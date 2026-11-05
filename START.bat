@echo off
chcp 65001 >nul
title SubTrans Auto - راه انداز خودکار

echo ====================================================
echo        SubTrans Auto - راه انداز مترجم هوشمند زیرنویس
echo ====================================================
echo.

:: 1. بررسی پایتون
set "PY_CMD="
py -3 --version >nul 2>&1
if %errorlevel% == 0 (
    set "PY_CMD=py -3"
) else (
    python --version >nul 2>&1
    if %errorlevel% == 0 (
        set "PY_CMD=python"
    )
)

if "%PY_CMD%"=="" (
    echo [خطا] پایتون روی سیستم شما پیدا نشد!
    echo.
    echo راه حل:
    echo 1. با زدن کلیدهای Win+R و نوشتن cmd، این دستور را اجرا کنید:
    echo    winget install Python.Python.3.11
    echo 2. یا از سایت رسمی https://www.python.org/downloads نسخه 3.11 به بالا را دانلود و نصب کنید.
    echo * حتما هنگام نصب تیک "Add python.exe to PATH" را بزنید.
    echo.
    pause
    exit /b 1
)

echo [+] پایتون پیدا شد: %PY_CMD%

:: 2. بررسی و ایجاد محیط مجازی .venv
if not exist ".venv\Scripts\activate.bat" (
    echo [+] در حال ساخت محیط مجازی .venv ...
    %PY_CMD% -m venv .venv
    if %errorlevel% neq 0 (
        echo [خطا] ساخت محیط مجازی با خطا مواجه شد.
        pause
        exit /b 1
    )
)

:: 3. فعال‌سازی محیط مجازی
call .venv\Scripts\activate.bat

:: 4. نصب و به‌روزرسانی وابستگی‌ها
echo [+] بررسی نیازمندی‌های برنامه...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt
if %errorlevel% neq 0 (
    echo [خطا] نصب بسته‌های مورد نیاز ناموفق بود.
    pause
    exit /b 1
)

:: 5. بررسی سلامت اولیه
echo [+] بررسی ابزارهای جانبی...
python -m subtrans doctor

:: 6. اجرای وب‌سرور
echo.
echo [+] در حال باز کردن برنامه در مرورگر...
python -m subtrans web

if %errorlevel% neq 0 (
    echo.
    echo [خطا] برنامه با خطا متوقف شد.
    pause
)
