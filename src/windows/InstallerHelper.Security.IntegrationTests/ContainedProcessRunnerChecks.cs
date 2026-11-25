using InstallerHelper.Security;

internal static class ContainedProcessRunnerChecks
{
    public static void Run()
    {
        var system = Environment.GetFolderPath(Environment.SpecialFolder.System);
        var command = Path.Combine(system, "cmd.exe");
        if (!File.Exists(command))
            throw new FileNotFoundException("Windows command interpreter is unavailable.", command);

        using (var job = new WindowsJobObject())
        {
            var exitCode = job.RunSuspendedCommandLine(
                Quote(command) + " /d /c exit 0",
                system,
                TimeSpan.FromSeconds(10));
            if (exitCode != 0 || job.GetActiveProcessCount() != 0)
                throw new InvalidOperationException("Contained process did not exit cleanly or left active descendants.");
        }
        Console.WriteLine("PASS: suspended process was assigned to Job Object before resume and exited cleanly.");

        using (var cancellation = new CancellationTokenSource())
        using (var job = new WindowsJobObject())
        {
            var run = Task.Run(() => job.RunSuspendedCommandLine(
                Quote(command) + " /d /c ping -n 30 127.0.0.1 > nul",
                system,
                TimeSpan.FromSeconds(20),
                cancellation.Token));
            Thread.Sleep(300);
            cancellation.Cancel();
            try
            {
                _ = run.GetAwaiter().GetResult();
                throw new InvalidOperationException("Contained process runner ignored cancellation.");
            }
            catch (OperationCanceledException)
            {
                // Expected: the entire Job is terminated before the exception escapes.
            }

            if (job.GetActiveProcessCount() != 0)
                throw new InvalidOperationException("Cancellation left an active process in the Job Object.");
        }
        Console.WriteLine("PASS: cancellation terminates the contained process tree.");
    }

    private static string Quote(string value) => "\"" + value.Replace("\"", "\\\"") + "\"";
}
