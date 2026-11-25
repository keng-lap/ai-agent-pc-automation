using System.ComponentModel;
using System.IO.Pipes;
using System.Runtime.InteropServices;
using System.Security;
using Microsoft.Win32.SafeHandles;

namespace InstallerHelper.Security;

/// <summary>
/// Creates a single-instance local-only server pipe using the exact protected
/// DACL returned by WindowsNamedPipePeerVerifier. The native creation flags
/// include PIPE_REJECT_REMOTE_CLIENTS; do not replace this with the managed
/// NamedPipeServerStream(name, ...) constructor.
/// </summary>
public static class WindowsSecureNamedPipeServer
{
    private const uint PipeAccessDuplex = 0x00000003;
    private const uint FileFlagOverlapped = 0x40000000;
    private const uint FileFlagFirstPipeInstance = 0x00080000;
    private const uint PipeRejectRemoteClients = 0x00000008;
    private const uint PipeUnlimitedInstances = 255;
    private const uint BufferSize = 64 * 1024;
    private const uint SddlRevision1 = 1;

    public static NamedPipeServerStream Create(string ticketId, string requesterSid)
    {
        if (!OperatingSystem.IsWindows())
            throw new PlatformNotSupportedException("Secure named pipes are Windows-only.");

        var pipeName = WindowsNamedPipePeerVerifier.CreatePipeName(ticketId);
        var sddl = WindowsNamedPipePeerVerifier.BuildServerPipeSddl(requesterSid);
        if (!Native.ConvertStringSecurityDescriptorToSecurityDescriptor(
                sddl, SddlRevision1, out var descriptor, out _))
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not convert the named-pipe security descriptor.");

        try
        {
            var attributes = new SecurityAttributes
            {
                Length = Marshal.SizeOf<SecurityAttributes>(),
                SecurityDescriptor = descriptor,
                InheritHandle = false
            };

            var handle = Native.CreateNamedPipe(
                @"\\.\pipe\\" + pipeName,
                PipeAccessDuplex | FileFlagOverlapped | FileFlagFirstPipeInstance,
                PipeRejectRemoteClients,
                1,
                BufferSize,
                BufferSize,
                0,
                ref attributes);

            if (handle.IsInvalid)
            {
                var error = Marshal.GetLastWin32Error();
                handle.Dispose();
                throw new Win32Exception(error, "Could not create the protected local installer-helper pipe.");
            }

            try
            {
                return new NamedPipeServerStream(PipeDirection.InOut, isAsync: true, isConnected: false, handle);
            }
            catch
            {
                handle.Dispose();
                throw;
            }
        }
        finally
        {
            _ = Native.LocalFree(descriptor);
        }
    }

    public static async Task<WindowsTokenIdentityInfo> WaitForApprovedClientAsync(
        NamedPipeServerStream server,
        WindowsTokenIdentityInfo expectedRequester,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(server);
        ArgumentNullException.ThrowIfNull(expectedRequester);
        await server.WaitForConnectionAsync(cancellationToken).ConfigureAwait(false);

        // A failed or incomplete token query is a hard denial; the connected
        // stream must be disposed by the caller and must never process a frame.
        return WindowsNamedPipePeerVerifier.RequireClientIdentity(
            server.SafePipeHandle,
            expectedRequester.UserSid,
            expectedRequester.AuthenticationId,
            expectedRequester.SessionId,
            requireNonElevatedClient: true);
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct SecurityAttributes
    {
        public int Length;
        public IntPtr SecurityDescriptor;
        [MarshalAs(UnmanagedType.Bool)]
        public bool InheritHandle;
    }

    private static class Native
    {
        [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true,
            EntryPoint = "ConvertStringSecurityDescriptorToSecurityDescriptorW")]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool ConvertStringSecurityDescriptorToSecurityDescriptor(
            string stringSecurityDescriptor, uint stringSDRevision,
            out IntPtr securityDescriptor, out uint securityDescriptorSize);

        [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true,
            EntryPoint = "CreateNamedPipeW")]
        internal static extern SafePipeHandle CreateNamedPipe(
            string name, uint openMode, uint pipeMode, uint maxInstances,
            uint outBufferSize, uint inBufferSize, uint defaultTimeout,
            ref SecurityAttributes securityAttributes);

        [DllImport("kernel32.dll")]
        internal static extern IntPtr LocalFree(IntPtr memory);
    }
}

/// <summary>
/// Length-prefixed, bounded byte framing for the future Helper protocol.
/// The four-byte network-order length is validated before allocating payload memory.
/// </summary>
public static class InstallerHelperPipeProtocol
{
    public const int MaximumFrameBytes = 64 * 1024;

    public static async Task<byte[]> ReadFrameAsync(Stream stream, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(stream);
        var header = new byte[sizeof(int)];
        await ReadExactlyAsync(stream, header, cancellationToken).ConfigureAwait(false);
        var length = System.Buffers.Binary.BinaryPrimitives.ReadInt32BigEndian(header);
        if (length <= 0 || length > MaximumFrameBytes)
            throw new InvalidDataException("Installer-helper IPC frame length is outside the permitted range.");

        var payload = new byte[length];
        await ReadExactlyAsync(stream, payload, cancellationToken).ConfigureAwait(false);
        return payload;
    }

    public static async Task WriteFrameAsync(Stream stream, ReadOnlyMemory<byte> payload, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(stream);
        if (payload.Length <= 0 || payload.Length > MaximumFrameBytes)
            throw new InvalidDataException("Installer-helper IPC frame length is outside the permitted range.");

        var header = new byte[sizeof(int)];
        System.Buffers.Binary.BinaryPrimitives.WriteInt32BigEndian(header, payload.Length);
        await stream.WriteAsync(header, cancellationToken).ConfigureAwait(false);
        await stream.WriteAsync(payload, cancellationToken).ConfigureAwait(false);
        await stream.FlushAsync(cancellationToken).ConfigureAwait(false);
    }

    private static async Task ReadExactlyAsync(Stream stream, Memory<byte> buffer, CancellationToken cancellationToken)
    {
        var offset = 0;
        while (offset < buffer.Length)
        {
            var read = await stream.ReadAsync(buffer[offset..], cancellationToken).ConfigureAwait(false);
            if (read == 0)
                throw new EndOfStreamException("Installer-helper IPC disconnected during a frame.");
            offset += read;
        }
    }
}
