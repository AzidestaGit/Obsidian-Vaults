import os
import time
from datetime import datetime, timedelta
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import tkinter as tk
from threading import Thread
import subprocess

# Configuration
FOLDER_TO_WATCH = r"C:\ObsidianVaults\Brain"
COOLDOWN_SECONDS = 120  # 2 minutes
IDLE_THRESHOLD_SECONDS = 600  # 10 minutes
GIT_REPO_PATH = r"C:\ObsidianVaults"  # Path to the Git repository

# Global variables
last_change_time = datetime.now()
cooldown_remaining = COOLDOWN_SECONDS
idle_remaining = IDLE_THRESHOLD_SECONDS
status = "Active"
watcher_enabled = True

# File change handler
class ChangeHandler(FileSystemEventHandler):
    def on_any_event(self, event):
        global last_change_time, status
        if watcher_enabled:
            last_change_time = datetime.now()
            status = "Active"
            print(f"File change detected: {event.src_path}")

# Function to run Git commands
def run_git_commands():
    try:
        print("Changes detected. Committing and pushing...")
        subprocess.run(["git", "-C", GIT_REPO_PATH, "add", "."], check=True)
        subprocess.run(["git", "-C", GIT_REPO_PATH, "commit", "-m", "Auto-commit"], check=True)
        subprocess.run(["git", "-C", GIT_REPO_PATH, "push"], check=True)
        print("Changes pushed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error during Git operations: {e}")

# Function to update timers
def update_timers():
    global cooldown_remaining, idle_remaining, status, watcher_enabled, last_change_time
    while True:
        now = datetime.now()
        cooldown_remaining = max(0, COOLDOWN_SECONDS - (now - last_change_time).total_seconds())
        idle_remaining = max(0, IDLE_THRESHOLD_SECONDS - (now - last_change_time).total_seconds())

        if cooldown_remaining == 0 and watcher_enabled:
            run_git_commands()
            last_change_time = datetime.now()  # Reset cooldown timer

        if idle_remaining == 0 and watcher_enabled:
            status = "Idle"
            watcher_enabled = False
            print("No activity detected. Pausing watcher...")

        time.sleep(1)

# Function to update the GUI
def update_gui():
    while True:
        cooldown_label.config(text=f"Cooldown Remaining: {int(cooldown_remaining)} seconds")
        idle_label.config(text=f"Idle Remaining: {int(idle_remaining)} seconds")
        status_label.config(text=f"Status: {status}")
        root.update()
        time.sleep(1)

# Start file watcher
def start_watcher():
    global watcher_enabled, status
    event_handler = ChangeHandler()
    observer = Observer()
    observer.schedule(event_handler, FOLDER_TO_WATCH, recursive=True)
    observer.start()
    print(f"Watching folder: {FOLDER_TO_WATCH}")
    try:
        while True:
            if not watcher_enabled:
                status = "Paused"
                observer.stop()
                time.sleep(1)
            else:
                observer.start()
                status = "Active"
            time.sleep(1)
    except KeyboardInterrupt:
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

# Start threads
Thread(target=update_timers, daemon=True).start()
Thread(target=update_gui, daemon=True).start()
Thread(target=start_watcher, daemon=True).start()

# Run the GUI
root.mainloop()