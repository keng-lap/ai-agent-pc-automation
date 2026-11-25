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

        using var server = new NamedPipeServerStream(
            pipeName, PipeDirection.InOut, 1, PipeTransmissionMode.Byte, PipeOptions.Asynchronous);
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
        Console.WriteLine("PASS: named-pipe peer PID is resolved to the actual process token; SID, logon LUID, session ID, and non-elevated policy are enforced.");
    }

    private static void ExpectUnauthorized(Action action)
    {
        try { action(); }
        catch (UnauthorizedAccessException) { return; }
        throw new InvalidOperationException("An unauthorized named-pipe peer was incorrectly accepted.");
    }
}
