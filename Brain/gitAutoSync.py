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
last_check_time = datetime.now()
idle_mode = False
watcher_enabled = True
status = "Initializing"
observer = None
root = None

# === FILE CHANGE TRACKING ===
class ChangeHandler(FileSystemEventHandler):
    def on_any_event(self, event):
        global last_change_time
        if not event.is_directory:
            last_change_time = datetime.now()

# === GIT OPS ===
def run_git_commands(force=False):
    try:
        subprocess.run(["git", "-C", GIT_REPO_PATH, "add", "."], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        result = subprocess.run(["git", "-C", GIT_REPO_PATH, "status", "--porcelain"],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)

        if result.stdout.strip():
            diff_result = subprocess.run(["git", "-C", GIT_REPO_PATH, "diff", "--cached", "--name-status"],
                                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            if not force:
                print("🕒 60s idle reached...\n🎉Pushing files to Git...")
            else:
                print("📤 Pushing files to Git...")

            for line in diff_result.stdout.strip().splitlines():
                status_code, *filepath_parts = line.split()
                filepath = " ".join(filepath_parts)

                action = {
                    "A": "Added",
                    "M": "Edited",
                    "D": "Removed",
                    "R100": "Moved"
                }.get(status_code, f"Changed ({status_code})")

                print(f"✨ {action}: {filepath}") 
                print("\n")

            subprocess.run(["git", "-C", GIT_REPO_PATH, "commit", "-m", "Auto-commit"],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "-C", GIT_REPO_PATH, "push"],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("✅ Push Complete!\nRestarting timer...\n")
            return True  # Indicates a push occurred
        elif force:
            print("🤷 No modified files found. No push needed...\n")
        return False
    except subprocess.CalledProcessError as e:
        print(f"💥 ERROR! Git operation failed!\n🚫 Reason: {e}\n")
        return False

# === TIMER LOGIC ===
def update_timers():
    global last_change_time, last_check_time, idle_mode

    print("🟢 Git Auto Sync Running... 💻\n🎬 Opening GUI...\n")
    run_git_commands(force=True)
    last_change_time = datetime.now()
    last_check_time = datetime.now()

    while True:
        now = datetime.now()
        since_change = (now - last_change_time).total_seconds()
        since_check = (now - last_check_time).total_seconds()

        if not idle_mode:
            if since_check >= 60:
                last_check_time = now
                if since_change <= 60:
                    result = subprocess.run(["git", "-C", GIT_REPO_PATH, "diff", "--name-only"],
                                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
                    changed_files = result.stdout.strip().splitlines()
                    if changed_files:
                        print("✏️ Modifications detected on files:")
                        for path in changed_files:
                            print(path)
                        print("\n⏱️ Restarting timer...\n")
                        last_check_time = now
                        last_change_time = now  # ✅ Only reset if modifications found
                        continue
                else:
                    pushed = run_git_commands(force=False)
                    if pushed:
                        last_change_time = now  # ✅ Only reset if push occurred
                    last_check_time = now
                    continue

            if (now - last_change_time).total_seconds() >= IDLE_THRESHOLD_SECONDS:
                print("😴 You've been idle for 5 minutes... Pausing script...\n")
                idle_mode = True
                close_gui()
                observer.stop()
                Thread(target=idle_watcher, daemon=True).start()

        time.sleep(1)

# === IDLE MONITOR ===
def idle_watcher():
    global idle_mode, last_change_time, observer
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
            now = datetime.now()
            elapsed = int((now - last_change_time).total_seconds())
            check_elapsed = int((now - last_check_time).total_seconds())
            cooldown = max(0, COOLDOWN_SECONDS - check_elapsed)
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
