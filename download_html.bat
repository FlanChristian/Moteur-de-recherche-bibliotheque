@echo off
echo.
echo ========================================
echo   TELECHARGEMENT HTML GUTENBERG
echo ========================================
echo.
echo Mode: TEXT/PLAIN ou HTML (extraction auto)
echo Cible: 2000 livres (^>= 10000 mots)
echo Langues: anglais + francais
echo.
echo IMPORTANT: Installe beautifulsoup4 si necessaire
echo pip install beautifulsoup4
echo.

cd /d "%~dp0"

REM Vérifie et installe beautifulsoup4 si nécessaire
echo Verification de beautifulsoup4...
"C:\Users\Hamid\AppData\Local\Programs\Python\Python313\python.exe" -c "import bs4" 2>nul
if errorlevel 1 (
    echo Installation de beautifulsoup4...
    "C:\Users\Hamid\AppData\Local\Programs\Python\Python313\python.exe" -m pip install beautifulsoup4
    echo.
)

set FETCH_TARGET=2000
set FETCH_LANGS=en,fr
set FETCH_MIN_WORDS=10000
set FETCH_RATE_S=1.0
set FETCH_TIMEOUT_S=90
set FETCH_START_PAGE=1

echo Demarrage du telechargement...
echo (duree estimee: 2-3 heures)
echo.

"C:\Users\Hamid\AppData\Local\Programs\Python\Python313\python.exe" fetcher\fetch_gutenberg_html.py

echo.
echo ========================================
echo   TELECHARGEMENT TERMINE
echo ========================================
echo.
pause
