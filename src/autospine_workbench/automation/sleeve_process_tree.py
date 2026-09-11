"""Own only this workflow's descendants; gate execution until containment exists."""
import ctypes
import os
import signal
import subprocess

GATE = "import sys,runpy; gate=sys.stdin.buffer.read(1); sys.exit(125) if gate!=b'1' else None; sys.argv=sys.argv[1:]; runpy.run_path(sys.argv[0],run_name='__main__')"


class WindowsJob:
    def __init__(self):
        from ctypes import wintypes as w
        class Basic(ctypes.Structure):
            _fields_ = [('process_time',ctypes.c_int64),('job_time',ctypes.c_int64),
                ('flags',w.DWORD),('min_ws',ctypes.c_size_t),('max_ws',ctypes.c_size_t),
                ('active',w.DWORD),('affinity',ctypes.c_size_t),('priority',w.DWORD),('scheduling',w.DWORD)]
        class Io(ctypes.Structure):
            _fields_ = [(name,ctypes.c_uint64) for name in ('read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes')]
        class Extended(ctypes.Structure):
            _fields_ = [('basic',Basic),('io',Io),('process_memory',ctypes.c_size_t),
                ('job_memory',ctypes.c_size_t),('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]
        self.api = ctypes.WinDLL('kernel32',use_last_error=True)
        signatures = {'CreateJobObjectW':([ctypes.c_void_p,w.LPCWSTR],w.HANDLE),
            'SetInformationJobObject':([w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD],w.BOOL),
            'OpenProcess':([w.DWORD,w.BOOL,w.DWORD],w.HANDLE),
            'AssignProcessToJobObject':([w.HANDLE,w.HANDLE],w.BOOL),
            'TerminateJobObject':([w.HANDLE,w.UINT],w.BOOL), 'CloseHandle':([w.HANDLE],w.BOOL)}
        for name,(args,result) in signatures.items():
            method=getattr(self.api,name);method.argtypes=args;method.restype=result
        self.handle=self.api.CreateJobObjectW(None,None)
        if not self.handle:raise ctypes.WinError(ctypes.get_last_error())
        limits=Extended();limits.basic.flags=0x2000  # KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(self.handle,9,ctypes.byref(limits),ctypes.sizeof(limits)):
            error=ctypes.WinError(ctypes.get_last_error());self.close();raise error

    def assign(self,pid):
        process=self.api.OpenProcess(0x0101,False,pid)  # SET_QUOTA | TERMINATE
        if not process:raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not self.api.AssignProcessToJobObject(self.handle,process):raise ctypes.WinError(ctypes.get_last_error())
        finally:self.api.CloseHandle(process)

    def terminate(self):
        if self.handle and not self.api.TerminateJobObject(self.handle,125):raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle:self.api.CloseHandle(self.handle);self.handle=None


class SleeveProcessTree:
    def __init__(self,command,**options):
        if command[1]!='-u':raise ValueError('sleeve_process_command_invalid')
        self.job=WindowsJob() if os.name=='nt' else None
        self.process=None
        try:
            self.process=subprocess.Popen([command[0],'-u','-c',GATE,*command[2:]],
                stdin=subprocess.PIPE,start_new_session=os.name!='nt',**options)
            if self.job:self.job.assign(self.process.pid)
        except BaseException:
            if self.process:self.process.kill();self.process.wait()
            if self.job:self.job.close()
            raise

    def release(self):
        self.process.stdin.write('1');self.process.stdin.flush();self.process.stdin.close()

    def terminate(self):
        if self.job:self.job.terminate()
        else:
            try:os.killpg(self.process.pid,signal.SIGKILL)
            except ProcessLookupError:pass

    def close(self):
        self.terminate();self.process.wait()
        for stream in (self.process.stdin,self.process.stdout):
            if stream and not stream.closed:stream.close()
        if self.job:self.job.close()

    def __enter__(self):return self
    def __exit__(self,*exc):self.close()
