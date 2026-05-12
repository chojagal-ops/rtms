Set WShell = CreateObject("WScript.Shell")
WShell.Run "cmd /c pushd ""\\192.168.10.3\품질팀\AI프로그램\RTMS"" && call venv\Scripts\activate.bat && python app.py", 0, False
Set WShell = Nothing
