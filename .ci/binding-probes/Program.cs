using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using Microsoft.Win32;
using ReactiveUI;
using ServiceLib;
using ServiceLib.Common;
using ServiceLib.Enums;
using ServiceLib.Handler;
using ServiceLib.Helper;
using ServiceLib.Manager;
using ServiceLib.Models.Entities;
using ServiceLib.Models.Editors;
using ServiceLib.Models.Configs;
using ServiceLib.ViewModels;
#if WPF
using System.Windows;
using System.Windows.Controls;
using System.Windows.Markup;
using System.Windows.Threading;
using ReactiveUI.Builder;
using ReactiveUI.Wpf;
using Views = v2rayN.Views;
#else
using Avalonia;
using Avalonia.Controls;
using Avalonia.Headless;
using Avalonia.Threading;
using ReactiveUI.Avalonia;
using v2rayN.Desktop.Common;
using Views = v2rayN.Desktop.Views;
#endif

internal static class Program
{
    private static int _assertions;
    private static bool _negative;
    private static string _output = "";
    private static readonly FieldInfo StartupSentinel = typeof(AppManager).GetField("_statePort", BindingFlags.Instance | BindingFlags.NonPublic)!;

    [STAThread]
    private static int Main(string[] args)
    {
        _output = args[0];
        _negative = args.Contains("--negative");
        Directory.CreateDirectory(_output);
        using var log = new StreamWriter(Path.Combine(_output, "probe.log")) { AutoFlush = true };
        Console.SetOut(log);
        Console.SetError(log);
        var before = OperatingSystem.IsWindows() ? RegistrySnapshot() : null;
        if (before is not null)
            File.WriteAllText(Path.Combine(_output, "registry-before.json"), before);
        var exit = 1;
        try
        {
#if WPF
            var desktop = DesktopName(GetThreadDesktop(GetCurrentThreadId()));
            Assert(desktop.StartsWith("CodexBindingProbe-", StringComparison.Ordinal), "isolated desktop before first WPF window: " + desktop);
            var input = OpenInputDesktop(0, false, 1);
            try { Assert(DesktopName(input) != desktop, "probe desktop is not input desktop"); }
            finally { CloseDesktop(input); }
#endif
            Environment.SetEnvironmentVariable(Global.LocalAppData, null);
            var startupPath = Utils.StartupPath();
            Assert(startupPath.Contains("binding-probes", StringComparison.OrdinalIgnoreCase)
                || startupPath.Contains("ui-ci-binding-probe", StringComparison.OrdinalIgnoreCase), "task-local config root: " + startupPath);
            Assert(StartupSentinel.GetValue(AppManager.Instance) == null, "startup sentinel initially null");
            var config = ConfigHandler.LoadConfig() ?? throw new InvalidOperationException("Config defaults failed");
            config.SystemProxyItem.SysProxyType = (ESysProxyType)2;
            config.UiItem.CurrentTheme = "Light";
            config.WebDavItem = new WebDavItem { UserName = "initial", Url = "https://invalid.example/", DirName = "probe" };
            typeof(AppManager).GetField("_config", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(AppManager.Instance, config);
#if WPF
            var app = new Application { ShutdownMode = ShutdownMode.OnExplicitShutdown };
            _ = typeof(MaterialDesignThemes.Wpf.BundledTheme).Assembly;
            _ = typeof(MaterialDesignColors.SwatchesProvider).Assembly;
            app.Resources = LoadResources(args[1]);
            RxAppBuilder.CreateReactiveUIBuilder().WithWpf().BuildApp();
            SynchronizationContext.SetSynchronizationContext(new DispatcherSynchronizationContext(app.Dispatcher));
            app.DispatcherUnhandledException += (_, e) => throw new InvalidOperationException("Unexpected dispatcher exception", e.Exception);
#else
            AppBuilder.Configure<v2rayN.Desktop.App>().UseSkia()
                .UseHeadless(new AvaloniaHeadlessPlatformOptions { UseHeadlessDrawing = false })
                .WithFontByDefault().UseReactiveUI(_ => { }).SetupWithoutStarting();
            Assert(Application.Current!.ApplicationLifetime == null, "headless application has no desktop lifetime");
            Assert(Application.Current.DataContext == null, "headless startup did not create StatusBarViewModel");
#endif
            Assert(StartupSentinel.GetValue(AppManager.Instance) == null, "startup sentinel after framework setup");
            SQLiteHelper.Instance.CreateTable<ProfileItem>();
            SQLiteHelper.Instance.CreateTable<SubItem>();
            Probe(new Views.AddServerWindow(), new AddServerViewModel(new ProfileItem
            { IndexId = "probe", ConfigType = EConfigType.SOCKS, Remarks = "initial", Address = "127.0.0.1", Port = 1080, Username = "nullable" }),
                "SelectedSource", "Remarks", "txtRemarks", "Username", "txtSecurity4");
            Probe(new Views.AddServerWindow(), new AddServerViewModel(new ProfileItem
            { IndexId = "probe-reality", ConfigType = EConfigType.VLESS, Remarks = "initial", Address = "127.0.0.1", Port = 443, Password = "nullable", StreamSecurity = Global.StreamSecurityReality }),
                "SelectedSource", "Remarks", "txtRemarks", "Password", "txtId5");
            Probe(new Views.AddServer2Window(), new AddServer2ViewModel(new ProfileItem
            { IndexId = "probe-custom", ConfigType = EConfigType.Custom, Remarks = "initial", Address = "probe.json", PreSocksPort = 1081 }),
                "SelectedSource", "Remarks", "txtRemarks", "PreSocksPort", "txtPreSocksPort");
            var groupVm = new AddGroupServerViewModel(new ProfileItem { ConfigType = EConfigType.PolicyGroup, Remarks = "initial" });
            var groupDeadline = DateTime.UtcNow.AddSeconds(5);
            while (groupVm.SubItems.Count == 0 && DateTime.UtcNow < groupDeadline) { Pump(); Thread.Sleep(5); }
            Assert(groupVm.SubItems.Count > 0, "group constructor initialization completed");
            Probe(new Views.AddGroupServerWindow(), groupVm, "SelectedSource", "Remarks", "txtRemarks", "Remarks", "txtRemarks");
            Probe(new Views.SubEditWindow(), new SubEditViewModel(new SubItem
            { Id = "probe-sub", Remarks = "initial", Url = "https://invalid.example/", Memo = "nullable" }),
                "SelectedSource", "Remarks", "txtRemarks", "Memo", "txtMemo");
            Probe(new Views.RoutingRuleSettingWindow(), new RoutingRuleSettingViewModel(new RoutingItem
            { Remarks = "initial", Url = "nullable", RuleSet = "[]" }),
                "SelectedRouting", "Remarks", "txtRemarks", "Url", "txtUrl");
            Probe(new Views.BackupAndRestoreView(), new BackupAndRestoreViewModel(),
                "SelectedSource", "UserName", "txtWebDavUserName", "DirName", "txtWebDavDirName");
            Assert(config.WebDavItem.UserName == "initial", "unsaved WebDav edits do not change Config");
            WaitTask(SQLiteHelper.Instance.DisposeDbConnectionAsync());
            exit = 0;
        }
        catch (BindingAssertionException ex)
        {
            Console.WriteLine("BINDING_ASSERTION_FAILURE " + ex.Message);
            exit = _negative && ex.Message == "AddServerWindow model-to-control" ? 42 : 1;
        }
        catch (Exception ex) { Console.WriteLine("UNEXPECTED_EXCEPTION " + ex); exit = 1; }
        finally
        {
            try
            {
                Assert(StartupSentinel.GetValue(AppManager.Instance) == null, "startup sentinel remains untouched");
                if (OperatingSystem.IsWindows())
                {
                    var after = RegistrySnapshot();
                    File.WriteAllText(Path.Combine(_output, "registry-after.json"), after);
                    Assert(before == after, "HKCU proxy and Run unchanged");
                }
                else
                {
                    Console.WriteLine("NOT_APPLICABLE Windows HKCU state: non-Windows headless host");
                }
            }
            catch (Exception ex) { Console.WriteLine(ex); exit = 1; }
#if WPF
            Dispatcher.CurrentDispatcher.InvokeShutdown();
#endif
            Console.WriteLine($"RESULT exit={exit} assertions={_assertions} negative={_negative}");
        }
        return exit;
    }

    private static void Probe(object view, object vm, string sourceName, string propertyName, string controlName, string nullableName, string nullableControlName)
    {
        var name = view.GetType().Name;
        view.GetType().GetProperty("ViewModel")!.SetValue(view, vm);
        var sourceProperty = vm.GetType().GetProperty(sourceName)!;
        var model = sourceProperty.GetValue(vm)!;
        var property = model.GetType().GetProperty(propertyName)!;
        var nullable = model.GetType().GetProperty(nullableName)!;
#if WPF
        var element = (FrameworkElement)view;
        var host = view as Window ?? new Window { Content = view, Width = 1000, Height = 700 };
        var text = (TextBox)element.FindName(controlName);
        var nullableText = (TextBox)element.FindName(nullableControlName);
#else
        var element = (Control)view;
        var host = view as Window ?? new Window { Content = view, Width = 1000, Height = 700 };
        var text = element.FindControl<TextBox>(controlName)!;
        var nullableText = element.FindControl<TextBox>(nullableControlName)!;
#endif
        host.Show();
        Pump();
        Assert(text.Text == "initial", name + " initial entity-to-control");
        text.Text = "control-edit";
        Pump();
        Assert((string?)property.GetValue(model) == "control-edit", name + " control-to-model");
        if (_negative)
        {
            using (((ReactiveObject)model).SuppressChangeNotifications()) { property.SetValue(model, "model-edit"); }
        }
        else { property.SetValue(model, "model-edit"); }
        Pump();
        Assert(text.Text == "model-edit", name + " model-to-control");
        nullable.SetValue(model, null);
        Pump();
        Assert(string.IsNullOrEmpty(nullableText.Text), name + " nullable clearing model-to-control");
        nullableText.Text = Nullable.GetUnderlyingType(nullable.PropertyType) == typeof(int) ? "1082" : "clear-me";
        Pump();
        Assert(nullable.GetValue(model) != null, name + " nullable control edit");
        nullableText.Text = "";
        Pump();
        Assert(nullable.GetValue(model) is null || Equals(nullable.GetValue(model), ""), name + " empty control clearing");
        var entity = model.GetType().GetMethod("ToEntity")!.Invoke(model, null)!;
        var replacement = model.GetType().GetMethod("FromEntity")!.Invoke(null, [entity])!;
        property.SetValue(replacement, "replacement");
        string? oldSecurity = null;
        if (vm is AddServerViewModel)
        {
            oldSecurity = ((ProfileEditorModel)model).StreamSecurity;
            ((ProfileEditorModel)replacement).StreamSecurity = Global.StreamSecurity;
        }
        sourceProperty.SetValue(vm, replacement);
        Pump();
        Assert(text.Text == "replacement", name + " selected editor replacement");
        if (vm is AddServerViewModel)
        {
#if WPF
            var securityControl = (ComboBox)element.FindName("cmbStreamSecurity");
#else
            var securityControl = element.FindControl<ComboBox>("cmbStreamSecurity")!;
#endif
            Assert(((ProfileEditorModel)replacement).StreamSecurity == Global.StreamSecurity, name + " replacement preserves new TLS");
            Assert(((ProfileEditorModel)model).StreamSecurity == oldSecurity, name + " replacement preserves old TLS/Reality");
            Assert((string?)securityControl.SelectedItem == Global.StreamSecurity, name + " replacement displays new TLS");
        }
        property.SetValue(model, "old-model-change");
        Pump();
        Assert(text.Text == "replacement", name + " old model detached");
        text.Text = "replacement-control-edit";
        Pump();
        Assert((string?)property.GetValue(replacement) == "replacement-control-edit", name + " replacement two-way");
        Assert((string?)property.GetValue(model) == "old-model-change", name + " old model receives no control edits");
        if (vm is AddServer2ViewModel customVm)
        {
            var beforeBrowse = customVm.SelectedSource;
            var importFile = Path.Combine(_output, "custom-import.json");
            File.WriteAllText(importFile, "{}");
            WaitTask(customVm.BrowseServer(importFile));
            Pump();
            Assert(!ReferenceEquals(beforeBrowse, customVm.SelectedSource), "AddServer2 Browse replaces editor");
            Assert(customVm.IsModified, "AddServer2 Browse completes import");
#if WPF
            var address = (TextBox)element.FindName("txtAddress");
#else
            var address = element.FindControl<TextBox>("txtAddress")!;
#endif
            Assert(address.Text == customVm.SelectedSource.Address && File.Exists(Utils.GetConfigPath(address.Text)), "AddServer2 Browse binding follows imported file");
            beforeBrowse.Remarks = "obsolete-before-browse";
            Pump();
            Assert(text.Text != "obsolete-before-browse", "AddServer2 Browse detaches old editor");
            text.Text = "after-browse-control";
            Pump();
            Assert(customVm.SelectedSource.Remarks == "after-browse-control", "AddServer2 Browse control-to-new-editor");
            customVm.SelectedSource.Remarks = "after-browse-model";
            Pump();
            Assert(text.Text == "after-browse-model", "AddServer2 Browse new-editor-to-control");
            replacement = customVm.SelectedSource;
        }
        host.Close();
        Pump();
        var closedText = text.Text;
        property.SetValue(replacement, "after-close-model");
        Pump();
        Assert(text.Text == closedText, name + " close disposes model-to-control");
        text.Text = "after-close-control";
        Pump();
        Assert((string?)property.GetValue(replacement) == "after-close-model", name + " close disposes control-to-model");
        Console.WriteLine("CASE_PASS " + name);
    }

    private static void Pump()
    {
#if WPF
        for (var i = 0; i < 3; i++)
        {
            var frame = new DispatcherFrame();
            Dispatcher.CurrentDispatcher.BeginInvoke(DispatcherPriority.ApplicationIdle, new Action(() => frame.Continue = false));
            Dispatcher.PushFrame(frame);
        }
#else
        Dispatcher.UIThread.RunJobs();
        AvaloniaHeadlessPlatform.ForceRenderTimerTick();
        Dispatcher.UIThread.RunJobs();
#endif
    }

    private static void WaitTask(Task task)
    {
        var deadline = DateTime.UtcNow.AddSeconds(10);
        while (!task.IsCompleted && DateTime.UtcNow < deadline) { Pump(); Thread.Sleep(5); }
        if (!task.IsCompleted) throw new TimeoutException("Task did not complete within ten seconds");
        task.GetAwaiter().GetResult();
    }

    private static void Assert(bool condition, string label)
    {
        if (!condition) throw new BindingAssertionException(label);
        _assertions++;
        Console.WriteLine("PASS " + label);
    }

    private static string RegistrySnapshot()
    {
        if (!OperatingSystem.IsWindows()) throw new PlatformNotSupportedException("This probe measures Windows HKCU state");
        var result = new SortedDictionary<string, object?>();
        foreach (var path in new[] { @"Software\Microsoft\Windows\CurrentVersion\Internet Settings", @"Software\Microsoft\Windows\CurrentVersion\Run" })
        {
            using var key = Registry.CurrentUser.OpenSubKey(path, false);
            foreach (var name in (path.EndsWith("Run") ? key?.GetValueNames() ?? [] : new[] { "ProxyEnable", "ProxyServer", "ProxyOverride", "AutoConfigURL" }).Order())
                result[path + "/" + name] = key?.GetValue(name, null, RegistryValueOptions.DoNotExpandEnvironmentNames);
        }
        return JsonSerializer.Serialize(result);
    }

#if WPF
    private static ResourceDictionary LoadResources(string root)
    {
        var xaml = File.ReadAllText(Path.Combine(root, "v2rayN", "v2rayN", "App.xaml"));
        var start = xaml.IndexOf("<Application.Resources>", StringComparison.Ordinal) + "<Application.Resources>".Length;
        var end = xaml.IndexOf("</Application.Resources>", StringComparison.Ordinal);
        var inner = xaml[start..end].Trim();
        const string ns = "<ResourceDictionary xmlns=\"http://schemas.microsoft.com/winfx/2006/xaml/presentation\" " +
            "xmlns:x=\"http://schemas.microsoft.com/winfx/2006/xaml\" " +
            "xmlns:conv=\"clr-namespace:v2rayN.Converters;assembly=v2rayN\" " +
            "xmlns:materialDesign=\"http://materialdesigninxaml.net/winfx/xaml/themes\" ";
        inner = new System.Text.RegularExpressions.Regex("^<ResourceDictionary ").Replace(inner, ns, 1);
        return (ResourceDictionary)XamlReader.Parse(inner);
    }
    private static string DesktopName(IntPtr handle)
    {
        var value = new StringBuilder(256);
        if (handle == IntPtr.Zero || !GetUserObjectInformation(handle, 2, value, value.Capacity * 2, out _))
            throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
        return value.ToString();
    }
    [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Unicode)] private static extern bool GetUserObjectInformation(IntPtr handle, int index, StringBuilder value, int size, out int needed);
    [DllImport("user32.dll")] private static extern IntPtr GetThreadDesktop(uint thread);
    [DllImport("kernel32.dll")] private static extern uint GetCurrentThreadId();
    [DllImport("user32.dll", SetLastError = true)] private static extern IntPtr OpenInputDesktop(uint flags, bool inherit, uint access);
    [DllImport("user32.dll")] private static extern bool CloseDesktop(IntPtr desktop);
#endif
    private sealed class BindingAssertionException(string message) : Exception(message);
}
