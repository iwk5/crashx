@echo off
REM Launcher that bypasses the Microsoft Store "python.exe" alias.
REM Double-click to run with dashboard, or from a terminal:
REM   start.bat             (monitor + dashboard)
REM   start.bat --once      (one iteration, no dashboard)
"C:\Users\iwk4c\AppData\Local\Programs\Python\Python312\python.exe" main.py %*