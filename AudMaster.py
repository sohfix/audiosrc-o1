import os
import threading
import time
import configparser
import feedparser
import requests
from yt_dlp import YoutubeDL
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import vlc

# --- Config ---
CONFIG_DIR = r"C:\tools\config"
CONFIG_FILE = os.path.join(CONFIG_DIR, "pods.ini")
os.makedirs(CONFIG_DIR, exist_ok=True)

# --- Helper functions ---
def format_bytes(n):
    """
    Convert a numeric value in bytes to a human-readable string representation
    using appropriate size units (B, KB, MB, GB). The function ensures accurate
    conversion with two decimal precision.

    :param n: The number of bytes to be converted. Must be a non-negative integer or float.
    :type n: int or float
    :return: A string representing the size in the largest appropriate unit
        (e.g., B, KB, MB, GB), formatted with two decimals.
    :rtype: str
    """
    if n >= 1024**3: return f"{n/1024**3:.2f} GB"
    if n >= 1024**2: return f"{n/1024**2:.2f} MB"
    if n >= 1024:   return f"{n/1024:.2f} KB"
    return f"{n} B"

# --- Main App ---
class AllInOneDownloader(tk.Tk):
    """
    Represents a GUI application for downloading and playing podcasts, as well as
    YouTube audio and video content.

    This class is built around the `tkinter` framework, providing a user-friendly
    graphical interface. The application facilitates downloading podcasts and YouTube
    content (audio and video), maintaining a playback playlist, and managing a VLC
    player to play selected media. It is suitable for users who want an integrated
    solution for media downloading and playback.

    :ivar config: Stores the configuration data for podcasts, including URLs and
        output paths.
    :type config: ConfigParser
    :ivar podcasts: A dictionary containing podcast data loaded from the configuration
        file. Each entry includes podcast URLs and output directories.
    :type podcasts: dict
    :ivar vlc_inst: An instance of the VLC player.
    :type vlc_inst: vlc.Instance
    :ivar player: A VLC media player utilized for playing audio or video using the
        playlist.
    :type player: vlc.MediaPlayer
    :ivar playlist: A list containing the media titles and their corresponding paths
        for playback.
    :type playlist: list
    :ivar pod_tree: A tree view UI element for managing the podcast list and metadata.
    :type pod_tree: ttk.Treeview
    :ivar tol_var: Controls the podcast update tolerance in MB for new content downloads.
    :type tol_var: tk.IntVar
    :ivar yt_url: A variable that holds the YouTube URL entered by the user.
    :type yt_url: tk.StringVar
    :ivar yt_type: A radio button variable used to indicate whether the YouTube download
        is for audio or video.
    :type yt_type: tk.StringVar
    :ivar yt_out: The output directory for downloaded YouTube content as specified by
        the user.
    :type yt_out: tk.StringVar
    :ivar plist: A list box that displays the playback playlist.
    :type plist: tk.Listbox
    :ivar log_txt: A text widget used for displaying activity logs of the application,
        such as download progress or errors.
    :type log_txt: tk.Text
    """
    def __init__(self):
        super().__init__()
        self.title("Downloader + Player")
        self.geometry("1000x700")
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # load podcasts config
        self.config = configparser.ConfigParser()
        self.config.read(CONFIG_FILE)
        self.podcasts = {s: dict(self.config[s]) for s in self.config.sections()}

        # VLC player
        self.vlc_inst = vlc.Instance()
        self.player = self.vlc_inst.media_player_new()
        self.playlist = []  # list of (title, path)

        # build UI
        self._build_download_section()
        self._build_player_section()
        self._build_log_section()

    def _build_download_section(self):
        frame = ttk.LabelFrame(self, text="Downloads")
        frame.pack(fill="both", expand=False, padx=5, pady=5)

        # --- Podcast side ---
        pod_frame = ttk.Frame(frame)
        pod_frame.pack(side="left", fill="both", expand=True, padx=5, pady=5)

        ttk.Label(pod_frame, text="Podcasts:").pack(anchor="w")
        cols = ("URL","Output")
        self.pod_tree = ttk.Treeview(pod_frame, columns=cols, show="headings", height=8)
        for c in cols:
            self.pod_tree.heading(c, text=c)
            self.pod_tree.column(c, width=200, anchor="w")
        self.pod_tree.pack(fill="both", expand=True)

        btns = ttk.Frame(pod_frame)
        btns.pack(fill="x", pady=5)
        for txt, cmd in (("Add",self._pod_add),("Edit",self._pod_edit),
                         ("Remove",self._pod_remove),("Update",self._pod_update_selected)):
            ttk.Button(btns, text=txt, command=cmd).pack(side="left", padx=2)
        ttk.Label(btns, text="Tolerance (MB):").pack(side="left", padx=(10,2))
        self.tol_var = tk.IntVar(value=15)
        ttk.Entry(btns, textvariable=self.tol_var, width=4).pack(side="left")

        self._refresh_pod_tree()

        # --- YouTube side ---
        yt_frame = ttk.Frame(frame)
        yt_frame.pack(side="left", fill="both", expand=True, padx=5, pady=5)

        ttk.Label(yt_frame, text="YouTube URL:").pack(anchor="w")
        self.yt_url = tk.StringVar()
        ttk.Entry(yt_frame, textvariable=self.yt_url).pack(fill="x", padx=2)

        self.yt_type = tk.StringVar(value="audio")
        ttk.Radiobutton(yt_frame, text="Audio (mp3)", variable=self.yt_type, value="audio").pack(anchor="w")
        ttk.Radiobutton(yt_frame, text="Video (mp4)", variable=self.yt_type, value="video").pack(anchor="w")

        path_frame = ttk.Frame(yt_frame)
        path_frame.pack(fill="x", pady=5)
        ttk.Label(path_frame, text="Output Dir:").pack(side="left")
        self.yt_out = tk.StringVar(value=os.getcwd())
        ttk.Entry(path_frame, textvariable=self.yt_out).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(path_frame, text="Browse", command=lambda: self._choose_dir(self.yt_out)).pack(side="left")

        ttk.Button(yt_frame, text="Download YouTube", command=self._download_youtube).pack(pady=5)

    def _build_player_section(self):
        frame = ttk.LabelFrame(self, text="Player")
        frame.pack(fill="both", expand=True, padx=5, pady=5)

        # playlist listbox
        self.plist = tk.Listbox(frame, height=6)
        self.plist.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        self.plist.bind("<Double-Button-1>", lambda e:self._play_selected())

        ctrl = ttk.Frame(frame)
        ctrl.pack(side="left", fill="y", padx=5)
        for txt, cmd in (("►",self._play),("⏸",self._pause),("■",self._stop),
                        ("⏪15s",self._back15),("15s⏩",self._fwd15)):
            ttk.Button(ctrl, text=txt, width=6, command=cmd).pack(pady=2)

    def _build_log_section(self):
        frame = ttk.LabelFrame(self, text="Activity Log")
        frame.pack(fill="both", expand=True, padx=5, pady=5)
        self.log_txt = tk.Text(frame, height=10, wrap="word")
        self.log_txt.pack(fill="both", expand=True)

    # --- Podcast callbacks ---
    def _refresh_pod_tree(self):
        for i in self.pod_tree.get_children(): self.pod_tree.delete(i)
        for name, d in self.podcasts.items():
            self.pod_tree.insert("", "end", iid=name, values=(d["url"], d["output"]))

    def _pod_add(self):
        self._pod_dialog("Add Podcast")

    def _pod_edit(self):
        sel = self.pod_tree.selection()
        if len(sel)!=1: return messagebox.showinfo("Info","Select one.")
        name=sel[0]
        self._pod_dialog("Edit Podcast", name)

    def _pod_remove(self):
        for name in self.pod_tree.selection():
            self.config.remove_section(name)
            self.podcasts.pop(name,None)
        self._save_config(); self._refresh_pod_tree()

    def _pod_dialog(self, title, name=None):
        dlg = tk.Toplevel(self); dlg.title(title)
        ttk.Label(dlg,text="Name:").grid(row=0,column=0,sticky="w")
        nvar=tk.StringVar(value=name or "")
        ttk.Entry(dlg,textvariable=nvar).grid(row=0,column=1,sticky="we")
        ttk.Label(dlg,text="URL:").grid(row=1,column=0,sticky="w")
        uvar=tk.StringVar(value=(self.podcasts[name]["url"] if name else ""))
        ttk.Entry(dlg,textvariable=uvar).grid(row=1,column=1,sticky="we")
        ttk.Label(dlg,text="Output:").grid(row=2,column=0,sticky="w")
        ovar=tk.StringVar(value=(self.podcasts[name]["output"] if name else os.getcwd()))
        ttk.Entry(dlg,textvariable=ovar).grid(row=2,column=1,sticky="we")
        ttk.Button(dlg, text="Browse", command=lambda:self._choose_dir(ovar)).grid(row=2,column=2)
        def on_ok():
            nm, url, out = nvar.get().strip(), uvar.get().strip(), ovar.get().strip()
            if not (nm and url and out): return
            if name and name!=nm:
                self.config.remove_section(name)
                self.podcasts.pop(name)
            if not self.config.has_section(nm):
                self.config[nm]={}
            self.config[nm]["url"]=url
            self.config[nm]["output"]=out
            self.podcasts[nm]={"url":url,"output":out}
            self._save_config(); self._refresh_pod_tree()
            dlg.destroy()
        ttk.Button(dlg,text="OK",command=on_ok).grid(row=3,column=1)
        dlg.columnconfigure(1, weight=1)
        dlg.grab_set(); dlg.wait_window()

    def _save_config(self):
        with open(CONFIG_FILE,"w") as f:
            self.config.write(f)

    def _pod_update_selected(self):
        sel = self.pod_tree.selection()
        if not sel: return messagebox.showinfo("Info","Select >=1")
        tol = self.tol_var.get()*1024*1024
        threading.Thread(target=self._do_podcast_update, args=(sel,tol), daemon=True).start()

    def _do_podcast_update(self, names, tol):
        tasks=[]
        for nm in names:
            url,out=self.podcasts[nm]["url"],self.podcasts[nm]["output"]
            feed=feedparser.parse(url)
            for e in feed.entries:
                if "enclosures" not in e: continue
                for enc in e.enclosures:
                    fn=os.path.basename(enc.href.split("?")[0])
                    path=os.path.join(out,fn)
                    if os.path.exists(path) and abs(os.path.getsize(path)- (enc.length if "length" in enc else 0))<tol:
                        self._log(f"Skip {fn}")
                        continue
                    tasks.append((enc.href,out))
        for url,out in tasks:
            self._log(f"Downloading {url}…")
            os.makedirs(out,exist_ok=True)
            try:
                r=requests.get(url,stream=True,timeout=15); r.raise_for_status()
                fn=os.path.basename(url.split("?")[0])
                with open(os.path.join(out,fn),"wb") as f:
                    for chunk in r.iter_content(8192):
                        f.write(chunk)
                self._log(f"Saved {fn}")
            except Exception as e:
                self._log(f"Error: {e}")
        self._log("Podcasts update done.")

    # --- YouTube ---
    def _download_youtube(self):
        url, out, typ = self.yt_url.get().strip(), self.yt_out.get(), self.yt_type.get()
        if not url: return
        threading.Thread(target=self._do_yt, args=(url,out,typ), daemon=True).start()

    def _do_yt(self, url, out, typ):
        opts={"outtmpl":os.path.join(out,"%(title)s.%(ext)s")}
        if typ=="audio":
            opts.update({"format":"bestaudio","postprocessors":[{"key":"FFmpegExtractAudio","preferredcodec":"mp3"}]})
        with YoutubeDL(opts) as y:
            self._log(f"Starting yt-dlp for {url}")
            try:
                info=y.extract_info(url, download=True)
                fn=y.prepare_filename(info)
                self._log(f"Done: {fn}")
                # add to playlist
                if typ=="audio":
                    self._add_to_playlist(fn)
            except Exception as e:
                self._log(f"yt-dlp error: {e}")

    # --- Player & playlist ---
    def _add_to_playlist(self, path):
        title=os.path.splitext(os.path.basename(path))[0]
        self.playlist.append((title,path))
        self.plist.insert("end", title)

    def _play_selected(self):
        idx=self.plist.curselection()
        if not idx: return
        _,path=self.playlist[idx[0]]
        self._play_file(path)

    def _play_file(self, path):
        media=self.vlc_inst.media_new(path)
        self.player.set_media(media)
        self.player.play()
        self._log(f"Playing {os.path.basename(path)}")

    def _play(self): self.player.play()
    def _pause(self): self.player.pause()
    def _stop(self): self.player.stop()
    def _back15(self): self.player.set_time(max(0,self.player.get_time()-15000))
    def _fwd15(self): self.player.set_time(self.player.get_time()+15000)

    # --- Utilities ---
    def _choose_dir(self, var):
        d=filedialog.askdirectory()
        if d: var.set(d)

    def _log(self, msg):
        ts=time.strftime("%H:%M:%S")
        self.log_txt.insert("end", f"[{ts}] {msg}\n")
        self.log_txt.see("end")

    def on_close(self):
        self.player.stop()
        self.destroy()

if __name__ == "__main__":
    AllInOneDownloader().mainloop()
