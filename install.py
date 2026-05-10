#!/usr/bin/env python3
"""
install.py — Universal installer for claude_auto.py
Sets up the `auto` command for all shells on Linux, macOS, and Windows.

Usage:
    python3 install.py          # Install
    python3 install.py --uninstall  # Remove
"""
import sys
import os
import shutil
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(SCRIPT_DIR, "claude_auto.py")

# ── Helpers ──────────────────────────────────────────────────────────────────

def ok(msg):  print(f"\033[32m  ✓ {msg}\033[0m")
def info(msg): print(f"\033[34m  • {msg}\033[0m")
def warn(msg): print(f"\033[33m  ⚠ {msg}\033[0m")
def err(msg):  print(f"\033[31m  ✗ {msg}\033[0m")

def run(cmd, check=False):
    try:
        subprocess.run(cmd, shell=True, check=check)
        return True
    except Exception:
        return False

def file_contains(path, text):
    try:
        return text in open(path).read()
    except Exception:
        return False

def append_to_file(path, text):
    with open(path, "a") as f:
        f.write(text)

# ── Linux / macOS installer ───────────────────────────────────────────────────

def install_posix(uninstall=False):
    # Where to install the `auto` binary
    install_dir = os.path.expanduser("~/.local/bin")
    install_path = os.path.join(install_dir, "auto")

    if uninstall:
        if os.path.exists(install_path):
            os.remove(install_path)
            ok(f"Removed {install_path}")
        else:
            warn("'auto' command not found — nothing to uninstall")
        return

    # Create ~/.local/bin if it doesn't exist
    os.makedirs(install_dir, exist_ok=True)

    # Copy the script and make it executable
    shutil.copy2(SOURCE, install_path)
    os.chmod(install_path, 0o755)
    ok(f"Installed to {install_path}")

    # ── Add ~/.local/bin to PATH in every shell config ────────────────────────
    path_export = f'\n# Added by claude_auto installer\nexport PATH="$HOME/.local/bin:$PATH"\n'
    path_export_fish = f'\n# Added by claude_auto installer\nset -gx PATH $HOME/.local/bin $PATH\n'

    shell_configs = {
        "bash":  [os.path.expanduser("~/.bashrc"), os.path.expanduser("~/.bash_profile")],
        "zsh":   [os.path.expanduser("~/.zshrc")],
        "ksh":   [os.path.expanduser("~/.kshrc")],
        "tcsh":  [os.path.expanduser("~/.tcshrc")],
    }

    for shell, configs in shell_configs.items():
        for cfg in configs:
            if os.path.exists(cfg) and not file_contains(cfg, ".local/bin"):
                append_to_file(cfg, path_export)
                ok(f"Added ~/.local/bin to PATH in {cfg}")

    # Fish shell needs different syntax
    fish_config = os.path.expanduser("~/.config/fish/config.fish")
    if os.path.exists(os.path.expanduser("~/.config/fish")):
        os.makedirs(os.path.dirname(fish_config), exist_ok=True)
        if not file_contains(fish_config, ".local/bin"):
            append_to_file(fish_config, path_export_fish)
            ok(f"Added ~/.local/bin to PATH in {fish_config}")

    # Check if ~/.local/bin is already live in this session
    current_path = os.environ.get("PATH", "")
    if install_dir not in current_path:
        warn("~/.local/bin is not in your current PATH yet.")
        info("Run this once now (or restart your terminal):")
        print(f'\n      export PATH="$HOME/.local/bin:$PATH"\n')

    # ── Final verification ────────────────────────────────────────────────────
    which = shutil.which("auto", path=install_dir + ":" + current_path)
    if which:
        ok(f"'auto' command is ready!")
    else:
        info("'auto' will be available after you restart your terminal.")

# ── Windows installer ─────────────────────────────────────────────────────────

def install_windows(uninstall=False):
    import winreg

    # We'll install a .bat file to %USERPROFILE%\AppData\Local\Microsoft\WindowsApps
    # which is already in PATH on modern Windows 10/11
    win_apps = os.path.join(os.environ.get("LOCALAPPDATA", ""), 
                             "Microsoft", "WindowsApps")
    bat_path = os.path.join(win_apps, "auto.bat")
    # Fallback: use the user's home bin dir
    fallback_dir = os.path.join(os.environ.get("USERPROFILE", ""), "bin")
    fallback_bat = os.path.join(fallback_dir, "auto.bat")

    python_exe = sys.executable

    bat_content = f'@echo off\n"{python_exe}" "{SOURCE}" %*\n'

    if uninstall:
        for p in [bat_path, fallback_bat]:
            if os.path.exists(p):
                os.remove(p)
                ok(f"Removed {p}")
        return

    # Try WindowsApps first (already in PATH, no restart needed)
    installed = False
    if os.path.isdir(win_apps):
        try:
            with open(bat_path, "w") as f:
                f.write(bat_content)
            ok(f"Installed to {bat_path}")
            installed = True
        except PermissionError:
            pass

    if not installed:
        # Fallback: install to ~/bin and add to user PATH via registry
        os.makedirs(fallback_dir, exist_ok=True)
        with open(fallback_bat, "w") as f:
            f.write(bat_content)
        ok(f"Installed to {fallback_bat}")

        # Add ~/bin to the user's PATH permanently via the Windows registry
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                "Environment", 0, winreg.KEY_READ | winreg.KEY_WRITE
            )
            current, _ = winreg.QueryValueEx(key, "PATH")
            if fallback_dir.lower() not in current.lower():
                winreg.SetValueEx(key, "PATH", 0, winreg.REG_EXPAND_SZ,
                                  current + ";" + fallback_dir)
                ok(f"Added {fallback_dir} to your Windows user PATH")
                warn("Please restart PowerShell/CMD for changes to take effect.")
            winreg.CloseKey(key)
        except Exception as e:
            warn(f"Could not update Windows PATH automatically: {e}")
            info(f"Manually add this to your PATH: {fallback_dir}")

    ok("'auto' command installed for CMD and PowerShell!")

    # ── PowerShell profile (adds function for PowerShell users) ────────────────
    ps_profile = os.path.join(
        os.environ.get("USERPROFILE", ""),
        "Documents", "PowerShell", "Microsoft.PowerShell_profile.ps1"
    )
    ps_content = f'\n# Added by claude_auto installer\nfunction auto {{ & "{python_exe}" "{SOURCE}" @args }}\n'
    try:
        os.makedirs(os.path.dirname(ps_profile), exist_ok=True)
        if not os.path.exists(ps_profile) or not file_contains(ps_profile, "claude_auto"):
            append_to_file(ps_profile, ps_content)
            ok(f"Added PowerShell 'auto' function to {ps_profile}")
    except Exception as e:
        warn(f"Could not write PowerShell profile: {e}")

# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    uninstall = "--uninstall" in sys.argv

    print()
    print("=" * 55)
    if uninstall:
        print("  claude_auto — UNINSTALLER")
    else:
        print("  claude_auto — INSTALLER")
        print("  Sets up: auto claude / auto claude --resume <id>")
    print("=" * 55)
    print()

    if not os.path.exists(SOURCE):
        err(f"Cannot find claude_auto.py at: {SOURCE}")
        err("Please run this installer from the same directory as claude_auto.py")
        sys.exit(1)

    if sys.platform == "win32":
        install_windows(uninstall)
    else:
        install_posix(uninstall)

    print()
    if not uninstall:
        print("=" * 55)
        print("  Done! You can now use:")
        print()
        print("      auto claude")
        print("      auto claude --resume <session-id>")
        print("      auto claude --dangerously-skip-permissions")
        print()
        print("  (works in bash, zsh, fish, ksh, CMD, PowerShell)")
        print("=" * 55)
    print()

if __name__ == "__main__":
    main()
