import os
import time
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import tkinter as tk
from threading import Thread
import subprocess

# Configuration
FOLDER_TO_WATCH = r"C:\ObsidianVaults\Brain"
COOLDOWN_SECONDS = 60    # 🔄 1 minute cooldown before auto-commit
IDLE_THRESHOLD_SECONDS = 360  # 💤 6 minutes idle timeout
GIT_REPO_PATH = r"C:\ObsidianVaults"  # Git repo path

# Global state
last_change_time = datetime.now()
cooldown_remaining = COOLDOWN_SECONDS
idle_remaining = IDLE_THRESHOLD_SECONDS
status = "Active"
watcher_enabled = True

# File system event handler
class ChangeHandler(FileSystemEventHandler):
    def on_any_event(self, event):
        global last_change_time, status
        if watcher_enabled:
            last_change_time = datetime.now()
            status = "Active"
            print(f"File change detected: {event.src_path}")

# Git automation
def run_git_commands():
    try:
        # Stage any new or modified files
        subprocess.run(["git", "-C", GIT_REPO_PATH, "add", "."], check=True)

        # Check for staged changes
        result = subprocess.run(
            ["git", "-C", GIT_REPO_PATH, "status", "--porcelain"],
            stdout=subprocess.PIPE,
            text=True
        )

        if result.stdout.strip():
            print("Changes detected. Committing and pushing...")
            subprocess.run(["git", "-C", GIT_REPO_PATH, "commit", "-m", "Auto-commit"], check=True)
            subprocess.run(["git", "-C", GIT_REPO_PATH, "push"], check=True)
            print("✅ Sync complete: Changes committed and pushed.")
        else:
            print("🟡 No changes to commit. Push not needed.")
    except subprocess.CalledProcessError as e:
        print(f"❌ Git operation failed: {e}")

# Timer and commit logic
def update_timers():
    global cooldown_remaining, idle_remaining, status, watcher_enabled, last_change_time
    while True:
        now = datetime.now()
        seconds_since_change = (now - last_change_time).total_seconds()
        cooldown_remaining = max(0, COOLDOWN_SECONDS - seconds_since_change)
        idle_remaining = max(0, IDLE_THRESHOLD_SECONDS - seconds_since_change)

        if cooldown_remaining == 0 and watcher_enabled:
            run_git_commands()
            last_change_time = datetime.now()  # reset after commit or check

        if idle_remaining == 0 and watcher_enabled:
            status = "Idle"
            watcher_enabled = False
            print("🛑 No activity detected. Pausing watcher...")

        time.sleep(1)

# GUI updater
def update_gui():
    while True:
        cooldown_label.config(text=f"Cooldown Remaining: {int(cooldown_remaining)} seconds")
        idle_label.config(text=f"Idle Remaining: {int(idle_remaining)} seconds")
        status_label.config(text=f"Status: {status}")
        root.update()
        time.sleep(1)

# Watchdog runner
def start_watcher():
    global status
    event_handler = ChangeHandler()
    observer = Observer()
    observer.schedule(event_handler, FOLDER_TO_WATCH, recursive=True)
    observer.start()
    print(f"👀 Watching folder: {FOLDER_TO_WATCH}")
    try:
        while True:
            if not watcher_enabled:
                status = "Paused"
            else:
                status = "Active"
            time.sleep(1)
    except KeyboardInterrupt:
        print("👋 Watcher interrupted. Stopping...")
        observer.stop()
    observer.join()

# GUI setup
root = tk.Tk()
root.title("Git AutoSync Dashboard")
root.geometry("400x200")

status_label = tk.Label(root, text=f"Status: {status}", font=("Arial", 14))
status_label.pack(pady=10)

cooldown_label = tk.Label(root, text=f"Cooldown Remaining: {cooldown_remaining} seconds", font=("Arial", 12))
cooldown_label.pack(pady=5)

idle_label = tk.Label(root, text=f"Idle Remaining: {idle_remaining} seconds", font=("Arial", 12))
idle_label.pack(pady=5)

# Launch threads
Thread(target=update_timers, daemon=True).start()
Thread(target=update_gui, daemon=True).start()
Thread(target=start_watcher, daemon=True).start()

# Run GUI
try:
    root.mainloop()
except KeyboardInterrupt:
    print("👋 Exiting GUI...")
