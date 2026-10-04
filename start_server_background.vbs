' ============================================================================
' Karachi Gymkhana Club - RFID VAMS
' Silent Background Launcher (No visible CMD window)
' ============================================================================
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

strCurDir = fso.GetParentFolderName(WScript.ScriptFullName)
strBatPath = fso.BuildPath(strCurDir, "start_server.bat")

' Run start_server.bat in hidden window (window style 0, false for wait)
WshShell.CurrentDirectory = strCurDir
WshShell.Run Chr(34) & strBatPath & Chr(34), 0, False

Set WshShell = Nothing
Set fso = Nothing
