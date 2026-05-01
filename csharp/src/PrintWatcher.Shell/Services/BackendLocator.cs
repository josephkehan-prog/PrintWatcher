using System;
using System.IO;

namespace PrintWatcher.Shell.Services;

/// <summary>Resolves the path to <c>PrintWatcher-backend.exe</c>.</summary>
public static class BackendLocator
{
    public const string ExecutableName = "PrintWatcher-backend.exe";
    public const string DevEnvVar = "PRINTWATCHER_DEV_BACKEND";

    /// <summary>Find the backend executable next to the running shell, or fall back to %PATH%.</summary>
    public static string FindBackend()
    {
        var here = AppContext.BaseDirectory;
        var sibling = Path.Combine(here, ExecutableName);
        if (File.Exists(sibling)) return sibling;

        // Dev-tree layout: csharp/src/PrintWatcher.Shell/bin/.../net8.0-windows... up to repo root.
        var probe = new DirectoryInfo(here);
        for (var depth = 0; depth < 10 && probe is not null; depth++, probe = probe.Parent)
        {
            var devCandidate = Path.Combine(probe.FullName, "dist", ExecutableName);
            if (File.Exists(devCandidate)) return devCandidate;
        }

        return ExecutableName;  // last resort: hope it's on PATH
    }

    public static string ServerJsonPath()
    {
        var local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        return Path.Combine(local, "PrintWatcher", "server.json");
    }
}
