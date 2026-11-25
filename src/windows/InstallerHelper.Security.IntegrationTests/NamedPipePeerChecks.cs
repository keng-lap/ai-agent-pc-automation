using System.IO.Pipes;
using InstallerHelper.Security;

internal static class NamedPipePeerChecks
{
    internal static void Run()
    {
        var identity = WindowsTokenIdentity.GetCurrentProcessIdentity();
        var ticketId = Guid.NewGuid().ToString("N");
        var pipeName = WindowsNamedPipePeerVerifier.CreatePipeName(ticketId);
        var sddl = WindowsNamedPipePeerVerifier.BuildServerPipeSddl(identity.UserSid);
        if (!sddl.StartsWith("D:P", StringComparison.Ordinal)
            || !sddl.Contains(identity.UserSid, StringComparison.Ordinal))
            throw new InvalidOperationException("Named-pipe DACL does not contain a protected requester-specific ACE.");

        // This test uses the native CreateNamedPipeW factory. It therefore
        // exercises the actual SDDL and PIPE_REJECT_REMOTE_CLIENTS creation flags.
        using var server = WindowsSecureNamedPipeServer.Create(ticketId, identity.UserSid);
        var connection = server.WaitForConnectionAsync();
        using var client = new NamedPipeClientStream(".", pipeName, PipeDirection.InOut, PipeOptions.Asynchronous);
        client.Connect(5_000);
        connection.GetAwaiter().GetResult();

        var peer = WindowsNamedPipePeerVerifier.RequireClientIdentity(
            server.SafePipeHandle, identity.UserSid, identity.AuthenticationId, identity.SessionId,
            requireNonElevatedClient: false);
        if (peer.UserSid != identity.UserSid || peer.AuthenticationId != identity.AuthenticationId
            || peer.SessionId != identity.SessionId)
            throw new InvalidOperationException("Named-pipe peer identity did not match the actual client token.");

        ExpectUnauthorized(() => WindowsNamedPipePeerVerifier.RequireClientIdentity(
            server.SafePipeHandle, "S-1-5-21-0-0-0-9999", identity.AuthenticationId, identity.SessionId,
            requireNonElevatedClient: false));
        ExpectUnauthorized(() => WindowsNamedPipePeerVerifier.RequireClientIdentity(
            server.SafePipeHandle, identity.UserSid, new string('0', 16), identity.SessionId,
            requireNonElevatedClient: false));
        ExpectUnauthorized(() => WindowsNamedPipePeerVerifier.RequireClientIdentity(
            server.SafePipeHandle, identity.UserSid, identity.AuthenticationId, identity.SessionId + 1,
            requireNonElevatedClient: false));

        if (identity.IsElevated)
        {
            ExpectUnauthorized(() => WindowsNamedPipePeerVerifier.RequireClientIdentity(
                server.SafePipeHandle, identity.UserSid, identity.AuthenticationId, identity.SessionId));
        }

        RunFrameChecks();
        Console.WriteLine("PASS: native named-pipe creation applies requester DACL and rejects remote clients; connected peer PID resolves to the actual process token.");
        Console.WriteLine("PASS: bounded length-prefixed IPC framing handles valid, oversized, empty, and truncated frames.");
    }

    private static void RunFrameChecks()
    {
        var payload = System.Text.Encoding.UTF8.GetBytes("{\"protocol\":1,\"type\":\"hello\"}");
        using (var stream = new MemoryStream())
        {
            InstallerHelperPipeProtocol.WriteFrameAsync(stream, payload, CancellationToken.None).GetAwaiter().GetResult();
            stream.Position = 0;
            var recovered = InstallerHelperPipeProtocol.ReadFrameAsync(stream, CancellationToken.None).GetAwaiter().GetResult();
            if (!payload.AsSpan().SequenceEqual(recovered))
                throw new InvalidOperationException("IPC frame round-trip changed the payload.");
        }

        ExpectInvalidFrame(new byte[] { 0, 1, 0, 1 }); // declared 65,537 bytes
        ExpectInvalidFrame(new byte[] { 0, 0, 0, 0 }); // empty frame
        ExpectTruncatedFrame(new byte[] { 0, 0, 0, 3, 0x41 }); // short body
        ExpectWriteFailure(new byte[InstallerHelperPipeProtocol.MaximumFrameBytes + 1]);
    }

    private static void ExpectInvalidFrame(byte[] bytes)
    {
        try
        {
            using var stream = new MemoryStream(bytes);
            _ = InstallerHelperPipeProtocol.ReadFrameAsync(stream, CancellationToken.None).GetAwaiter().GetResult();
        }
        catch (InvalidDataException) { return; }
        throw new InvalidOperationException("An invalid IPC frame length was accepted.");
    }

    private static void ExpectTruncatedFrame(byte[] bytes)
    {
        try
        {
            using var stream = new MemoryStream(bytes);
            _ = InstallerHelperPipeProtocol.ReadFrameAsync(stream, CancellationToken.None).GetAwaiter().GetResult();
        }
        catch (EndOfStreamException) { return; }
        throw new InvalidOperationException("A truncated IPC frame was accepted.");
    }

    private static void ExpectWriteFailure(byte[] bytes)
    {
        try
        {
            using var stream = new MemoryStream();
            InstallerHelperPipeProtocol.WriteFrameAsync(stream, bytes, CancellationToken.None).GetAwaiter().GetResult();
        }
        catch (InvalidDataException) { return; }
        throw new InvalidOperationException("An oversized IPC frame was written.");
    }

    private static void ExpectUnauthorized(Action action)
    {
        try { action(); }
        catch (UnauthorizedAccessException) { return; }
        throw new InvalidOperationException("An unauthorized named-pipe peer was incorrectly accepted.");
    }
}
