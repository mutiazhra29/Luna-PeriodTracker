import calendar
import sqlite3
import tkinter as tk
from datetime import date, datetime, timedelta
from tkinter import filedialog, messagebox, simpledialog
from typing import Callable

from .database import SYMPTOMS, LunaDatabase
from .paths import data_directory
from .predictor import CyclePrediction, predict_cycle
from .security import hash_pin, verify_pin


THEMES = {
    "Rose Blush": {
        "bg": "#FFF7F9", "card": "#FFFFFF", "soft": "#FDE8EF",
        "primary": "#C94770", "hover": "#A9365C", "accent": "#B79CED",
        "lilac": "#EDE4FB", "peach": "#F6B58A", "text": "#4A2C3F",
        "muted": "#765C6D", "border": "#E8C6D3", "success": "#DDF3E9",
        "warning": "#FFF0DA", "period_text": "#4A1029",
    },
    "Lavender Dream": {
        "bg": "#FAF7FF", "card": "#FFFFFF", "soft": "#EEE8FA",
        "primary": "#765BB5", "hover": "#604693", "accent": "#D66E99",
        "lilac": "#EDE4FB", "peach": "#F6B58A", "text": "#3B2F52",
        "muted": "#685D7B", "border": "#D9CFED", "success": "#DDF3E9",
        "warning": "#FFF0DA", "period_text": "#30234A",
    },
    "Night Moon": {
        "bg": "#1E1726", "card": "#2A2136", "soft": "#38293F",
        "primary": "#F27BA6", "hover": "#D7618C", "accent": "#B79CED",
        "lilac": "#40344F", "peach": "#F6B58A", "text": "#F4E9F2",
        "muted": "#C5B2C6", "border": "#49364D", "success": "#304638",
        "warning": "#4C3B30", "period_text": "#FFFFFF",
    },
}

MOODS = [
    ("😊", "Senang"), ("😌", "Tenang"), ("🥰", "Penuh kasih"),
    ("🥺", "Sensitif"), ("😢", "Sedih"), ("😰", "Cemas"),
    ("😠", "Mudah marah"), ("😴", "Lelah"),
]
FLOW_LABELS = {
    "spotting": "Bercak", "light": "Ringan", "medium": "Sedang", "heavy": "Deras"
}
MONTH_NAMES = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]
WEEKDAY_NAMES = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
MEDICAL_DISCLAIMER = (
    "Luna bukan alat medis. Semua prediksi hanyalah perkiraan dan bukan metode "
    "kontrasepsi atau diagnosis. Konsultasikan ke tenaga kesehatan bila siklus "
    "sangat tidak teratur, nyeri hebat, atau haid terlambat disertai kekhawatiran lain."
)
TIPS = {
    "Menstruasi": "Beristirahat dan bergerak lembut bisa membantu tubuhmu merasa nyaman.",
    "Folikular": "Tubuhmu sedang membangun energi baru. Dengarkan ritmemu hari ini.",
    "Masa subur": "Masa subur adalah perkiraan kalender, bukan jaminan ovulasi.",
    "Luteal": "Luangkan ruang untuk jeda dan pilih hal-hal yang membuatmu nyaman.",
}


def parse_date(value: str) -> date:
    return date.fromisoformat(value.strip())


def display_date(value: date, include_year: bool = True) -> str:
    result = f"{value.day:02d} {MONTH_NAMES[value.month - 1]}"
    return f"{result} {value.year}" if include_year else result


class LunaApp:
    def __init__(self, root: tk.Tk, database: LunaDatabase):
        self.root = root
        self.db = database
        self.today = date.today()
        self.colors = THEMES.get(self.db.get_setting("theme", "Rose Blush"), THEMES["Rose Blush"])
        self.current_page = "Beranda"
        self.month = date(self.today.year, self.today.month, 1)
        self._configure_window()
        if self.db.get_setting("onboarding_complete") != "1":
            if not self._show_onboarding():
                self.root.destroy()
                return
        pin_hash = self.db.get_setting("pin_hash")
        if pin_hash and not self._unlock(pin_hash):
            self.root.destroy()
            return
        self._maybe_backup()
        self._build_shell()
        self.show_page("Beranda")

    def _configure_window(self) -> None:
        title = "Catatan" if self.db.get_setting("discreet") == "1" else "Luna — Kenali ritme tubuhmu"
        self.root.title(title)
        self.root.geometry("1120x760")
        self.root.minsize(800, 560)
        self.root.configure(bg=self.colors["bg"])
        self.root.option_add("*Font", ("Segoe UI", 12))

    def _maybe_backup(self) -> None:
        if not self.db.get_cycles():
            return
        last_backup = self.db.get_setting("last_auto_backup")
        try:
            due = not last_backup or (self.today - date.fromisoformat(last_backup)).days >= 7
        except ValueError:
            due = True
        if due:
            backup_dir = data_directory() / "backup"
            target = backup_dir / f"luna-{self.today.isoformat()}.luna"
            try:
                self.db.backup_to(target)
            except (OSError, sqlite3.Error) as error:
                messagebox.showwarning(
                    "Cadangan otomatis gagal",
                    f"Luna tidak dapat membuat cadangan mingguan: {error}",
                    parent=self.root,
                )
                return
            self.db.set_settings({"last_auto_backup": self.today.isoformat()})

    def _show_onboarding(self) -> bool:
        self.root.withdraw()
        dialog = tk.Toplevel(self.root)
        dialog.title("Selamat datang di Luna")
        dialog.configure(bg=self.colors["bg"])
        dialog.geometry("500x560")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        state: dict[str, str] = {
            "name": "", "last_start": self.today.isoformat(),
            "cycle_length": "28", "period_length": "5", "pin": "",
        }
        step = {"value": 0}
        result = {"complete": False}
        body = tk.Frame(dialog, bg=self.colors["bg"], padx=36, pady=30)
        body.pack(fill="both", expand=True)

        def render() -> None:
            for child in body.winfo_children():
                child.destroy()
            tk.Label(body, text="🌙", font=("Segoe UI Emoji", 38),
                     bg=self.colors["bg"], fg=self.colors["primary"]).pack(pady=(0, 4))
            tk.Label(body, text="Halo, aku Luna!", font=("Segoe UI", 24, "bold"),
                     bg=self.colors["bg"], fg=self.colors["text"]).pack()
            subtitles = [
                "Teman pencatat siklusmu yang privat.",
                "Kapan hari pertama haid terakhirmu?",
                "Atur siklusmu. Semuanya bisa diubah nanti.",
            ]
            tk.Label(body, text=subtitles[step["value"]], wraplength=390,
                     bg=self.colors["bg"], fg=self.colors["muted"]).pack(pady=(8, 24))
            if step["value"] == 0:
                tk.Label(body, text="Nama panggilan", bg=self.colors["bg"],
                         fg=self.colors["text"], anchor="w").pack(fill="x")
                field = self._entry(body, state["name"])
                field.pack(fill="x", pady=(6, 16))
                field.focus_set()

                def sync_name(_event: object = None) -> None:
                    state["name"] = field.get()

                field.bind("<KeyRelease>", sync_name)
            elif step["value"] == 1:
                tk.Label(body, text="Tanggal mulai terakhir (YYYY-MM-DD)",
                         bg=self.colors["bg"], fg=self.colors["text"], anchor="w").pack(fill="x")
                field = self._entry(body, state["last_start"])
                field.pack(fill="x", pady=(6, 12))
                tk.Label(body, text="Kamu bisa mengetik tanggal langsung, misalnya 2026-10-19.",
                         bg=self.colors["bg"], fg=self.colors["muted"], wraplength=390,
                         justify="left").pack(anchor="w")

                def sync_date(_event: object = None) -> None:
                    state["last_start"] = field.get()

                field.bind("<KeyRelease>", sync_date)
            else:
                for label, key, default, low, high in (
                    ("Panjang siklus rata-rata (hari)", "cycle_length", "28", 15, 60),
                    ("Durasi haid (hari)", "period_length", "5", 1, 15),
                ):
                    row = tk.Frame(body, bg=self.colors["bg"])
                    row.pack(fill="x", pady=7)
                    tk.Label(row, text=label, bg=self.colors["bg"], fg=self.colors["text"]).pack(side="left")
                    value = tk.IntVar(value=int(state[key] or default))
                    tk.Spinbox(row, from_=low, to=high, textvariable=value, width=5,
                               font=("Segoe UI", 12), relief="flat",
                               bg=self.colors["card"], fg=self.colors["text"],
                               buttonbackground=self.colors["soft"]).pack(side="right", ipady=6)

                    def sync_value(_event: object = None, target: str = key,
                                   variable: tk.IntVar = value) -> None:
                        state[target] = str(variable.get())

                    value.trace_add("write", sync_value)
                tk.Label(body, text="PIN 4 digit (opsional)", bg=self.colors["bg"],
                         fg=self.colors["text"], anchor="w").pack(fill="x", pady=(16, 5))
                pin_field = self._entry(body, "", show="•")
                pin_field.pack(fill="x")
                pin_field.bind("<KeyRelease>", lambda _e: state.update(pin=pin_field.get()))
                tk.Label(body, text="Prediksi siklus bukan alat kontrasepsi atau diagnosis.",
                         bg=self.colors["bg"], fg=self.colors["muted"], wraplength=390,
                         justify="left").pack(anchor="w", pady=(8, 0))

            footer = tk.Frame(body, bg=self.colors["bg"])
            footer.pack(side="bottom", fill="x", pady=(20, 0))
            tk.Label(footer, text=f"{'●' if step['value'] >= 0 else '○'}  "
                     f"{'●' if step['value'] >= 1 else '○'}  "
                     f"{'●' if step['value'] >= 2 else '○'}",
                     bg=self.colors["bg"], fg=self.colors["primary"]).pack(side="left")
            if step["value"] > 0:
                self._button(footer, "← Kembali", lambda: change_step(-1)).pack(side="left", padx=8)
            label = "Mulai 🌸" if step["value"] == 2 else "Lanjut →"
            self._button(footer, label, lambda: change_step(1), primary=True).pack(side="right")

        def change_step(delta: int) -> None:
            if step["value"] == 0:
                field = next(
                    (widget for widget in body.winfo_children() if isinstance(widget, tk.Entry)),
                    None,
                )
                state["name"] = field.get().strip() if field else ""
                if not state["name"]:
                    messagebox.showwarning("Nama panggilan", "Isi nama panggilanmu dulu ya.", parent=dialog)
                    return
            if step["value"] == 1:
                field = next(
                    (widget for widget in body.winfo_children() if isinstance(widget, tk.Entry)),
                    None,
                )
                if field:
                    state["last_start"] = field.get().strip()
                try:
                    selected = parse_date(state["last_start"])
                    if selected > self.today:
                        raise ValueError
                except ValueError:
                    messagebox.showerror("Tanggal tidak valid",
                                         "Masukkan tanggal yang valid dan tidak di masa depan.", parent=dialog)
                    return
            if delta < 0:
                step["value"] -= 1
                render()
                return
            if step["value"] < 2:
                step["value"] += 1
                render()
                return
            try:
                cycle_length = int(state["cycle_length"] or "28")
                period_length = int(state["period_length"] or "5")
                if not 15 <= cycle_length <= 60 or not 1 <= period_length <= 15:
                    raise ValueError
                pin_field = next(
                    (widget for widget in body.winfo_children() if isinstance(widget, tk.Entry)),
                    None,
                )
                pin = pin_field.get().strip() if pin_field else state["pin"]
                if pin and len(pin) != 4 or pin and not pin.isdigit():
                    messagebox.showerror("PIN tidak valid", "PIN harus terdiri dari 4 angka.", parent=dialog)
                    return
                started = parse_date(state["last_start"])
                cycle_end = (
                    None if (self.today - started).days < period_length
                    else started + timedelta(days=period_length - 1)
                )
                self.db.add_cycle(started, cycle_end)
                settings = {
                    "name": state["name"].strip(),
                    "default_cycle": str(cycle_length),
                    "period_length": str(period_length),
                    "theme": self.db.get_setting("theme", "Rose Blush"),
                    "onboarding_complete": "1",
                }
                if pin:
                    settings["pin_hash"] = hash_pin(pin)
                self.db.set_settings(settings)
            except (ValueError, sqlite3.IntegrityError) as error:
                messagebox.showerror("Data tidak valid", str(error), parent=dialog)
                return
            result["complete"] = True
            dialog.destroy()

        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        render()
        self.root.wait_window(dialog)
        if result["complete"]:
            self.root.deiconify()
        return result["complete"]

    def _unlock(self, pin_hash: str) -> bool:
        self.root.withdraw()
        dialog = tk.Toplevel(self.root)
        dialog.title("Catatan" if self.db.get_setting("discreet") == "1" else "Luna — Buka kunci")
        dialog.configure(bg=self.colors["bg"])
        dialog.geometry("380x330")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        unlocked = {"value": False}
        discreet = self.db.get_setting("discreet") == "1"
        if not discreet:
            tk.Label(dialog, text="🌙", font=("Segoe UI Emoji", 38), bg=self.colors["bg"],
                     fg=self.colors["primary"]).pack(pady=(28, 4))
        tk.Label(dialog, text="Masukkan PIN" if discreet else "Masukkan PIN Luna",
                 font=("Segoe UI", 18, "bold"),
                 bg=self.colors["bg"], fg=self.colors["text"]).pack()
        field = self._entry(dialog, "", show="•", justify="center")
        field.pack(padx=48, fill="x", pady=18)
        error = tk.Label(dialog, text="", bg=self.colors["bg"], fg=self.colors["primary"])
        error.pack()

        def check(_event: object = None) -> None:
            if verify_pin(field.get(), pin_hash):
                unlocked["value"] = True
                dialog.destroy()
            else:
                error.configure(text="PIN belum cocok. Coba lagi ya.")
                field.delete(0, "end")

        self._button(dialog, "Buka Luna", check, primary=True).pack(pady=8)
        field.bind("<Return>", check)
        field.focus_set()
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        self.root.wait_window(dialog)
        if unlocked["value"]:
            self.root.deiconify()
        return unlocked["value"]

    def _build_shell(self) -> None:
        for child in self.root.winfo_children():
            child.destroy()
        self.shell = tk.Frame(self.root, bg=self.colors["bg"])
        self.shell.pack(fill="both", expand=True)
        self.sidebar = tk.Frame(self.shell, bg=self.colors["card"], width=220,
                                highlightthickness=1, highlightbackground=self.colors["border"])
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        self.brand = tk.Label(self.sidebar, text="🌙  Luna", font=("Segoe UI", 20, "bold"),
                              bg=self.colors["card"], fg=self.colors["text"], anchor="w")
        self.brand.pack(fill="x", padx=20, pady=(26, 30))
        self.nav_buttons: dict[str, tk.Button] = {}
        self.nav_icons: dict[str, str] = {}
        nav_items = [("Beranda", "⌂"), ("Kalender", "▦"), ("Catatan", "✎"),
                     ("Statistik", "▥"), ("Pengaturan", "⚙")]
        for label, icon in nav_items:
            button = tk.Button(
                self.sidebar, text=f"  {icon}   {label}", anchor="w",
                command=lambda page=label: self.show_page(page),
                bd=0, padx=14, pady=12, font=("Segoe UI", 12),
                bg=self.colors["card"], fg=self.colors["muted"],
                activebackground=self.colors["soft"], activeforeground=self.colors["text"],
                cursor="hand2",
            )
            button.pack(fill="x", padx=10, pady=3)
            self.nav_buttons[label] = button
            self.nav_icons[label] = icon
        tk.Label(self.sidebar, text="Offline • Data tersimpan di perangkat ini",
                 wraplength=175, justify="left", font=("Segoe UI", 12),
                 bg=self.colors["card"], fg=self.colors["muted"]).pack(
                     side="bottom", fill="x", padx=18, pady=20)
        self.content = tk.Frame(self.shell, bg=self.colors["bg"])
        self.content.pack(side="left", fill="both", expand=True)
        self.root.bind("<Configure>", self._resize_sidebar)

    def _resize_sidebar(self, _event: object = None) -> None:
        if not hasattr(self, "sidebar") or not self.sidebar.winfo_exists():
            return
        compact = self.root.winfo_width() < 900
        self.sidebar.configure(width=72 if compact else 220)
        self.brand.configure(text="🌙" if compact else "🌙  Luna", anchor="center" if compact else "w")
        for label, button in self.nav_buttons.items():
            icon = self.nav_icons[label]
            button.configure(text=f"{icon}" if compact else f"  {icon}   {label}",
                             anchor="center" if compact else "w")

    def _button(self, parent: tk.Widget, text: str, command: Callable[[], None],
                primary: bool = False, **kwargs: object) -> tk.Button:
        background = self.colors["primary"] if primary else self.colors["soft"]
        foreground = "#FFFFFF" if primary else self.colors["text"]
        return tk.Button(
            parent, text=text, command=command, bd=0, padx=16, pady=10,
            font=("Segoe UI", 12, "bold" if primary else "normal"),
            bg=background, fg=foreground,
            activebackground=self.colors["hover"] if primary else self.colors["border"],
            activeforeground="#FFFFFF" if primary else self.colors["text"],
            disabledforeground=self.colors["muted"], cursor="hand2",
            **kwargs,
        )

    def _entry(self, parent: tk.Widget, value: str = "", **kwargs: object) -> tk.Entry:
        field = tk.Entry(
            parent, bd=0, relief="flat", font=("Segoe UI", 12),
            bg=self.colors["card"], fg=self.colors["text"],
            insertbackground=self.colors["text"], highlightthickness=1,
            highlightbackground=self.colors["border"], highlightcolor=self.colors["primary"],
            **kwargs,
        )
        field.insert(0, value)
        return field

    def _card(self, parent: tk.Widget, padx: int = 20, pady: int = 18) -> tk.Frame:
        frame = tk.Frame(
            parent, bg=self.colors["card"], padx=padx, pady=pady,
            highlightthickness=1, highlightbackground=self.colors["border"],
        )
        return frame

    def _page_header(self, parent: tk.Widget, title: str, subtitle: str = "") -> None:
        tk.Label(parent, text=title, font=("Segoe UI", 23, "bold"),
                 bg=self.colors["bg"], fg=self.colors["text"], anchor="w").pack(fill="x")
        if subtitle:
            tk.Label(parent, text=subtitle, font=("Segoe UI", 12),
                     bg=self.colors["bg"], fg=self.colors["muted"],
                     anchor="w", justify="left", wraplength=820).pack(fill="x", pady=(3, 14))

    def _page_frame(self) -> tk.Frame:
        for child in self.content.winfo_children():
            child.destroy()
        canvas = tk.Canvas(self.content, bg=self.colors["bg"], highlightthickness=0)
        scrollbar = tk.Scrollbar(self.content, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        frame = tk.Frame(canvas, bg=self.colors["bg"], padx=28, pady=24)
        window = canvas.create_window((0, 0), window=frame, anchor="nw")
        frame.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        canvas.bind("<MouseWheel>", lambda event: canvas.yview_scroll(-int(event.delta / 120), "units"))
        return frame

    def show_page(self, page: str) -> None:
        self.current_page = page
        for label, button in self.nav_buttons.items():
            active = label == page
            button.configure(
                bg=self.colors["soft"] if active else self.colors["card"],
                fg=self.colors["primary"] if active else self.colors["muted"],
            )
        if page == "Beranda":
            self._dashboard()
        elif page == "Kalender":
            self._calendar_page()
        elif page == "Catatan":
            self._notes_page()
        elif page == "Statistik":
            self._statistics_page()
        else:
            self._settings_page()

    def _prediction(self) -> CyclePrediction | None:
        starts = [date.fromisoformat(item["start_date"]) for item in self.db.get_cycles()]
        return predict_cycle(
            starts, self.today, int(self.db.get_setting("default_cycle", "28")),
            int(self.db.get_setting("period_length", "5")),
        )

    def _dashboard(self) -> None:
        page = self._page_frame()
        hour = datetime.now().hour
        greeting = "Selamat pagi" if hour < 11 else "Selamat siang" if hour < 15 else "Selamat sore" if hour < 19 else "Selamat malam"
        name = self.db.get_setting("name", "teman")
        self._page_header(page, f"{greeting}, {name} 🌸", "Kenali ritme tubuhmu, dengan tenang.")
        prediction = self._prediction()
        row = tk.Frame(page, bg=self.colors["bg"])
        row.pack(fill="x", pady=(4, 16))
        ring_card = self._card(row, 20, 18)
        ring_card.pack(side="left", fill="both", expand=True, padx=(0, 10))
        self._draw_cycle_ring(ring_card, prediction)
        info = tk.Frame(row, bg=self.colors["bg"])
        info.pack(side="left", fill="both", expand=True, padx=(10, 0))
        if prediction:
            until = (prediction.next_period - self.today).days
            next_text = "Perkiraan hari ini" if until == 0 else (
                "Perkiraan terlewat" if until < 0 else f"Dalam {until} hari"
            )
            self._info_card(info, "🩸  Haid berikutnya · perkiraan", next_text)
            self._info_card(info, "✦  Ovulasi · perkiraan", display_date(prediction.ovulation))
            fertile = f"{display_date(prediction.fertile_start, False)} – {display_date(prediction.fertile_end, False)}"
            self._info_card(info, "☾  Masa subur · perkiraan", fertile)
            if prediction.irregular:
                tk.Label(info, text=f"Siklus bervariasi; prediksi dapat bergeser ±{prediction.uncertainty_days} hari.",
                         bg=self.colors["warning"], fg=self.colors["text"], wraplength=350,
                         justify="left", padx=12, pady=9).pack(fill="x", pady=(0, 8))
        else:
            card = self._card(info)
            card.pack(fill="both", expand=True)
            tk.Label(card, text="Mulai dengan mencatat hari pertama haidmu.",
                     bg=self.colors["card"], fg=self.colors["text"], wraplength=320,
                     justify="left").pack(anchor="w", pady=(10, 14))
            self._button(card, "Catat hari ini", lambda: self.open_log_editor(self.today),
                         primary=True).pack(anchor="w")
        actions = tk.Frame(page, bg=self.colors["bg"])
        actions.pack(fill="x", pady=4)
        cycles = self.db.get_cycles()
        active = bool(cycles and not cycles[-1]["end_date"])
        start_button = self._button(
            actions, "🩸  Haid dimulai hari ini",
            lambda: self._start_period(), primary=True,
        )
        start_button.pack(side="left", padx=(0, 10))
        if active:
            self._button(actions, "Haid selesai", self._finish_period).pack(side="left")
        tip = self._card(page, 16, 13)
        tip.pack(fill="x", pady=(15, 10))
        phase = prediction.phase if prediction else "Folikular"
        tk.Label(tip, text=f"💡  {TIPS[phase]}", bg=self.colors["card"],
                 fg=self.colors["text"], justify="left", wraplength=790).pack(anchor="w")
        self._disclaimer(page)

    def _draw_cycle_ring(self, parent: tk.Widget, prediction: CyclePrediction | None) -> None:
        tk.Label(parent, text="Siklusmu hari ini", font=("Segoe UI", 12),
                 bg=self.colors["card"], fg=self.colors["muted"]).pack(anchor="w")
        canvas = tk.Canvas(parent, width=220, height=190, bg=self.colors["card"],
                           highlightthickness=0)
        canvas.pack(fill="both", expand=True, pady=(0, 4))
        if prediction is None:
            day, phase, length, color, progress = "—", "Belum ada data", 28, self.colors["primary"], 0.25
        else:
            day, phase, length = str(prediction.cycle_day), prediction.phase, prediction.cycle_length
            color = self.colors["primary"] if phase == "Menstruasi" else self.colors["accent"] if phase == "Masa subur" else self.colors["peach"]
            progress = min(1, prediction.cycle_day / max(1, length))
        canvas.create_oval(39, 10, 181, 152, outline=self.colors["soft"], width=15)
        canvas.create_arc(39, 10, 181, 152, start=90, extent=-360 * progress,
                          style="arc", outline=color, width=15)
        canvas.create_text(110, 70, text=day, fill=self.colors["text"],
                           font=("Segoe UI", 34, "bold"))
        canvas.create_text(110, 104, text="hari ke", fill=self.colors["muted"],
                           font=("Segoe UI", 12))
        canvas.create_text(110, 176, text=phase, fill=self.colors["text"],
                           font=("Segoe UI", 12, "bold"))

    def _info_card(self, parent: tk.Widget, title: str, value: str) -> None:
        card = self._card(parent, 16, 11)
        card.pack(fill="x", pady=(0, 8), expand=True)
        tk.Label(card, text=title, bg=self.colors["card"], fg=self.colors["muted"],
                 font=("Segoe UI", 12), anchor="w").pack(fill="x")
        tk.Label(card, text=value, bg=self.colors["card"], fg=self.colors["text"],
                 font=("Segoe UI", 15, "bold"), anchor="w").pack(fill="x", pady=(4, 0))

    def _disclaimer(self, parent: tk.Widget) -> None:
        tk.Label(parent, text=MEDICAL_DISCLAIMER, bg=self.colors["bg"],
                 fg=self.colors["muted"], font=("Segoe UI", 12),
                 wraplength=820, justify="left").pack(anchor="w", pady=(6, 0))

    def _start_period(self) -> None:
        if not messagebox.askyesno("Catat haid", "Tandai hari ini sebagai hari pertama haid?", parent=self.root):
            return
        cycles = self.db.get_cycles()
        if cycles and not cycles[-1]["end_date"]:
            messagebox.showinfo(
                "Haid sedang tercatat",
                "Siklus saat ini masih berlangsung. Tandai haid selesai terlebih dahulu.",
                parent=self.root,
            )
            return
        if any(item["start_date"] == self.today.isoformat() for item in cycles):
            messagebox.showinfo("Sudah tercatat", "Haid hari ini sudah tercatat.", parent=self.root)
            return
        self.db.add_cycle(self.today)
        existing = self.db.get_log(self.today) or {}
        self.db.save_log({**existing, "log_date": self.today, "is_period": True,
                          "flow": existing.get("flow") or "medium",
                          "symptoms": existing.get("symptoms", [])})
        self.show_page(self.current_page)

    def _finish_period(self) -> None:
        if not messagebox.askyesno("Haid selesai", "Tandai haid selesai hari ini?", parent=self.root):
            return
        self.db.finish_active_cycle(self.today)
        existing = self.db.get_log(self.today) or {}
        self.db.save_log({**existing, "log_date": self.today, "is_period": True,
                          "symptoms": existing.get("symptoms", [])})
        self.show_page(self.current_page)

    def _calendar_page(self) -> None:
        page = self._page_frame()
        self._page_header(page, "Kalender", "Lihat catatan dan perkiraan siklusmu.")
        controls = tk.Frame(page, bg=self.colors["bg"])
        controls.pack(fill="x", pady=(0, 10))
        month_name = MONTH_NAMES[self.month.month - 1]
        tk.Label(controls, text=f"{month_name} {self.month.year}", font=("Segoe UI", 17, "bold"),
                 bg=self.colors["bg"], fg=self.colors["text"]).pack(side="left", padx=12)
        self._button(controls, "‹", lambda: self._shift_month(-1)).pack(side="left")
        self._button(controls, "›", lambda: self._shift_month(1)).pack(side="left", padx=6)
        self._button(controls, "Hari ini", self._go_today).pack(side="right")
        grid = tk.Frame(page, bg=self.colors["bg"])
        grid.pack(fill="both", expand=True)
        weekday_names = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]
        first_weekday = int(self.db.get_setting("first_weekday", "0"))
        weekdays = weekday_names[first_weekday:] + weekday_names[:first_weekday]
        for column, label in enumerate(weekdays):
            grid.grid_columnconfigure(column, weight=1, uniform="calendar")
            tk.Label(grid, text=label, bg=self.colors["bg"], fg=self.colors["muted"],
                     font=("Segoe UI", 12, "bold")).grid(row=0, column=column, pady=(0, 7))
        for row in range(1, 7):
            grid.grid_rowconfigure(row, weight=1, uniform="calendar")
        prediction = self._prediction()
        logs = {date.fromisoformat(item["log_date"]): item for item in self.db.get_logs()}
        period_dates = {day for day, item in logs.items() if item["is_period"]}
        for cycle in self.db.get_cycles():
            start = date.fromisoformat(cycle["start_date"])
            default_end = start + timedelta(
                days=int(self.db.get_setting("period_length", "5")) - 1
            )
            end = date.fromisoformat(cycle["end_date"]) if cycle["end_date"] else min(self.today, default_end)
            if end < start:
                continue
            period_dates.update(start + timedelta(days=offset)
                                for offset in range(min((end - start).days + 1, 31)))
        for logged_day, log in logs.items():
            if log["is_period"]:
                period_dates.add(logged_day)
            else:
                period_dates.discard(logged_day)
        predicted_dates: set[date] = set()
        fertile_dates: set[date] = set()
        if prediction:
            period_len = int(self.db.get_setting("period_length", "5"))
            predicted_dates = {
                prediction.next_period + timedelta(days=i) for i in range(period_len)
            }
            fertile_dates = {
                prediction.fertile_start + timedelta(days=i) for i in range(7)
            }
        days = calendar.Calendar(firstweekday=first_weekday).monthdatescalendar(
            self.month.year, self.month.month
        )
        days = [week for week in days]
        while len(days) < 6:
            last_day = days[-1][-1]
            days.append([last_day + timedelta(days=i) for i in range(1, 8)])
        for row, week in enumerate(days[:6], start=1):
            for col, day in enumerate(week):
                in_month = day.month == self.month.month
                background = self.colors["card"]
                foreground = self.colors["text"] if in_month else self.colors["muted"]
                if day in fertile_dates:
                    background = self.colors["lilac"]
                if day in predicted_dates:
                    background = self.colors["soft"]
                if day == (prediction.ovulation if prediction else None):
                    background = self.colors["peach"]
                if day in period_dates:
                    background, foreground = self.colors["primary"], self.colors["period_text"]
                label = str(day.day)
                if prediction and day == prediction.ovulation:
                    label += " ✦"
                cell = tk.Button(
                    grid, text=label, command=lambda selected=day: self.open_log_editor(selected),
                    bd=0, relief="flat", bg=background, fg=foreground,
                    activebackground=self.colors["border"], activeforeground=self.colors["text"],
                    font=("Segoe UI", 12), cursor="hand2" if in_month else "arrow",
                    state="normal" if in_month and day <= self.today else "disabled",
                    disabledforeground=self.colors["muted"],
                    highlightthickness=2 if day == self.today or day in predicted_dates else 0,
                    highlightbackground=self.colors["primary"] if day == self.today else self.colors["accent"],
                    highlightcolor=self.colors["primary"],
                )
                cell.grid(row=row, column=col, sticky="nsew", padx=3, pady=3)
        legend = tk.Frame(page, bg=self.colors["bg"])
        legend.pack(fill="x", pady=(12, 0))
        for label, color in (
            ("Haid", self.colors["primary"]), ("Perkiraan haid", self.colors["soft"]),
            ("Masa subur", self.colors["lilac"]), ("Ovulasi ✦", self.colors["peach"]),
            ("Hari ini", self.colors["card"]),
        ):
            item = tk.Frame(legend, bg=self.colors["bg"])
            item.pack(side="left", padx=(0, 13))
            tk.Label(item, text="●", bg=self.colors["bg"], fg=color,
                     font=("Segoe UI", 12, "bold")).pack(side="left")
            tk.Label(item, text=label, bg=self.colors["bg"], fg=self.colors["text"],
                     font=("Segoe UI", 12)).pack(side="left", padx=(3, 0))

    def _shift_month(self, offset: int) -> None:
        month_index = self.month.month - 1 + offset
        self.month = date(self.month.year + month_index // 12, month_index % 12 + 1, 1)
        self._calendar_page()

    def _go_today(self) -> None:
        self.month = date(self.today.year, self.today.month, 1)
        self._calendar_page()

    def _notes_page(self) -> None:
        page = self._page_frame()
        self._page_header(page, "Catatan harian", "Catat aliran, gejala, suasana hati, dan hal yang ingin kamu ingat.")
        top = tk.Frame(page, bg=self.colors["bg"])
        top.pack(fill="x", pady=(0, 12))
        self._button(top, "＋  Catat hari ini", lambda: self.open_log_editor(self.today),
                     primary=True).pack(side="left")
        self._button(top, "Pilih tanggal…", self._choose_note_date).pack(side="left", padx=8)
        logs = self.db.get_logs(30)
        if not logs:
            card = self._card(page)
            card.pack(fill="x", pady=8)
            tk.Label(card, text="🌷  Belum ada catatan. Yuk, mulai hari ini.",
                     bg=self.colors["card"], fg=self.colors["text"],
                     font=("Segoe UI", 12)).pack(anchor="w")
            return
        for log in logs:
            day = date.fromisoformat(log["log_date"])
            card = self._card(page, 14, 11)
            card.pack(fill="x", pady=4)
            summary = " • ".join(SYMPTOMS[item] for item in log["symptoms"])
            pieces = [f"{WEEKDAY_NAMES[day.weekday()]}, {day.day} "
                      f"{MONTH_NAMES[day.month - 1]} {day.year}"]
            if log["is_period"]:
                pieces.append("Haid" + (f" · {FLOW_LABELS.get(log['flow'], '')}" if log["flow"] else ""))
            if log["mood"]:
                pieces.append(log["mood"])
            if summary:
                pieces.append(summary)
            if log["note"]:
                pieces.append(log["note"])
            tk.Label(card, text="  ·  ".join(pieces), bg=self.colors["card"],
                     fg=self.colors["text"], anchor="w", justify="left",
                     wraplength=670).pack(side="left", fill="x", expand=True)
            self._button(card, "Buka", lambda selected=day: self.open_log_editor(selected)).pack(side="right")

    def _choose_note_date(self) -> None:
        value = simpledialog.askstring(
            "Pilih tanggal", "Masukkan tanggal (YYYY-MM-DD):",
            initialvalue=self.today.isoformat(), parent=self.root,
        )
        if value:
            try:
                self.open_log_editor(parse_date(value))
            except ValueError:
                messagebox.showerror("Tanggal tidak valid", "Gunakan format YYYY-MM-DD.", parent=self.root)

    def open_log_editor(self, selected: date) -> None:
        if selected > self.today:
            messagebox.showinfo("Tanggal belum tiba", "Catatan hanya bisa dibuat untuk hari ini atau sebelumnya.",
                                parent=self.root)
            return
        existing = self.db.get_log(selected) or {}
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Catatan — {display_date(selected)}")
        dialog.configure(bg=self.colors["bg"])
        dialog.geometry("600x700")
        dialog.minsize(500, 560)
        dialog.transient(self.root)
        dialog.grab_set()
        outer = tk.Frame(dialog, bg=self.colors["bg"], padx=24, pady=18)
        outer.pack(fill="both", expand=True)
        pending_autosave: str | None = None

        def schedule_autosave(*_args: object) -> None:
            nonlocal pending_autosave
            if pending_autosave:
                dialog.after_cancel(pending_autosave)
            save_status.configure(text="Menyimpan perubahan…")
            pending_autosave = dialog.after(700, auto_save)

        def auto_save() -> None:
            nonlocal pending_autosave
            pending_autosave = None
            save(quiet=True)

        tk.Label(outer, text=f"{WEEKDAY_NAMES[selected.weekday()]}, {selected.day} "
                 f"{MONTH_NAMES[selected.month - 1]} {selected.year}",
                 font=("Segoe UI", 18, "bold"), bg=self.colors["bg"],
                 fg=self.colors["text"]).pack(anchor="w", pady=(0, 14))
        is_period = tk.BooleanVar(value=bool(existing.get("is_period")))
        tk.Checkbutton(outer, text="Haid hari ini", variable=is_period,
                       bg=self.colors["bg"], fg=self.colors["text"],
                       activebackground=self.colors["bg"], selectcolor=self.colors["soft"],
                       font=("Segoe UI", 12), command=schedule_autosave).pack(anchor="w")
        tk.Label(outer, text="Intensitas aliran", bg=self.colors["bg"],
                 fg=self.colors["muted"]).pack(anchor="w", pady=(10, 2))
        flow = tk.StringVar(value=existing.get("flow") or "")
        flow_row = tk.Frame(outer, bg=self.colors["bg"])
        flow_row.pack(fill="x")
        for code, label in FLOW_LABELS.items():
            tk.Radiobutton(flow_row, text=label, value=code, variable=flow,
                           bg=self.colors["bg"], fg=self.colors["text"],
                           activebackground=self.colors["bg"], selectcolor=self.colors["soft"],
                           font=("Segoe UI", 12), command=schedule_autosave).pack(
                               side="left", padx=(0, 8)
                           )
        tk.Label(outer, text="Gejala", bg=self.colors["bg"], fg=self.colors["muted"]).pack(anchor="w", pady=(12, 3))
        symptom_vars: dict[str, tk.BooleanVar] = {}
        symptom_grid = tk.Frame(outer, bg=self.colors["bg"])
        symptom_grid.pack(fill="x")
        for index, (code, label) in enumerate(SYMPTOMS.items()):
            variable = tk.BooleanVar(value=code in existing.get("symptoms", []))
            symptom_vars[code] = variable
            tk.Checkbutton(
                symptom_grid, text=label, variable=variable, bg=self.colors["bg"],
                fg=self.colors["text"], activebackground=self.colors["bg"],
                selectcolor=self.colors["soft"], font=("Segoe UI", 12),
                command=schedule_autosave,
            ).grid(row=index // 3, column=index % 3, sticky="w", padx=(0, 8), pady=2)
        tk.Label(outer, text="Suasana hati", bg=self.colors["bg"],
                 fg=self.colors["muted"]).pack(anchor="w", pady=(12, 3))
        mood = tk.StringVar(value=existing.get("mood") or "")
        mood_row = tk.Frame(outer, bg=self.colors["bg"])
        mood_row.pack(fill="x")
        for emoji, label in MOODS:
            tk.Radiobutton(mood_row, text=emoji, value=emoji, variable=mood,
                           indicatoron=False, width=3, bd=0, pady=6,
                           bg=self.colors["card"], fg=self.colors["text"],
                           selectcolor=self.colors["soft"], activebackground=self.colors["soft"],
                           font=("Segoe UI Emoji", 13), cursor="hand2",
                           command=schedule_autosave).pack(side="left", padx=(0, 5))
        tk.Label(outer, text="Catatan (maks. 500 karakter)", bg=self.colors["bg"],
                 fg=self.colors["muted"]).pack(anchor="w", pady=(12, 3))
        note = tk.Text(outer, height=4, wrap="word", font=("Segoe UI", 12),
                       bd=0, padx=10, pady=8, bg=self.colors["card"],
                       fg=self.colors["text"], insertbackground=self.colors["text"],
                       highlightthickness=1, highlightbackground=self.colors["border"])
        note.pack(fill="x")
        note.insert("1.0", existing.get("note", ""))
        note.bind("<KeyRelease>", schedule_autosave)
        metrics = tk.Frame(outer, bg=self.colors["bg"])
        metrics.pack(fill="x", pady=(12, 2))
        metric_fields: dict[str, tk.Entry] = {}
        for label, key in (("Suhu °C", "temperature"), ("Berat kg", "weight"), ("Air (gelas)", "water")):
            group = tk.Frame(metrics, bg=self.colors["bg"])
            group.pack(side="left", fill="x", expand=True, padx=(0, 8))
            tk.Label(group, text=label, bg=self.colors["bg"], fg=self.colors["muted"]).pack(anchor="w")
            field = self._entry(group, str(existing.get(key) or ""))
            field.pack(fill="x", pady=(4, 0), ipady=6)
            field.bind("<KeyRelease>", schedule_autosave)
            metric_fields[key] = field
        buttons = tk.Frame(outer, bg=self.colors["bg"])
        buttons.pack(side="bottom", fill="x", pady=(14, 0))
        save_status = tk.Label(outer, text="Perubahan disimpan otomatis.",
                               bg=self.colors["bg"], fg=self.colors["muted"],
                               anchor="w")
        save_status.pack(side="bottom", fill="x", pady=(6, 0))

        def save(quiet: bool = False) -> bool:
            text = note.get("1.0", "end-1c")
            if len(text) > 500:
                message = "Catatan maksimal 500 karakter."
                if quiet:
                    save_status.configure(text=message)
                else:
                    messagebox.showerror("Catatan terlalu panjang", message, parent=dialog)
                return False
            try:
                metrics_value: dict[str, int | float | None] = {}
                for key, field in metric_fields.items():
                    raw = field.get().strip()
                    metrics_value[key] = float(raw) if key != "water" and raw else (
                        int(raw) if raw else None
                    )
                    if key == "water" and raw and int(raw) < 0:
                        raise ValueError("Jumlah air tidak boleh negatif.")
                cycles = self.db.get_cycles()
                period_length = int(self.db.get_setting("period_length", "5"))
                cycle_covers_date = any(
                    date.fromisoformat(cycle["start_date"]) <= selected <= (
                        date.fromisoformat(cycle["end_date"])
                        if cycle["end_date"] else min(
                            self.today,
                            date.fromisoformat(cycle["start_date"])
                            + timedelta(days=period_length - 1),
                        )
                    )
                    for cycle in cycles
                )
                preceding_period = any(
                    log["is_period"] and log["log_date"] != selected.isoformat()
                    and 0 <= (selected - date.fromisoformat(log["log_date"])).days <= 7
                    for log in self.db.get_logs()
                )
                self.db.save_log({
                    "log_date": selected,
                    "is_period": is_period.get(),
                    "flow": flow.get() if is_period.get() else None,
                    "mood": mood.get(),
                    "note": text,
                    "symptoms": [code for code, variable in symptom_vars.items() if variable.get()],
                    **metrics_value,
                })
                if existing.get("is_period") and not is_period.get():
                    self.db.delete_cycle(selected)
                if is_period.get() and not cycle_covers_date and not preceding_period:
                    self.db.add_cycle(selected)
            except (ValueError, sqlite3.Error, OSError) as error:
                if quiet:
                    save_status.configure(text=f"Belum tersimpan: {error}")
                else:
                    messagebox.showerror("Data tidak valid", str(error), parent=dialog)
                return False
            saved_log = self.db.get_log(selected)
            if saved_log:
                existing.update(saved_log)
            if quiet:
                save_status.configure(text="Tersimpan otomatis.")
            else:
                nonlocal pending_autosave
                if pending_autosave:
                    dialog.after_cancel(pending_autosave)
                    pending_autosave = None
                dialog.destroy()
                self.show_page(self.current_page)
            return True

        self._button(buttons, "Hapus catatan", lambda: delete(), **{}).pack(side="left")
        self._button(buttons, "Simpan catatan", save, primary=True).pack(side="right")

        def delete() -> None:
            current = self.db.get_log(selected)
            if current and messagebox.askyesno("Hapus catatan", "Hapus catatan untuk tanggal ini?", parent=dialog):
                if pending_autosave:
                    dialog.after_cancel(pending_autosave)
                if current.get("is_period"):
                    self.db.delete_cycle(selected)
                self.db.delete_log(selected)
                dialog.destroy()
                self.show_page(self.current_page)

        dialog.protocol("WM_DELETE_WINDOW", save)
        dialog.bind("<Escape>", lambda _event: save())

    def _statistics_page(self) -> None:
        page = self._page_frame()
        self._page_header(page, "Statistik", "Ringkasan pola dari catatan yang kamu simpan.")
        cycles = self.db.get_cycles()
        lengths = [
            (date.fromisoformat(later["start_date"]) - date.fromisoformat(earlier["start_date"])).days
            for earlier, later in zip(cycles, cycles[1:])
        ]
        valid_lengths = [length for length in lengths if 15 <= length <= 60]
        durations = [
            (date.fromisoformat(item["end_date"]) - date.fromisoformat(item["start_date"])).days + 1
            for item in cycles if item["end_date"]
        ]
        avg_cycle = round(sum(valid_lengths) / len(valid_lengths)) if valid_lengths else int(self.db.get_setting("default_cycle", "28"))
        avg_duration = round(sum(durations) / len(durations), 1) if durations else float(self.db.get_setting("period_length", "5"))
        summary = tk.Frame(page, bg=self.colors["bg"])
        summary.pack(fill="x", pady=(0, 14))
        for title, value in (
            ("Rata-rata siklus", f"{avg_cycle} hari"),
            ("Rata-rata durasi haid", f"{avg_duration:g} hari"),
            ("Siklus tercatat", str(len(cycles))),
        ):
            card = self._card(summary, 16, 15)
            card.pack(side="left", fill="x", expand=True, padx=(0, 8))
            tk.Label(card, text=title, bg=self.colors["card"], fg=self.colors["muted"],
                     font=("Segoe UI", 12)).pack(anchor="w")
            tk.Label(card, text=value, bg=self.colors["card"], fg=self.colors["text"],
                     font=("Segoe UI", 18, "bold")).pack(anchor="w", pady=(5, 0))
        chart_card = self._card(page, 18, 16)
        chart_card.pack(fill="x", pady=(0, 12))
        tk.Label(chart_card, text="Panjang siklus terakhir", bg=self.colors["card"],
                 fg=self.colors["text"], font=("Segoe UI", 12, "bold")).pack(anchor="w")
        canvas = tk.Canvas(chart_card, height=155, bg=self.colors["card"], highlightthickness=0)
        canvas.pack(fill="x", pady=(8, 0))
        recent = valid_lengths[-12:]
        if recent:
            width = max(canvas.winfo_width(), 600)
            canvas.configure(height=160)
            bar_gap = 14
            bar_width = max(18, min(48, (width - 40) // len(recent) - bar_gap))
            max_value = max(max(recent), 40)
            for index, length in enumerate(recent):
                x = 24 + index * (bar_width + bar_gap)
                height = 105 * length / max_value
                color = self.colors["warning"] if length < 21 or length > 35 else self.colors["primary"]
                canvas.create_rectangle(x, 126 - height, x + bar_width, 126,
                                       fill=color, outline="")
                canvas.create_text(x + bar_width / 2, 126 - height - 11, text=str(length),
                                   fill=self.colors["text"], font=("Segoe UI", 12))
                canvas.create_text(x + bar_width / 2, 143, text=str(index + 1),
                                   fill=self.colors["muted"], font=("Segoe UI", 12))
        else:
            tk.Label(chart_card, text="Catat setidaknya dua awal haid untuk melihat grafik.",
                     bg=self.colors["card"], fg=self.colors["muted"]).pack(anchor="w", pady=12)
        symptom_counts: dict[str, int] = {}
        for log in self.db.get_logs():
            for symptom in log["symptoms"]:
                symptom_counts[symptom] = symptom_counts.get(symptom, 0) + 1
        common = sorted(symptom_counts.items(), key=lambda item: item[1], reverse=True)[:5]
        if common:
            symptom_card = self._card(page, 18, 14)
            symptom_card.pack(fill="x", pady=(0, 12))
            tk.Label(symptom_card, text="Gejala yang paling sering dicatat",
                     bg=self.colors["card"], fg=self.colors["text"],
                     font=("Segoe UI", 12, "bold")).pack(anchor="w")
            tk.Label(symptom_card, text="  ·  ".join(f"{SYMPTOMS[key]} ({count})" for key, count in common),
                     bg=self.colors["card"], fg=self.colors["muted"],
                     wraplength=780, justify="left").pack(anchor="w", pady=(8, 0))
        unusual = sum(length < 21 or length > 35 for length in valid_lengths)
        if unusual >= 2:
            tk.Label(page, text="Beberapa siklus berada di luar rentang 21–35 hari. "
                     "Bicarakan pola ini dengan tenaga kesehatan bila kamu khawatir.",
                     bg=self.colors["warning"], fg=self.colors["text"],
                     wraplength=780, justify="left", padx=12, pady=10).pack(fill="x", pady=(0, 10))
        self._disclaimer(page)

    def _settings_page(self) -> None:
        page = self._page_frame()
        self._page_header(page, "Pengaturan", "Preferensi dan data pribadimu tersimpan hanya di perangkat ini.")
        profile = self._card(page)
        profile.pack(fill="x", pady=(0, 12))
        tk.Label(profile, text="Profil & siklus", bg=self.colors["card"], fg=self.colors["text"],
                 font=("Segoe UI", 13, "bold")).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 12))
        fields: dict[str, tk.Entry] = {}
        for row, (label, key, default) in enumerate((
            ("Nama panggilan", "name", ""),
            ("Panjang siklus (15–60 hari)", "default_cycle", "28"),
            ("Durasi haid (1–15 hari)", "period_length", "5"),
        ), start=1):
            tk.Label(profile, text=label, bg=self.colors["card"], fg=self.colors["muted"]).grid(
                row=row, column=0, sticky="w", padx=(0, 14), pady=4
            )
            field = self._entry(profile, self.db.get_setting(key, default))
            field.grid(row=row, column=1, sticky="ew", padx=(0, 16), pady=4, ipady=6)
            fields[key] = field
        tk.Label(profile, text="Tema", bg=self.colors["card"], fg=self.colors["muted"]).grid(
            row=1, column=2, sticky="w", padx=(0, 10)
        )
        theme = tk.StringVar(value=self.db.get_setting("theme", "Rose Blush"))
        tk.OptionMenu(profile, theme, *THEMES.keys()).grid(row=1, column=3, sticky="ew")
        first_weekday = tk.StringVar(
            value="Senin" if self.db.get_setting("first_weekday", "0") == "0" else "Minggu"
        )
        tk.Label(profile, text="Minggu dimulai", bg=self.colors["card"],
                 fg=self.colors["muted"]).grid(row=2, column=2, sticky="w")
        tk.OptionMenu(profile, first_weekday, "Senin", "Minggu").grid(row=2, column=3, sticky="ew")
        profile.grid_columnconfigure(1, weight=1)
        profile.grid_columnconfigure(3, weight=1)
        discreet = tk.BooleanVar(value=self.db.get_setting("discreet") == "1")
        tk.Checkbutton(profile, text="Mode samaran (judul jendela: Catatan)",
                       variable=discreet, bg=self.colors["card"], fg=self.colors["text"],
                       activebackground=self.colors["card"], selectcolor=self.colors["soft"]).grid(
                           row=4, column=0, columnspan=3, sticky="w", pady=(10, 0)
                       )

        def save_settings() -> None:
            try:
                cycle_length = int(fields["default_cycle"].get())
                period_length = int(fields["period_length"].get())
                name = fields["name"].get().strip()
                if not name or not 15 <= cycle_length <= 60 or not 1 <= period_length <= 15:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Pengaturan tidak valid",
                                     "Isi nama, panjang siklus 15–60 hari, dan durasi 1–15 hari.",
                                     parent=self.root)
                return
            self.db.set_settings({
                "name": name, "default_cycle": str(cycle_length),
                "period_length": str(period_length), "theme": theme.get(),
                "first_weekday": "0" if first_weekday.get() == "Senin" else "6",
                "discreet": "1" if discreet.get() else "0",
            })
            self.colors = THEMES[theme.get()]
            self._configure_window()
            self._build_shell()
            self.show_page("Pengaturan")

        self._button(profile, "Simpan pengaturan", save_settings, primary=True).grid(
            row=5, column=0, columnspan=4, sticky="w", pady=(14, 0)
        )
        privacy = self._card(page, 18, 14)
        privacy.pack(fill="x", pady=(0, 12))
        tk.Label(privacy, text="Privasi & keamanan", bg=self.colors["card"],
                 fg=self.colors["text"], font=("Segoe UI", 13, "bold")).pack(anchor="w")
        privacy_actions = tk.Frame(privacy, bg=self.colors["card"])
        privacy_actions.pack(fill="x", pady=(10, 0))
        self._button(privacy_actions, "Atur / ubah PIN", self._change_pin).pack(side="left")
        self._button(privacy_actions, "Ekspor CSV", self._export_csv).pack(side="left", padx=8)
        self._button(privacy_actions, "Cadangkan data", self._backup_dialog).pack(side="left", padx=8)
        self._button(privacy_actions, "Pulihkan cadangan", self._restore_dialog).pack(side="left")
        data_card = self._card(page, 18, 14)
        data_card.pack(fill="x", pady=(0, 12))
        tk.Label(data_card, text="Data & informasi", bg=self.colors["card"],
                 fg=self.colors["text"], font=("Segoe UI", 13, "bold")).pack(anchor="w")
        tk.Label(data_card, text="Cadangan otomatis mingguan disimpan di LunaData/backup. "
                 "Luna bekerja offline dan tidak mengirim data ke pihak lain.",
                 bg=self.colors["card"], fg=self.colors["muted"], wraplength=780,
                 justify="left").pack(anchor="w", pady=(5, 10))
        actions = tk.Frame(data_card, bg=self.colors["card"])
        actions.pack(fill="x")
        self._button(actions, "Tentang & disclaimer", self._about_dialog).pack(side="left")
        self._button(actions, "Hapus semua data", self._delete_all).pack(side="right")

    def _change_pin(self) -> None:
        current = self.db.get_setting("pin_hash")
        if current:
            old = simpledialog.askstring("Verifikasi PIN", "Masukkan PIN lama:",
                                         show="•", parent=self.root)
            if old is None:
                return
            if not verify_pin(old, current):
                messagebox.showerror("PIN salah", "PIN lama tidak cocok.", parent=self.root)
                return
        new = simpledialog.askstring("PIN baru", "Masukkan PIN baru 4 digit "
                                     "(kosongkan untuk menonaktifkan):",
                                     show="•", parent=self.root)
        if new is None:
            return
        if new == "":
            if current and messagebox.askyesno("Nonaktifkan PIN", "Nonaktifkan kunci PIN?", parent=self.root):
                self.db.set_settings({"pin_hash": ""})
            return
        try:
            hashed = hash_pin(new)
        except ValueError as error:
            messagebox.showerror("PIN tidak valid", str(error), parent=self.root)
            return
        confirm = simpledialog.askstring("Konfirmasi PIN", "Ulangi PIN baru:",
                                         show="•", parent=self.root)
        if confirm != new:
            messagebox.showerror("PIN tidak cocok", "PIN yang dimasukkan berbeda.", parent=self.root)
            return
        self.db.set_settings({"pin_hash": hashed})
        messagebox.showinfo("PIN diperbarui", "PIN Luna berhasil diperbarui.", parent=self.root)

    def _export_csv(self) -> None:
        destination = filedialog.asksaveasfilename(
            parent=self.root, title="Ekspor catatan Luna",
            defaultextension=".csv", filetypes=[("CSV", "*.csv")],
            initialfile=f"luna-catatan-{self.today.isoformat()}.csv",
        )
        if not destination:
            return
        try:
            self.db.export_csv(destination)
        except (OSError, sqlite3.Error) as error:
            messagebox.showerror("Ekspor gagal", str(error), parent=self.root)
            return
        messagebox.showinfo("Ekspor selesai", "Catatan berhasil diekspor ke CSV.", parent=self.root)

    def _backup_dialog(self) -> None:
        destination = filedialog.asksaveasfilename(
            parent=self.root, title="Cadangkan data Luna",
            defaultextension=".luna", filetypes=[("Cadangan Luna", "*.luna")],
            initialfile=f"luna-backup-{self.today.isoformat()}.luna",
        )
        if destination:
            try:
                self.db.backup_to(destination)
            except (OSError, sqlite3.Error, ValueError) as error:
                messagebox.showerror("Cadangan gagal", str(error), parent=self.root)
                return
            messagebox.showinfo("Cadangan selesai", "Cadangan lokal berhasil dibuat.", parent=self.root)

    def _restore_dialog(self) -> None:
        source = filedialog.askopenfilename(
            parent=self.root, title="Pulihkan cadangan Luna",
            filetypes=[("Cadangan Luna", "*.luna"), ("Database SQLite", "*.db"), ("Semua file", "*.*")],
        )
        if not source or not messagebox.askyesno(
            "Pulihkan cadangan",
            "Data saat ini akan diganti dengan isi cadangan. Buat cadangan sebelum melanjutkan?",
            parent=self.root,
        ):
            return
        try:
            emergency = data_directory() / "backup" / f"before-restore-{self.today.isoformat()}.luna"
            self.db.backup_to(emergency)
            self.db.restore_from(source)
        except (OSError, ValueError, sqlite3.Error) as error:
            messagebox.showerror("Pemulihan gagal", str(error), parent=self.root)
            return
        messagebox.showinfo("Pemulihan selesai", "Data berhasil dipulihkan.", parent=self.root)
        self.root.destroy()

    def _delete_all(self) -> None:
        if not messagebox.askyesno("Hapus semua data",
                                   "Semua catatan dan pengaturan Luna akan dihapus permanen. Lanjutkan?",
                                   parent=self.root):
            return
        if not messagebox.askyesno("Konfirmasi terakhir",
                                   "Tindakan ini tidak dapat dibatalkan. Yakin ingin menghapus semuanya?",
                                   parent=self.root):
            return
        self.db.clear_all()
        if self._show_onboarding():
            self.colors = THEMES.get(self.db.get_setting("theme", "Rose Blush"), THEMES["Rose Blush"])
            self._configure_window()
            self._build_shell()
            self.show_page("Beranda")
        else:
            self.root.destroy()

    def _about_dialog(self) -> None:
        messagebox.showinfo(
            "Tentang Luna",
            "Luna v1.0\nKenali ritme tubuhmu, dengan tenang.\n\n"
            "Aplikasi pencatatan siklus yang bekerja offline. Data tersimpan "
            "secara lokal di folder LunaData di samping aplikasi.\n\n"
            + MEDICAL_DISCLAIMER,
            parent=self.root,
        )


import sqlite3
