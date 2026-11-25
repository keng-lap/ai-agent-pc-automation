using System.ComponentModel;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace InstallerHelper.Security;

/// <summary>
/// Helper-owned process-tree containment. The caller must create the root
/// installer process suspended, assign it, and only then resume its thread.
/// </summary>
public sealed class WindowsJobObject : IDisposable
{
    private const uint JobObjectExtendedLimitInformation = 9;
    private const uint JobObjectBasicAccountingInformation = 1;
    private const uint JobObjectLimitKillOnJobClose = 0x00002000;
    private const uint JobObjectLimitDieOnUnhandledException = 0x00000400;
    private readonly SafeJobHandle _handle;

    public WindowsJobObject()
    {
        EnsureWindows();
        _handle = NativeMethods.CreateJobObjectW(IntPtr.Zero, null);
        if (_handle.IsInvalid)
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not create the installer Job Object.");

        var limits = new ExtendedLimitInformation();
        limits.BasicLimitInformation.LimitFlags =
            JobObjectLimitKillOnJobClose | JobObjectLimitDieOnUnhandledException;
        if (!NativeMethods.SetInformationJobObject(
                _handle, JobObjectExtendedLimitInformation,
                ref limits, (uint)Marshal.SizeOf<ExtendedLimitInformation>()))
        {
            var error = Marshal.GetLastWin32Error();
            _handle.Dispose();
            throw new Win32Exception(error, "Could not configure kill-on-close process containment.");
        }
    }

    /// <summary>Assigns a process that must still be suspended.</summary>
    public void AssignSuspendedProcess(IntPtr processHandle)
    {
        EnsureOpen();
        if (processHandle == IntPtr.Zero || processHandle == new IntPtr(-1))
            throw new ArgumentException("A valid process handle is required.", nameof(processHandle));
        if (!NativeMethods.AssignProcessToJobObject(_handle, processHandle))
            throw new Win32Exception(
                Marshal.GetLastWin32Error(),
                "Could not contain the suspended installer process; it must not be resumed.");
    }

    public void Terminate(uint exitCode = 1)
    {
        EnsureOpen();
        if (!NativeMethods.TerminateJobObject(_handle, exitCode))
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not terminate the installer process tree.");
    }

    /// <summary>Returns the current number of active processes contained by this Job Object.</summary>
    public uint GetActiveProcessCount()
    {
        EnsureOpen();
        var accounting = new BasicAccountingInformation();
        if (!NativeMethods.QueryInformationJobObject(
                _handle, JobObjectBasicAccountingInformation,
                ref accounting, (uint)Marshal.SizeOf<BasicAccountingInformation>(), out _))
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not query installer process-tree accounting.");
        return accounting.ActiveProcesses;
    }

    public void WaitForEmpty(TimeSpan timeout)
    {
        EnsureOpen();
        if (timeout < TimeSpan.Zero || timeout > TimeSpan.FromMinutes(30))
            throw new ArgumentOutOfRangeException(nameof(timeout));

        var deadline = DateTime.UtcNow + timeout;
        do
        {
            var accounting = new BasicAccountingInformation();
            if (!NativeMethods.QueryInformationJobObject(
                    _handle, JobObjectBasicAccountingInformation,
                    ref accounting, (uint)Marshal.SizeOf<BasicAccountingInformation>(), out _))
                throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not verify installer process-tree termination.");

            if (accounting.ActiveProcesses == 0)
                return;
            Thread.Sleep(100);
        } while (DateTime.UtcNow < deadline);

        throw new TimeoutException("Installer Job Object still contains active processes.");
    }

    private void EnsureOpen()
    {
        if (_handle.IsClosed || _handle.IsInvalid)
            throw new ObjectDisposedException(nameof(WindowsJobObject));
    }

    private static void EnsureWindows()
    {
        if (!OperatingSystem.IsWindows())
            throw new PlatformNotSupportedException("Windows Job Objects are available only on Windows.");
    }

    public void Dispose() => _handle.Dispose();

    [StructLayout(LayoutKind.Sequential)]
    private struct BasicLimitInformation
    {
        public long PerProcessUserTimeLimit;
        public long PerJobUserTimeLimit;
        public uint LimitFlags;
        public UIntPtr MinimumWorkingSetSize;
        public UIntPtr MaximumWorkingSetSize;
        public uint ActiveProcessLimit;
        public UIntPtr Affinity;
        public uint PriorityClass;
        public uint SchedulingClass;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct IoCounters
    {
        public ulong ReadOperationCount;
        public ulong WriteOperationCount;
        public ulong OtherOperationCount;
        public ulong ReadTransferCount;
        public ulong WriteTransferCount;
        public ulong OtherTransferCount;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct ExtendedLimitInformation
    {
        public BasicLimitInformation BasicLimitInformation;
        public IoCounters IoInfo;
        public UIntPtr ProcessMemoryLimit;
        public UIntPtr JobMemoryLimit;
        public UIntPtr PeakProcessMemoryUsed;
        public UIntPtr PeakJobMemoryUsed;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct BasicAccountingInformation
    {
        public long TotalUserTime;
        public long TotalKernelTime;
        public long ThisPeriodTotalUserTime;
        public long ThisPeriodTotalKernelTime;
        public uint TotalPageFaultCount;
        public uint TotalProcesses;
        public uint ActiveProcesses;
        public uint TotalTerminatedProcesses;
    }

    private sealed class SafeJobHandle : SafeHandleZeroOrMinusOneIsInvalid
    {
        private SafeJobHandle() : base(true) { }
        protected override bool ReleaseHandle() => NativeMethods.CloseHandle(handle);
    }

    private static class NativeMethods
    {
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        internal static extern SafeJobHandle CreateJobObjectW(IntPtr attributes, string? name);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool SetInformationJobObject(
            SafeJobHandle job, uint informationClass,
            ref ExtendedLimitInformation information, uint informationLength);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool AssignProcessToJobObject(SafeJobHandle job, IntPtr process);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool TerminateJobObject(SafeJobHandle job, uint exitCode);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool QueryInformationJobObject(
            SafeJobHandle job, uint informationClass,
            ref BasicAccountingInformation information, uint informationLength, out uint returnLength);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool CloseHandle(IntPtr handle);
    }
}
