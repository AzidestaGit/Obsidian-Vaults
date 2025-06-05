import os
import time
import tkinter as tk
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from threading import Thread
import subprocess

# === CONFIGURATION ===
FOLDER_TO_WATCH = r"C:\ObsidianVaults\Brain"
GIT_REPO_PATH = r"C:\ObsidianVaults"
COOLDOWN_SECONDS = 60
IDLE_THRESHOLD_SECONDS = 300  # 5 minutes
IDLE_POLL_INTERVAL = 10       # check every 10 seconds in idle mode

# === GLOBALS ===
last_change_time = datetime.now()
cooldown_checkpoints = {30, 60}
change_log = []
idle_mode = False
watcher_enabled = True
status = "Initializing"
observer = None
root = None

# === FILE CHANGE TRACKING ===
class ChangeHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if not event.is_directory:
            change_log.append(("Edited", event.src_path))

    def on_created(self, event):
        if not event.is_directory:
            change_log.append(("Added", event.src_path))

    def on_deleted(self, event):
        if not event.is_directory:
            change_log.append(("Removed", event.src_path))

    def on_moved(self, event):
        if not event.is_directory:
            change_log.append(("Moved", f"{event.src_path} -> {event.dest_path}"))

# === GIT OPS ===
def run_git_commands():
    try:
        subprocess.run(["git", "-C", GIT_REPO_PATH, "add", "."], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        result = subprocess.run(
            ["git", "-C", GIT_REPO_PATH, "status", "--porcelain"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True
        )
        if result.stdout.strip():
            print("📤 Pushing files to Git...")
            for change_type, path in change_log:
                print(f"{change_type}: {path}")
            subprocess.run(["git", "-C", GIT_REPO_PATH, "commit", "-m", "Auto-commit"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "-C", GIT_REPO_PATH, "push"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("✅ Push Complete! ✨\n")
        else:
            print("🤷 No modified files found. No push needed...\n")
    except subprocess.CalledProcessError as e:
        print(f"💥 ERROR! Git operation failed!\n🚫 Reason: {e}\n")

# === TIMER LOGIC ===
def update_timers():
    global last_change_time, idle_mode, change_log, status, root
    print("🟢 Git Auto Sync Running... 💻\n🎬 Opening GUI...\n")

    # Immediate sync check on startup
    run_git_commands()
    last_change_time = datetime.now()

    while True:
        elapsed = (datetime.now() - last_change_time).total_seconds()

        if not idle_mode and int(elapsed) in cooldown_checkpoints:
            if change_log:
                print("🟨 File change detected in the following files:")
                for change_type, path in change_log:
                    print(f"{change_type}: {path}")
                print("⏱️ Restarting Countdown...\n")
                last_change_time = datetime.now()
                change_log = []

        elif not idle_mode and int(elapsed) >= COOLDOWN_SECONDS:
            run_git_commands()
            last_change_time = datetime.now()
            change_log = []

        elif not idle_mode and elapsed >= IDLE_THRESHOLD_SECONDS:
            print("😴 You've been idle for 5 minutes... Pausing script...\n")
            idle_mode = True
            close_gui()
            observer.stop()
            Thread(target=idle_watcher, daemon=True).start()

        time.sleep(1)

# === IDLE MONITOR ===
def idle_watcher():
    global idle_mode, last_change_time, change_log, status, observer
    while idle_mode:
        for dirpath, _, filenames in os.walk(FOLDER_TO_WATCH):
            for f in filenames:
                try:
                    full_path = os.path.join(dirpath, f)
                    if os.path.getmtime(full_path) > last_change_time.timestamp():
                        print("🔄 Activity detected! Resuming Auto Git Sync Script... 🎉\n🖥️ Opening GUI...\n")
                        last_change_time = datetime.now()
                        idle_mode = False
                        start_gui()
                        observer = Observer()
                        observer.schedule(ChangeHandler(), FOLDER_TO_WATCH, recursive=True)
                        observer.start()
                        return
                except FileNotFoundError:
                    continue
        time.sleep(IDLE_POLL_INTERVAL)

# === GUI ===
def update_gui():
    global root
    while True:
        if root:
            elapsed = int((datetime.now() - last_change_time).total_seconds())
            cooldown = max(0, COOLDOWN_SECONDS - elapsed)
            idle = max(0, IDLE_THRESHOLD_SECONDS - elapsed)
            status_label.config(text=f"Status: {'Paused' if idle_mode else 'Active'}")
            cooldown_label.config(text=f"Cooldown Remaining: {cooldown} seconds")
            idle_label.config(text=f"Idle Remaining: {idle} seconds")
            root.update()
        time.sleep(1)

def start_gui():
    global root, status_label, cooldown_label, idle_label
    root = tk.Tk()
    root.title("Git AutoSync Dashboard")
    root.geometry("400x200")
    status_label = tk.Label(root, text=f"Status: {status}", font=("Arial", 14))
    status_label.pack(pady=10)
    cooldown_label = tk.Label(root, text="", font=("Arial", 12))
    cooldown_label.pack(pady=5)
    idle_label = tk.Label(root, text="", font=("Arial", 12))
    idle_label.pack(pady=5)

def close_gui():
    global root
    if root:
        root.destroy()
        root = None

# === MAIN ===
def start_all():
    global observer
    try:
        start_gui()
        Thread(target=update_gui, daemon=True).start()
        observer = Observer()
        observer.schedule(ChangeHandler(), FOLDER_TO_WATCH, recursive=True)
        observer.start()
        Thread(target=update_timers, daemon=True).start()
        root.mainloop()
    except Exception as e:
        print(f"❗ ERROR! Git Auto Sync NOT started!\n🧨 Reason: {e}")

if __name__ == '__main__':
    try:
        start_all()
    except KeyboardInterrupt:
        print("🛑 Git Auto Sync manually stopped. Goodbye! 👋")
        if observer:
            observer.stop()
        close_gui()
