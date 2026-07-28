; ============================================================
;  Helix Core v3.0.0 -- Smart Portable Launcher
;
;  First launch:  shows splash, extracts to %APPDATA%\HelixCoreApp\
;  Next launches: detects version marker -> instant launch
;  New version:   cleans old cache -> extracts fresh
;
;  Sets PORTABLE_EXECUTABLE_DIR so the workspace (output files)
;  is created next to wherever the user placed this exe.
; ============================================================

!include "FileFunc.nsh"
!include "LogicLib.nsh"

; --- Configuration ---
!define APP_NAME      "Helix Core"
!define APP_VERSION   "3.0.0"
!define CACHE_REV     "3"
!define APP_EXE       "Helix Core.exe"
!define CACHE_DIR     "$APPDATA\HelixCoreApp"
!define MARKER        ".v${APP_VERSION}-${CACHE_REV}"
!define SPLASH_DONE   "$TEMP\helix_splash_done"

; --- Output ---
Name "${APP_NAME}"
OutFile "HelixCore-3.0.0-portable.exe"
Icon "frontend\resources\icon.ico"
Unicode True
RequestExecutionLevel user
SilentInstall silent

; --- Compression ---
SetCompressor /SOLID lzma
SetCompressorDictSize 64

; ============================================================
;  .onInit -- instant launch if cache is valid
; ============================================================

Function .onInit
  ; Cache hit: marker + exe both exist -> launch immediately
  ${If} ${FileExists} "${CACHE_DIR}\${MARKER}"
    ${If} ${FileExists} "${CACHE_DIR}\${APP_EXE}"
      System::Call 'Kernel32::SetEnvironmentVariable(t "PORTABLE_EXECUTABLE_DIR", t "$EXEDIR")i'
      SetOutPath "${CACHE_DIR}"
      Exec '"${CACHE_DIR}\${APP_EXE}"'
      Quit
    ${EndIf}
  ${EndIf}

  ; Cache stale or missing -- wipe it
  ${If} ${FileExists} "${CACHE_DIR}\*.*"
    RMDir /r "${CACHE_DIR}"
  ${EndIf}
FunctionEnd

; ============================================================
;  Main section -- splash + extract + marker
; ============================================================

Section "Extract"
  ; --- Launch dark splash screen (non-blocking, truly hidden) ---
  InitPluginsDir
  File /oname=$PLUGINSDIR\splash.ps1 "splash.ps1"
  File /oname=$PLUGINSDIR\icon.png   "frontend\resources\icon.png"
  Delete "${SPLASH_DONE}"

  ; Launch splash via PowerShell directly (no VBScript dependency)
  ; ExecShell with SW_HIDE = async + no console window flash
  ExecShell "" "powershell.exe" '-ExecutionPolicy Bypass -WindowStyle Hidden -NoProfile -File "$PLUGINSDIR\splash.ps1" -IconPath "$PLUGINSDIR\icon.png" -DoneFile "${SPLASH_DONE}"' SW_HIDE

  ; --- Extract all application files ---
  SetOutPath "${CACHE_DIR}"
  File /r "frontend\release\win-unpacked\*.*"

  ; --- Write version marker ---
  FileOpen $0 "${CACHE_DIR}\${MARKER}" w
  FileWrite $0 "${APP_VERSION}"
  FileClose $0

  ; --- Signal splash to close ---
  FileOpen $0 "${SPLASH_DONE}" w
  FileClose $0
  Sleep 600
  Delete "${SPLASH_DONE}"
SectionEnd

; ============================================================
;  Post-install -- launch the app
; ============================================================

Function .onInstSuccess
  System::Call 'Kernel32::SetEnvironmentVariable(t "PORTABLE_EXECUTABLE_DIR", t "$EXEDIR")i'
  Exec '"${CACHE_DIR}\${APP_EXE}"'
FunctionEnd
