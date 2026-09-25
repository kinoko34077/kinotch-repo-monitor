from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

from .config import AppConfig, ConfigStore, RepoEntry
from .devflow import DEFAULT_MANAGED_REPOSITORIES
from .discovery import discover_repositories
from .git_inspector import activity_age_seconds, inspect_repository
from .registry import merge_discovered
from .status import DisplayStatus, STATUS_COLORS, classify_status


STATUS_LABELS = {
    DisplayStatus.ACTIVE: "編集中",
    DisplayStatus.IDLE: "一時停止",
    DisplayStatus.STALE: "停止中",
    DisplayStatus.COMMITTED: "Commit済",
    DisplayStatus.CLEAN: "待機",
    DisplayStatus.ERROR: "エラー",
}


class RepoMonitorApp:
    def __init__(self, root: tk.Tk, store: ConfigStore | None = None):
        self.root = root
        self.store = store or ConfigStore()
        self.config = self.store.load()
        self.snapshots = {}
        self.cards: dict[str, tk.Frame] = {}
        self.labels: dict[str, dict[str, tk.Label]] = {}
        self.refreshing = False
        self._result_queue: queue.Queue[list] = queue.Queue()
        self._build_window()
        self._discover_and_save()
        self._render_cards()
        self.root.after(50, self._poll_results)
        self.root.after(100, self.refresh)

    def _build_window(self) -> None:
        self.root.title("KiNoTch. Repo Monitor")
        self.root.geometry("1280x760")
        self.root.minsize(980, 600)

        toolbar = tk.Frame(self.root, padx=12, pady=8)
        toolbar.pack(fill="x")
        tk.Label(toolbar, text="Repo Monitor", font=("Segoe UI", 16, "bold")).pack(side="left")
        tk.Button(toolbar, text="更新", command=self.refresh).pack(side="right", padx=4)
        tk.Button(toolbar, text="Repo追加", command=self.add_repository).pack(side="right", padx=4)
        tk.Button(toolbar, text="再検出", command=self.rediscover).pack(side="right", padx=4)

        self.canvas = tk.Canvas(self.root, highlightthickness=0)
        scrollbar = tk.Scrollbar(self.root, orient="vertical", command=self.canvas.yview)
        self.body = tk.Frame(self.canvas, padx=10, pady=10)
        self.body.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas_window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.canvas_window, width=e.width))
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.statusbar = tk.Label(self.root, text="", anchor="w", padx=10, pady=4)
        self.statusbar.pack(fill="x", side="bottom")

    def _discover_and_save(self) -> None:
        discovered = discover_repositories(self.config.scan_roots)
        self.config = merge_discovered(self.config, discovered)
        self.store.save(self.config)

    def _ordered_repos(self) -> list[RepoEntry]:
        managed = {name.lower(): i for i, name in enumerate(DEFAULT_MANAGED_REPOSITORIES)}
        return sorted(
            self.config.repositories,
            key=lambda r: (0, managed[r.name.lower()]) if r.name.lower() in managed else (1, r.name.lower()),
        )

    def _render_cards(self) -> None:
        for child in self.body.winfo_children():
            child.destroy()
        self.cards.clear()
        self.labels.clear()
        cols = max(1, self.config.columns)
        for index, repo in enumerate(self._ordered_repos()):
            row, col = divmod(index, cols)
            card = tk.Frame(self.body, width=220, height=145, bg=STATUS_COLORS[DisplayStatus.CLEAN], bd=1, relief="solid")
            card.grid(row=row, column=col, padx=7, pady=7, sticky="nsew")
            card.grid_propagate(False)
            name = tk.Label(card, text=repo.name, font=("Segoe UI", 11, "bold"), bg=card["bg"], anchor="w")
            name.place(x=10, y=9, width=198)
            state = tk.Label(card, text="読込中", font=("Segoe UI", 14, "bold"), bg=card["bg"], anchor="w")
            state.place(x=10, y=37, width=198)
            meta = tk.Label(card, text="", font=("Segoe UI", 9), bg=card["bg"], anchor="w", justify="left")
            meta.place(x=10, y=72, width=198, height=54)
            chat = tk.Label(card, text="Chat: 未登録" if not repo.chat_url else "Chat: 登録済", font=("Segoe UI", 8), bg=card["bg"], anchor="e")
            chat.place(x=10, y=123, width=198)
            self.cards[repo.name] = card
            self.labels[repo.name] = {"name": name, "state": state, "meta": meta, "chat": chat}
            for widget in (card, name, state, meta, chat):
                widget.bind("<Button-1>", lambda _e, r=repo: self.open_chat(r))
                widget.bind("<Button-3>", lambda e, r=repo: self.show_context_menu(e, r))
        for col in range(cols):
            self.body.grid_columnconfigure(col, weight=1, uniform="repo")

    def refresh(self) -> None:
        if self.refreshing:
            return
        self.refreshing = True
        repos = list(self.config.repositories)

        def worker():
            results = []
            for repo in repos:
                results.append((repo, inspect_repository(repo.path)))
            self._result_queue.put(results)

        threading.Thread(target=worker, daemon=True).start()

    def _poll_results(self) -> None:
        try:
            while True:
                results = self._result_queue.get_nowait()
                self._apply_snapshots(results)
        except queue.Empty:
            pass
        self.root.after(50, self._poll_results)

    def _apply_snapshots(self, results) -> None:
        now = time.time()
        for repo, snap in results:
            age = activity_age_seconds(snap, now)
            state = classify_status(
                snap.dirty,
                age,
                snap.ahead,
                bool(snap.error),
                self.config.active_seconds,
                self.config.stale_seconds,
            )
            self.snapshots[repo.name] = snap
            self._update_card(repo, snap, state, age)
        self.refreshing = False
        self.statusbar.config(text=f"最終更新 {time.strftime('%H:%M:%S')} / {len(results)} repos")
        self.root.after(self.config.refresh_ms, self.refresh)

    def _update_card(self, repo, snap, state, age) -> None:
        if repo.name not in self.cards:
            return
        color = STATUS_COLORS[state]
        card = self.cards[repo.name]
        card.configure(bg=color)
        for label in self.labels[repo.name].values():
            label.configure(bg=color)
        self.labels[repo.name]["state"].configure(text=STATUS_LABELS[state])
        if snap.error:
            meta = snap.error[:80]
        else:
            activity = "--" if age is None else self._format_age(age)
            sync = f"↑{snap.ahead} ↓{snap.behind}" if snap.upstream else "upstreamなし"
            meta = f"{snap.branch}  {snap.head}\n変更 {snap.changed_count} / 活動 {activity}\n{sync}"
        self.labels[repo.name]["meta"].configure(text=meta)
        self.labels[repo.name]["chat"].configure(text="Chat: 登録済" if repo.chat_url else "Chat: 未登録")

    @staticmethod
    def _format_age(seconds: float) -> str:
        if seconds < 60:
            return f"{int(seconds)}秒前"
        if seconds < 3600:
            return f"{int(seconds // 60)}分前"
        return f"{int(seconds // 3600)}時間前"

    def open_chat(self, repo: RepoEntry) -> None:
        if not repo.chat_url:
            self.set_chat_url(repo)
            return
        webbrowser.open(repo.chat_url)

    def set_chat_url(self, repo: RepoEntry) -> None:
        value = simpledialog.askstring("Chat URL", f"{repo.name} のChatGPT URL", initialvalue=repo.chat_url, parent=self.root)
        if value is None:
            return
        repo.chat_url = value.strip()
        self.store.save(self.config)
        label = self.labels.get(repo.name, {}).get("chat")
        if label is not None:
            label.configure(text="Chat: 登録済" if repo.chat_url else "Chat: 未登録")

    def show_context_menu(self, event, repo: RepoEntry) -> None:
        menu = tk.Menu(self.root, tearoff=False)
        menu.add_command(label="Chat URLを設定", command=lambda: self.set_chat_url(repo))
        menu.add_command(label="Repoフォルダを開く", command=lambda: self.open_folder(repo.path))
        menu.add_separator()
        menu.add_command(label="一覧から削除", command=lambda: self.remove_repository(repo))
        menu.tk_popup(event.x_root, event.y_root)

    def add_repository(self) -> None:
        path = filedialog.askdirectory(title="Git repositoryを選択", parent=self.root)
        if not path:
            return
        p = Path(path)
        if not (p / ".git").exists():
            messagebox.showerror("Repoではありません", ".git が見つかりません。", parent=self.root)
            return
        if not any(r.name.lower() == p.name.lower() for r in self.config.repositories):
            self.config.repositories.append(RepoEntry(p.name, str(p)))
        else:
            for repo in self.config.repositories:
                if repo.name.lower() == p.name.lower():
                    repo.path = str(p)
        self.store.save(self.config)
        self._render_cards()
        self.refresh()

    def remove_repository(self, repo: RepoEntry) -> None:
        self.config.repositories = [r for r in self.config.repositories if r.name != repo.name]
        self.store.save(self.config)
        self._render_cards()

    def rediscover(self) -> None:
        self._discover_and_save()
        self._render_cards()
        self.refresh()

    @staticmethod
    def open_folder(path: str) -> None:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
