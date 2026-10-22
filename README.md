# Salted

A background daemon for Linux that automatically sorts files from your
`Downloads` folder into category folders, including folders on external
drives. Drives are tracked by filesystem UUID, so sorting keeps working when a
drive is unplugged, replugged, or mounted at a different path.

## Features

- Watches `~/Downloads` in real time and sorts new files by extension
- Category destinations can be a local folder (e.g. `~/Documents`) or a folder
  on an external drive
- If an external drive isn't available, files wait in `Downloads/.salted_waiting`
  and are moved automatically once the drive is mounted. This also works when
  the drive was already plugged in but unmounted when the daemon started
- Files are copied first and the original is deleted only after the copy
  succeeds
- If a file with the same name already exists at the destination, the new one
  is saved as `name (1).ext`, `name (2).ext`, and so on instead of overwriting
- Unrecognized extensions are left alone, which also protects in-progress
  downloads (`.crdownload`, `.part`, ...)
- Desktop notifications for moves, plus a live progress notification for large
  files (over 50 MB)
- A periodic sweep every 30 minutes backs up the real-time watcher

## Requirements

- Linux with `udev` and a notification daemon (uses `notify-send`)
- Python 3.9 or newer
- `lsblk` (part of `util-linux`, present on virtually all distros)

## Installation

```bash
git clone <repo-url> salted
cd salted
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
chmod +x salted.py
```

## Configuration

Salted reads `~/.config/salted/config.json`. If the file doesn't exist, the
built-in defaults are used: standard folders such as `~/Documents`,
`~/Pictures`, `~/Music` and `~/Videos`, created on demand. To customize,
create the file yourself. Each key is a category name, and each value is a
destination folder plus the extensions that go there:

```json
{
  "documents": ["/home/youruser/Documents", [".pdf", ".docx", ".txt"]],
  "images":    ["/home/youruser/Pictures",  [".jpg", ".png", ".gif"]],
  "disk_images": ["/run/media/youruser/MyDrive/ISO", [".iso", ".img"]]
}
```

Use absolute paths. Salted reads the file fresh on every operation, so edits
take effect immediately without a restart. Keep each extension in only one
category.

### External drives

Add the category the same way as any other, using the folder's path while the
drive is plugged in and mounted (like `disk_images` above), then run:

```bash
./salted.py --reload
```

`--reload` finds which drive backs each non-home path, looks up its UUID, and
rewrites that entry in the config to include it. Afterwards the entry looks
like this:

```json
"disk_images": {
  "path": "/run/media/youruser/MyDrive/ISO",
  "uuid": "b0c3818d-b53c-487e-93b2-72af0777b1e7",
  "extensions": [".iso", ".img"]
}
```

If a drive isn't mounted when you run `--reload`, you'll get a notification
telling you to mount it and run the command again. It's safe to run while the
daemon is already running.

## Usage

Run in the foreground (stop with Ctrl+C):

```bash
source venv/bin/activate
./salted.py
```

## Running as a background service (systemd)

1. Create `~/.config/systemd/user/salted.service` (run
   `mkdir -p ~/.config/systemd/user` first if the folder doesn't exist):

    ```ini
    [Unit]
    Description=Salted file sorter

    [Service]
    Environment=PATH=%h/salted/venv/bin:/usr/bin:/bin
    ExecStart=%h/salted/salted.py
    Restart=on-failure

    [Install]
    WantedBy=default.target
    ```

   Change the `salted/` part of both paths to wherever you cloned the project.
   `%h` expands to your home directory. The `Environment=PATH` line makes the
   script's `#!/usr/bin/env python3` shebang pick up the venv's Python, which
   is where `watchdog` and `pyudev` are installed.

2. Enable and start it (no `sudo`; this is a user service):

    ```bash
    systemctl --user daemon-reload
    systemctl --user enable --now salted.service
    ```

3. Check status and logs:

    ```bash
    systemctl --user status salted.service
    journalctl --user -u salted.service -n 40 --no-pager
    ```

4. Stop it:

    ```bash
    systemctl --user stop salted.service
    ```

### Troubleshooting

- **`status=203/EXEC`, "Permission denied"**: the script isn't executable.
  Run `chmod +x salted.py`.
- **`ModuleNotFoundError`** in the logs: systemd isn't using the venv's Python.
  Check that the paths in `Environment=PATH=` are spelled exactly like your
  real folder (Linux paths are case-sensitive).
- **`start-limit-hit`**: systemd gave up after repeated crashes. Read the
  traceback above it in the logs, fix the cause, then run
  `systemctl --user reset-failed salted.service`.

## How it works

- A `watchdog` observer watches `~/Downloads` and matches each new file's
  extension against your categories.
- For a local category, the folder is created if it's missing and the file is
  copied in. For an external category, Salted tries the copy directly, and if
  the destination doesn't exist (drive not mounted) the file is parked in
  `.salted_waiting`.
- A `pyudev` listener watches for partitions being plugged in. When one
  matches a configured UUID, Salted waits for it to mount (retrying with a
  growing delay) and then sweeps the waiting folder. At startup it also checks
  partitions that are already present.
- The original file is deleted only after every matching copy has succeeded.

## Known limitations

- Mount paths containing spaces or other special characters may not be
  recognized, because `/proc/mounts` escapes them.
- If a drive is unplugged in the middle of a large copy, a partial file may be
  left at the destination.
- Extensions listed in more than one category behave unpredictably.
- Linux only.
- Tools that write the final filename directly (wget, curl -o) can trigger a copy while the file is still being      written. Browsers avoid this with temporary extensions. Salted could move a half-downloaded file and delete the    original.

## License

Copyright © 2026 Hurkins

This project is licensed under the GNU Affero General Public License v3.0. See the `LICENSE` file for details.
