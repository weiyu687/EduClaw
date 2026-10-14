"""Reviewed Windows PowerShell commands, bounded output and owned process trees."""
import base64
import json
import os
from pathlib import Path
import subprocess
import threading
import time


from core.security.terminal_policy import terminal_arguments


def run_terminal(cwd:str,command:str,timeout_seconds:int=60)->str:
    from core.security.tool_cancellation import current_cancel_event
    args=terminal_arguments({'cwd':cwd,'command':command,'timeout_seconds':timeout_seconds})
    import win32api,win32con,win32event,win32file,win32job,win32pipe,win32process,pywintypes
    executable=str(Path(os.environ['SystemRoot'])/'System32'/'WindowsPowerShell'/'v1.0'/'powershell.exe')
    # No profile, interactive stdin or credential-bearing inherited environment.
    env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PATH','PATHEXT','TEMP','TMP','COMSPEC','USERPROFILE','HOMEDRIVE','HOMEPATH','APPDATA','LOCALAPPDATA','PROGRAMFILES','PROGRAMFILES(X86)','PROGRAMDATA','PSMODULEPATH','SYSTEMDRIVE','NUMBER_OF_PROCESSORS','PROCESSOR_ARCHITECTURE'}}
    script="$ProgressPreference='SilentlyContinue'; $ErrorActionPreference='Stop'; [Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false); $OutputEncoding=[Console]::OutputEncoding; $global:LASTEXITCODE=0;\n& {\n"+command+"\n}\nif ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; if (-not $?) { exit 1 }"
    argv=[executable,'-NoLogo','-NoProfile','-NonInteractive','-OutputFormat','Text','-EncodedCommand',base64.b64encode(script.encode('utf-16le')).decode()]
    handles=[];readers=[];job=None;process=None;started=time.monotonic();cancel=current_cancel_event()
    buffers=[bytearray(),bytearray()];truncated=[False,False]
    def drain(handle,index):
        try:
            while True:
                _,chunk=win32file.ReadFile(handle,4096)
                if not chunk:break
                room=32768-len(buffers[index]);buffers[index].extend(chunk[:room])
                if len(chunk)>room:truncated[index]=True
        except pywintypes.error as exc:
            if exc.winerror not in (109,6):truncated[index]=True
    try:
        security=pywintypes.SECURITY_ATTRIBUTES();security.bInheritHandle=True
        out_read,out_write=win32pipe.CreatePipe(security,0);handles.extend([out_read,out_write])
        err_read,err_write=win32pipe.CreatePipe(security,0);handles.extend([err_read,err_write])
        for handle in (out_read,err_read):win32api.SetHandleInformation(handle,win32con.HANDLE_FLAG_INHERIT,0)
        stdin=win32file.CreateFile('NUL',win32con.GENERIC_READ,win32con.FILE_SHARE_READ|win32con.FILE_SHARE_WRITE,security,win32con.OPEN_EXISTING,0,None);handles.append(stdin)
        startup=win32process.STARTUPINFO();startup.dwFlags=win32process.STARTF_USESTDHANDLES|win32process.STARTF_USESHOWWINDOW
        startup.wShowWindow=0;startup.hStdInput=stdin;startup.hStdOutput=out_write;startup.hStdError=err_write
        job=win32job.CreateJobObject(None,'')
        limits=win32job.QueryInformationJobObject(job,win32job.JobObjectExtendedLimitInformation)
        limits['BasicLimitInformation']['LimitFlags']=win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        win32job.SetInformationJobObject(job,win32job.JobObjectExtendedLimitInformation,limits)
        process,thread,pid,_=win32process.CreateProcess(executable,subprocess.list2cmdline(argv),None,None,True,win32process.CREATE_SUSPENDED|win32process.CREATE_NO_WINDOW,env,args['cwd'],startup)
        handles.extend([process,thread])
        try:win32job.AssignProcessToJobObject(job,process)
        except BaseException:
            win32api.TerminateProcess(process,1);raise
        for handle in (out_write,err_write,stdin):handle.Close();handles.remove(handle)
        for index,handle in enumerate((out_read,err_read)):
            reader=threading.Thread(target=drain,args=(handle,index),daemon=True);reader.start();readers.append(reader)
        state='cancelled' if cancel and cancel.is_set() else 'completed'
        if state=='cancelled':win32job.TerminateJobObject(job,1)
        else:win32process.ResumeThread(thread)
        while win32event.WaitForSingleObject(process,100)==win32event.WAIT_TIMEOUT:
            if cancel and cancel.is_set():state='cancelled';break
            if time.monotonic()-started>=timeout_seconds:state='timed_out';break
        if state!='completed':win32job.TerminateJobObject(job,1)
        win32event.WaitForSingleObject(process,5000)
        exit_code=win32process.GetExitCodeProcess(process)
        # No background daemons survive a command, even after a successful shell exit.
        job.Close();job=None
        for reader in readers:reader.join(timeout=3)
        if state=='completed' and exit_code!=0:state='nonzero_exit'
        return json.dumps({'cwd':args['cwd'],'shell':'Windows PowerShell','command':command,'exit_code':exit_code,'execution_status':state,'stdout':buffers[0].decode('utf-8',errors='replace'),'stderr':buffers[1].decode('utf-8',errors='replace'),'truncated':any(truncated),'duration_seconds':round(time.monotonic()-started,3)},ensure_ascii=False)
    finally:
        if job is not None:job.Close()
        for reader in readers:reader.join(timeout=3)
        for handle in reversed(handles):
            try:handle.Close()
            except Exception:pass
