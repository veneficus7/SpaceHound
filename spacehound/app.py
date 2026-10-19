"""Entry point: desktop window (pywebview / WebView2), browser mode or CLI."""

import argparse
import os
import sys
import time

from . import APP_NAME, AUTHOR, __version__
from .util import data_dir, fmt_size, resource_path


def _cli_report(paths, top):
    from . import analysis, insights
    from .jobs import Job
    from .scanner import scan

    job = Job(0, "scan")
    t0 = time.time()
    print(f"{APP_NAME} {__version__} by {AUTHOR} - scanning {', '.join(paths)} …", flush=True)
    tree = scan(job, paths, threads=max(4, min(16, os.cpu_count() or 8)))
    root = tree.root
    print(f"\n{fmt_size(root.size)} in {root.nfiles:,} files / {root.ndirs:,} folders "
          f"({time.time() - t0:.1f}s, {tree.denied_count:,} unreadable folders)\n")
    print("Biggest folders")
    for d in analysis.deep_biggest(tree, top):
        print(f"  {fmt_size(d['size']):>10}  {d['path']}")
    print("\nLargest files")
    for f in analysis.largest_files(tree, {"limit": top})["items"]:
        print(f"  {fmt_size(f['size']):>10}  {f['path']}")
    print("\nBy type")
    for c in analysis.type_stats(tree)["categories"]:
        print(f"  {fmt_size(c['size']):>10}  {c['label']} ({c['count']:,} files)")
    found = insights.build(tree)
    if found:
        print("\nInsights")
        for i in found:
            print(f"  • {i['title']}\n    {i['text']}")


def _run_browser(api, port, open_browser=True):
    import webbrowser
    from .server import serve

    server, url = serve(api, port)
    print(f"{APP_NAME} is running at {url}\nPress Ctrl+C to quit.", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.shutdown()


def _install_cli(args):
    from . import installer

    try:
        if args.uninstall:
            if not args.quiet and not installer.message_box(
                    "Uninstall SpaceHound?\n\nYour scan history and settings are kept.", yes_no=True):
                return 1
            installer.uninstall()
            if not args.quiet:
                installer.message_box("SpaceHound was uninstalled.")
            return 0
        installer.install(desktop=args.desktop)
        print(f"Installed to {installer.INSTALLED_EXE}")
        if not args.quiet:
            installer.message_box("SpaceHound is installed.\n\nFind it any time by typing \"SpaceHound\" in the Start menu.")
        return 0
    except Exception as exc:
        if args.quiet:
            print(f"Failed: {exc}", file=sys.stderr)
        else:
            installer.message_box(f"Something went wrong:\n\n{exc}")
        return 1


def _redirect_output_if_windowed():
    """A windowed .exe has no console: send stdout/stderr to a log file instead of nowhere."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        log = open(os.path.join(data_dir(), "spacehound.log"), "a", encoding="utf-8", buffering=1)
        log.write(f"\n--- {APP_NAME} {__version__} started {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        sys.stdout = sys.stdout or log
        sys.stderr = sys.stderr or log
    except OSError:
        devnull = open(os.devnull, "w")
        sys.stdout = sys.stdout or devnull
        sys.stderr = sys.stderr or devnull


def main(argv=None):
    _redirect_output_if_windowed()
    parser = argparse.ArgumentParser(prog="spacehound", description="See what is eating your disk space.")
    parser.add_argument("--browser", action="store_true", help="open the UI in your web browser instead of a window")
    parser.add_argument("--port", type=int, default=0, help="port for --browser mode (default: random)")
    parser.add_argument("--no-open", action="store_true", help="with --browser: don't open a browser tab")
    parser.add_argument("--scan", nargs="+", metavar="PATH", help="scan from the command line and print a report")
    parser.add_argument("--top", type=int, default=15, help="rows per section in the CLI report")
    parser.add_argument("--debug", action="store_true", help="enable WebView developer tools")
    parser.add_argument("--install", action="store_true", help="install for this user (Start menu + Apps & features)")
    parser.add_argument("--desktop", action="store_true", help="with --install: also add a desktop shortcut")
    parser.add_argument("--uninstall", action="store_true", help="remove the installed copy and its shortcuts")
    parser.add_argument("--quiet", action="store_true", help="no dialogs for --install / --uninstall")
    parser.add_argument("path", nargs="?", help="folder or drive to scan right away")
    args = parser.parse_args(argv)

    if args.install or args.uninstall:
        return _install_cli(args)

    if args.scan:
        _cli_report(args.scan, args.top)
        return 0

    from .api import Api

    start = [args.path] if args.path else None

    if args.browser:
        _run_browser(Api(mode="browser", start_paths=start), args.port, not args.no_open)
        return 0

    try:
        import webview
    except ImportError:
        print("pywebview is not installed - falling back to browser mode (pip install pywebview)")
        _run_browser(Api(mode="browser", start_paths=start), args.port)
        return 0

    from . import winapi

    width, height, x, y = 1460, 930, None, None
    area = winapi.work_area()  # fit comfortably on smaller / high-DPI screens, centred
    if area:
        width = max(1000, min(width, int(area[0] * 0.92)))
        height = max(640, min(height, int(area[1] * 0.92)))
        x, y = max(0, (area[0] - width) // 2), max(0, (area[1] - height) // 2)
    api = Api(mode="webview", start_paths=start)
    window = webview.create_window(
        APP_NAME,
        url=resource_path("ui", "index.html"),
        js_api=api,
        width=width,
        height=height,
        x=x,
        y=y,
        min_size=(1000, 640),
        background_color="#120e0b",
        text_select=False,
    )
    api._set_window(window)
    window.events.closing += api._shutdown
    webview.start(debug=args.debug, http_server=True, private_mode=False,
                  storage_path=os.path.join(data_dir(), "webview"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
