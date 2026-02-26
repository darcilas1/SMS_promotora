@echo off
REM Ir a la carpeta del proyecto
cd /d "C:\Users\lcastillo\Documents\Development\CIAO_3"
 
REM Activar el entorno virtual
call venv\Scripts\activate.bat
 
REM Ejecutar el orquestador
python orquestador.py