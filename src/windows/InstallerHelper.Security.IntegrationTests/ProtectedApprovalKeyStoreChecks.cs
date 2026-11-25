using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Principal;
using InstallerHelper.Security;

internal static class ProtectedApprovalKeyStoreChecks
{
    internal static void Run()
    {
        var directory = Path.Combine(Path.GetTempPath(), "installer-helper-key-store-" + Guid.NewGuid().ToString("N"));
        ProtectedApprovalKeyStore.ProvisionDirectory(directory);
        try
        {
            var store = new ProtectedApprovalKeyStore(directory);
            var first = store.LoadOrCreate();
            if (first.Length != 32)
                throw new InvalidOperationException("Protected key store returned a key with an invalid length.");

            var second = new ProtectedApprovalKeyStore(directory).LoadOrCreate();
            if (!CryptographicOperations.FixedTimeEquals(first, second))
                throw new InvalidOperationException("Protected key store did not reload the same key.");
            Console.WriteLine("PASS: protected DPAPI key is atomically created and reloaded.");

            var keyPath = Path.Combine(directory, "approval-ticket-key.dpapi");
            var fileInfo = new FileInfo(keyPath);
            var fileSecurity = fileInfo.GetAccessControl(AccessControlSections.Access | AccessControlSections.Owner);
            fileSecurity.AddAccessRule(new FileSystemAccessRule(
                new SecurityIdentifier(WellKnownSidType.BuiltinUsersSid, null),
                FileSystemRights.Read,
                AccessControlType.Allow));
            fileInfo.SetAccessControl(fileSecurity);
            ExpectRejected(() => new ProtectedApprovalKeyStore(directory).LoadOrCreate());
            Console.WriteLine("PASS: key file ACL granting an untrusted principal read access is rejected.");

            // Re-provision the directory to restore the trusted DACL, then verify
            // that a broad directory ACE is rejected before any key operation.
            ProtectedApprovalKeyStore.ProvisionDirectory(directory);
            var directoryInfo = new DirectoryInfo(directory);
            var directorySecurity = directoryInfo.GetAccessControl(AccessControlSections.Access | AccessControlSections.Owner);
            directorySecurity.AddAccessRule(new FileSystemAccessRule(
                new SecurityIdentifier(WellKnownSidType.BuiltinUsersSid, null),
                FileSystemRights.ReadAndExecute,
                InheritanceFlags.ContainerInherit | InheritanceFlags.ObjectInherit,
                PropagationFlags.None,
                AccessControlType.Allow));
            directoryInfo.SetAccessControl(directorySecurity);
            ExpectRejected(() => new ProtectedApprovalKeyStore(directory));
            Console.WriteLine("PASS: directory ACL granting access to an untrusted principal is rejected.");

            CryptographicOperations.ZeroMemory(first);
            CryptographicOperations.ZeroMemory(second);
        }
        finally
        {
            try
            {
                ProtectedApprovalKeyStore.ProvisionDirectory(directory);
                Directory.Delete(directory, recursive: true);
            }
            catch
            {
                // Preserve test failure; CI workspace cleanup handles a locked test directory.
            }
        }

        var linkTarget = Path.Combine(Path.GetTempPath(), "installer-helper-key-target-" + Guid.NewGuid().ToString("N"));
        var linkPath = Path.Combine(Path.GetTempPath(), "installer-helper-key-link-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(linkTarget);
        try
        {
            Directory.CreateSymbolicLink(linkPath, linkTarget);
            ExpectRejected(() => new ProtectedApprovalKeyStore(linkPath));
            Console.WriteLine("PASS: reparse-point key directory is rejected.");
        }
        finally
        {
            try { Directory.Delete(linkPath); } catch { }
            Directory.Delete(linkTarget, recursive: true);
        }
    }

    private static void ExpectRejected(Action action)
    {
        try
        {
            action();
        }
        catch (Exception exception) when (
            exception is UnauthorizedAccessException ||
            exception is CryptographicException ||
            exception is IOException)
        {
            return;
        }

        throw new InvalidOperationException("An unsafe protected-key storage configuration was accepted.");
    }
}
