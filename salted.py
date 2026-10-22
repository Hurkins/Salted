#!/usr/bin/env python3

import os
import re
import time 
import json
import shutil
import pyudev
import tempfile
import argparse
import threading
import subprocess
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class saltedd (FileSystemEventHandler):  
    def __init__(self):
        self.downloads = Path.home() / "Downloads"
        self.waiting   = self.downloads / ".salted_waiting"
        self.pending_timers = {}
        self.waiting.mkdir(parents=True,exist_ok=True)


    def track_file(self, path):
        path = Path(path)
        size =  path.stat().st_size
        last_change = path.stat().st_mtime
    def notification(self, action):
        subprocess.run([
            "notify-send",
            "Salted",
            action
            ])
        time.sleep(1)
    DEFAULT_CONFIG = {
                "documents":(Path.home() / "Documents", [".pdf", ".docx", ".doc", ".odt", ".txt", ".md", ".rtf", ".tex",".xlsx", ".xls", ".csv", ".ods",".pptx", ".ppt", ".odp", ".key"]),

                "images":(Path.home() / "Pictures",[".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".tiff", ".ico", ".heic"]),

                "audio":(Path.home() / "Music",[".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".wma"]),
                
                "video": (Path.home() / "Videos",[".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".wmv"]),

                "archives": (Path.home() / "Archives",[".zip", ".tar", ".gz", ".rar", ".7z", ".bz2", ".xz", ".tar.gz"]),

                "code":(Path.home() / "Codes",[".py", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".sh", ".rs", ".go", ".rb", ".php", ".html", ".css", ".json", ".yaml", ".yml", ".sql"]),

                "executables":(Path.home() / "Installers",[".exe", ".msi", ".deb", ".rpm", ".appimage", ".run"]),

                "disk_images": (Path.home() / "Disk_Images",[".iso", ".img", ".dmg"]),

                "fonts":(Path.home() / ".local/share/fonts", [".ttf", ".otf", ".woff", ".woff2"]),

                "ebooks": (Path.home() / "Documents/Ebooks",[".epub", ".mobi", ".azw3", ".fb2"]),
            }

    CONFIG_PATH = str(Path.home() / ".config" / "salted")
    Path(CONFIG_PATH).mkdir(parents=True, exist_ok=True)
    CONFIG_FILE = os.path.join(CONFIG_PATH, "config.json")

    def load_config(self):
        if os.path.exists(self.CONFIG_FILE) and os.path.getsize(self.CONFIG_FILE) > 0:
            with open(self.CONFIG_FILE, "r") as p:
                data = json.load(p)
        else:
            data = self.DEFAULT_CONFIG
        return data
    
    def save_config(self, data=None):
        if data is None:
            data = self.load_config()
        path = self.CONFIG_FILE
        with tempfile.NamedTemporaryFile(prefix='temp_cofig',dir=self.CONFIG_PATH,suffix='.json', delete=False) as temp_cofig:
            temp_cofig.write(json.dumps(data, indent=2, default=str).encode('utf-8'))
            temp_cofig.flush()
            temp_dir = temp_cofig.name
        os.rename(temp_dir, path)


    def find_device_path(self, path:str):
        best_match = None
        best_devname = None
        with open("/proc/mounts") as f:
            for line in f:
                fields = line.split()
                if Path(path).is_relative_to(Path(fields[1])):
                    if  best_match is None or len(fields[1]) > len(best_match):
                        best_match = fields[1]
                        best_devname = fields[0]
        return best_devname

    def get_uuid_device(self, devname: str):
        result = subprocess.run(["lsblk", "-no", "UUID", devname], capture_output=True, text=True)
        if result.returncode !=0:
            return None
        uuid = result.stdout.strip()
        if not uuid:
            return None
        return uuid
    def themountpoint(self, devname):
        with open("/proc/mounts") as f:
            for line in f:
                fields = line.split()
                if fields[0] == devname:
                    return fields[1]
            return None
 
    def block_mount(self, stuff, wait=3, max_wait=60):
        mountpoint = self.themountpoint(stuff['Partition'])
        if mountpoint is not None:
            self.pending_timers.pop(stuff['Partition'], None)
            self.swip(self.waiting)
            return
        else:
            nexttt = wait * 2
            if nexttt > max_wait:
                self.pending_timers.pop(stuff['Partition'], None)
                return

            timer = threading.Timer(nexttt,self.block_mount, args=(stuff, nexttt, max_wait))
            self.pending_timers[stuff['Partition']] = timer
            timer.start()

    def block_event(self, device):
            if device.action == 'add':
                uuid = device.properties.get('ID_FS_UUID')
                if uuid is None:
                    return
                category_name = self.get_category_for_uuid(uuid)
                if category_name == None:
                    return
                stuff = {
                    "Partition": device.device_node,
                    "category": category_name
                }
                self.block_mount(stuff)
            elif device.action == 'remove':
                if device.device_node in self.pending_timers:
                    self.pending_timers[device.device_node].cancel()
    def block_watcher(self):
        context = pyudev.Context()
        for device in context.list_devices(subsystem='block', DEVTYPE='partition'):
            uuid = device.properties.get('ID_FS_UUID')
            if uuid is None:
                continue
            category_name = self.get_category_for_uuid(uuid)
            if category_name is None:
                continue
            stuff = {"Partition": device.device_node, "category": category_name}
            self.block_mount(stuff)
        monitor = pyudev.Monitor.from_netlink(context)
        monitor.filter_by(subsystem='block', device_type='partition')
        observer = pyudev.MonitorObserver(monitor, callback=self.block_event)
        observer.start()
        return observer
    def get_category_for_uuid(self, uuid: str):
        data = self.load_config()

        for category_name, entry in data.items():
            if not isinstance(entry, dict): continue
            if entry["uuid"] == uuid:
                return category_name
        return None

    def salthem(self, path):
        path   = Path(path)
        data = self.load_config()
        matched = False
        try:
            for directory_name, entry in data.items():
                if isinstance(entry, dict):
                    destination_path = entry["path"]
                    extensions = entry["extensions"]
                else:
                    destination_path, extensions = entry
                    
                if path.suffix not in extensions:
                    continue
                try:
                    path_obj = Path(path)
                    stem = path_obj.stem
                    suffix = path_obj.suffix
                    i = 1
                    path_check = Path(destination_path)/path_obj.name
                    while path_check.exists():
                        path_check = Path(destination_path)/f"{stem} ({i}){suffix}"
                        i += 1

                    self.copy_with_progress(path, path_check)
                    self.notification(f"File moved to {destination_path}")
                    matched  = True
                except(FileExistsError, NotADirectoryError,FileNotFoundError):
                    if Path(destination_path).is_relative_to(Path.home()):
                        os.makedirs(destination_path, exist_ok=True)
                        self.copy_with_progress(path, path_check)
                        self.notification(destination_path)
                        matched  = True
                    else:
                        shutil.move(path, self.waiting)
                        return
            try:
                if matched:
                    path.unlink(missing_ok=True)
            except IsADirectoryError:
                pass
        except shutil.Error as e:
            match = re.search(r"'(.*?)'", str(e.args))
            pathe = match.group(1) if match else None
            
            folder = os.path.dirname(pathe)
            filename= os.path.basename(pathe)
            name,ext = os.path.splitext(filename)
            i = 1

            new_path = pathe

            while os.path.exists(new_path):
                new_name = f"{name} ({i}){ext}"
                new_path = os.path.join(folder, new_name)
                i += 1
            shutil.move(path, new_path)
            subprocess.run([
                "notify-send",
                "Salted",
                f"File ALREADY EXIST & ReNamed {new_name}"
            ])
    def start_progress(self, message):
        strt_progress = subprocess.run(["notify-send", "-p", "Salted", message],capture_output=True, text=True)
        captured_outpt= strt_progress.stdout.strip()
        return captured_outpt
    def update_progress(self, notif_id, message):
        if not notif_id: return
        subprocess.run(["notify-send", "-r", notif_id, "Salted", message])
    
    def copy_with_progress(self, src, dst):
        chunk_size = 1024 * 1024
        min_size   = 50 * 1024 * 1024
        copied = 0
        last_change = -1
        total_size = src.stat().st_size 
        
        if total_size <= min_size:
            shutil.copy2(src, dst)
            return
        message = f"Copying {src.name}..."
        
        with open(src, "rb") as fsrc, open(dst, "wb") as fdst:
            notif_id = self.start_progress(message)
            while True:
                chunk = fsrc.read(chunk_size)
                if not chunk:
                    break
                fdst.write(chunk)
                copied += len(chunk)
                percent = 100 * copied // total_size
                if percent >= last_change + 10:
                    self.update_progress(notif_id, f"{src.name} progress {percent}")
                    last_change = percent
                    time.sleep(1)
        shutil.copystat(src, dst)
        self.update_progress(notif_id, f"{src.name} progress DONE!")


    def on_created(self, event):
        if event.is_directory:
            return
        path = event.src_path
        self.track_file(path)
        self.salthem(path)

    
    def swip(self, path=None):
        is_default = path is None
        if path is None:
            path = self.downloads
        for f in path.iterdir():
            self.salthem(f)
        if is_default:
            threading.Timer(1800, self.swip).start()
        
    def reload(self):
        data = self.load_config()
        changed = False

        for category_name, entry in  data.items():
            if isinstance(entry, dict) and entry.get("uuid"):
                continue
            if isinstance(entry, dict):
                path = entry["path"]
            else:
                path = entry[0]
            if Path(path).is_relative_to(Path.home()):
                continue
            devname = self.find_device_path(path)
            if devname is None:
                self.notification(f"Device for '{category_name}' not mounted - mount it and run --reload again")
                continue
            uuid = self.get_uuid_device(devname)
            if uuid is None:
                self.notification(f"Could not determine UUID for '{category_name}' - check blkid manually")
                continue
            if isinstance(entry, dict):
                extensions = entry["extensions"]
            else:
                extensions = entry[1]

            data[category_name] = {"path": path, "uuid":uuid, "extensions":extensions}
            changed = True

        if changed:
            self.save_config(data)

def main():
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument("--reload", action="store_true")
        args = parser.parse_args()

        handler = saltedd()

        if args.reload: handler.reload(); return

        handler.swip()
        block = handler.block_watcher()

        observer = Observer()

        observer.schedule(handler, path=str(handler.downloads), recursive=True)
        observer.start()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
            block.stop()

        observer.join()
    except KeyboardInterrupt:
        return
main()
