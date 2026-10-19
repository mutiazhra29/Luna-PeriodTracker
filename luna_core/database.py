import csv
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any


SYMPTOMS = {
    "cramps": "Kram",
    "headache": "Sakit kepala",
    "back_pain": "Nyeri punggung",
    "bloating": "Kembung",
    "acne": "Jerawat",
    "fatigue": "Lelah",
    "nausea": "Mual",
    "breast_pain": "Nyeri payudara",
    "dizziness": "Pusing",
    "appetite": "Perubahan nafsu makan",
    "sleep": "Sulit tidur",
    "digestion": "Diare / sembelit",
}
FLOWS = ("spotting", "light", "medium", "heavy")


class LunaDatabase:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._initialize()

    def _initialize(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS cycles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_date TEXT NOT NULL UNIQUE,
                end_date TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_cycles_start ON cycles(start_date);
            CREATE TABLE IF NOT EXISTS daily_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                log_date TEXT NOT NULL UNIQUE,
                is_period INTEGER NOT NULL DEFAULT 0,
                flow TEXT,
                mood TEXT,
                note TEXT NOT NULL DEFAULT '',
                temperature REAL,
                weight REAL,
                water INTEGER,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS symptoms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                label TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS log_symptoms (
                log_id INTEGER NOT NULL REFERENCES daily_logs(id) ON DELETE CASCADE,
                symptom_id INTEGER NOT NULL REFERENCES symptoms(id),
                PRIMARY KEY (log_id, symptom_id)
            );
            """
        )
        self.connection.executemany(
            "INSERT OR IGNORE INTO symptoms(code, label) VALUES (?, ?)",
            SYMPTOMS.items(),
        )
        self.connection.commit()

    def get_setting(self, key: str, default: str = "") -> str:
        row = self.connection.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default

    def set_settings(self, values: dict[str, str]) -> None:
        with self.connection:
            self.connection.executemany(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                values.items(),
            )

    def get_cycles(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT id, start_date, end_date FROM cycles ORDER BY start_date"
        ).fetchall()
        return [dict(row) for row in rows]

    def add_cycle(self, start: date, end: date | None = None) -> int:
        if end and end < start:
            raise ValueError("Tanggal selesai tidak boleh sebelum tanggal mulai.")
        with self.connection:
            cursor = self.connection.execute(
                "INSERT INTO cycles(start_date, end_date) VALUES (?, ?)",
                (start.isoformat(), end.isoformat() if end else None),
            )
            return int(cursor.lastrowid)

    def finish_active_cycle(self, end: date) -> bool:
        with self.connection:
            row = self.connection.execute(
                "SELECT id, start_date FROM cycles WHERE end_date IS NULL "
                "ORDER BY start_date DESC LIMIT 1"
            ).fetchone()
            if not row:
                return False
            if end < date.fromisoformat(row["start_date"]):
                raise ValueError("Tanggal selesai tidak boleh sebelum tanggal mulai.")
            self.connection.execute(
                "UPDATE cycles SET end_date = ? WHERE id = ?",
                (end.isoformat(), row["id"]),
            )
            return True

    def delete_cycle(self, start: date) -> None:
        with self.connection:
            self.connection.execute(
                "DELETE FROM cycles WHERE start_date = ?", (start.isoformat(),)
            )

    def get_log(self, log_date: date) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM daily_logs WHERE log_date = ?", (log_date.isoformat(),)
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["symptoms"] = self._symptoms_for(int(result["id"]))
        return result

    def get_logs(self, limit: int | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM daily_logs ORDER BY log_date DESC"
        params: tuple[Any, ...] = ()
        if limit is not None:
            query += " LIMIT ?"
            params = (limit,)
        result = [dict(row) for row in self.connection.execute(query, params)]
        for log in result:
            log["symptoms"] = self._symptoms_for(int(log["id"]))
        return result

    def _symptoms_for(self, log_id: int) -> list[str]:
        rows = self.connection.execute(
            "SELECT s.code FROM symptoms s JOIN log_symptoms ls "
            "ON ls.symptom_id = s.id WHERE ls.log_id = ? ORDER BY s.label",
            (log_id,),
        ).fetchall()
        return [row["code"] for row in rows]

    def save_log(self, values: dict[str, Any]) -> None:
        log_date = values["log_date"]
        if isinstance(log_date, date):
            log_date = log_date.isoformat()
        note = str(values.get("note", ""))
        if len(note) > 500:
            raise ValueError("Catatan maksimal 500 karakter.")
        flow = values.get("flow") or None
        if flow not in (*FLOWS, None):
            raise ValueError("Intensitas aliran tidak valid.")
        symptoms = set(values.get("symptoms", []))
        invalid = symptoms.difference(SYMPTOMS)
        if invalid:
            raise ValueError("Gejala tidak dikenal: " + ", ".join(sorted(invalid)))
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO daily_logs(log_date, is_period, flow, mood, note,
                    temperature, weight, water, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(log_date) DO UPDATE SET
                    is_period = excluded.is_period, flow = excluded.flow,
                    mood = excluded.mood, note = excluded.note,
                    temperature = excluded.temperature, weight = excluded.weight,
                    water = excluded.water, updated_at = CURRENT_TIMESTAMP
                """,
                (
                    log_date,
                    int(bool(values.get("is_period"))),
                    flow,
                    values.get("mood") or None,
                    note,
                    values.get("temperature"),
                    values.get("weight"),
                    values.get("water"),
                ),
            )
            row = self.connection.execute(
                "SELECT id FROM daily_logs WHERE log_date = ?", (log_date,)
            ).fetchone()
            log_id = int(row["id"])
            self.connection.execute("DELETE FROM log_symptoms WHERE log_id = ?", (log_id,))
            self.connection.executemany(
                "INSERT INTO log_symptoms(log_id, symptom_id) "
                "SELECT ?, id FROM symptoms WHERE code = ?",
                ((log_id, code) for code in sorted(symptoms)),
            )

    def delete_log(self, log_date: date) -> None:
        with self.connection:
            self.connection.execute(
                "DELETE FROM daily_logs WHERE log_date = ?", (log_date.isoformat(),)
            )

    def export_csv(self, destination: Path | str) -> None:
        with Path(destination).open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(
                ["tanggal", "haid", "aliran", "mood", "gejala", "catatan",
                 "suhu_basal", "berat_badan", "air"]
            )
            for log in reversed(self.get_logs()):
                writer.writerow(
                    [
                        log["log_date"],
                        "Ya" if log["is_period"] else "Tidak",
                        log["flow"] or "",
                        log["mood"] or "",
                        ", ".join(SYMPTOMS[code] for code in log["symptoms"]),
                        log["note"],
                        log["temperature"] if log["temperature"] is not None else "",
                        log["weight"] if log["weight"] is not None else "",
                        log["water"] if log["water"] is not None else "",
                    ]
                )

    def backup_to(self, destination: Path | str) -> None:
        target = Path(destination)
        if target.resolve() == self.path.resolve():
            raise ValueError("Lokasi cadangan tidak boleh menimpa database aktif.")
        target.parent.mkdir(parents=True, exist_ok=True)
        backup = sqlite3.connect(target)
        try:
            self.connection.backup(backup)
        finally:
            backup.close()

    def restore_from(self, source_path: Path | str) -> None:
        source_path = Path(source_path)
        if source_path.resolve() == self.path.resolve():
            raise ValueError("Pilih file cadangan yang berbeda dari database aktif.")
        source = sqlite3.connect(source_path)
        try:
            integrity = source.execute("PRAGMA integrity_check").fetchone()
            if not integrity or integrity[0] != "ok":
                raise ValueError("File cadangan rusak atau tidak valid.")
            tables = {
                row[0]
                for row in source.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            if not {"settings", "cycles", "daily_logs", "symptoms", "log_symptoms"} <= tables:
                raise ValueError("File bukan cadangan Luna yang valid.")
            source.backup(self.connection)
            self.connection.execute("PRAGMA foreign_keys = ON")
        finally:
            source.close()

    def clear_all(self) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM log_symptoms")
            self.connection.execute("DELETE FROM daily_logs")
            self.connection.execute("DELETE FROM cycles")
            self.connection.execute("DELETE FROM settings")

    def close(self) -> None:
        self.connection.close()
