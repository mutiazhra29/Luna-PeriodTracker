import tempfile
import sqlite3
import unittest
from datetime import date
from pathlib import Path

from luna_core.database import LunaDatabase
from luna_core.predictor import predict_cycle
from luna_core.security import hash_pin, verify_pin


class PredictorTests(unittest.TestCase):
    def test_regular_cycles_predict_dates_and_phase(self):
        starts = [date(2026, 1, 1), date(2026, 1, 29), date(2026, 2, 26)]
        result = predict_cycle(starts, date(2026, 3, 5), 28, 5)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.next_period, date(2026, 3, 26))
        self.assertEqual(result.ovulation, date(2026, 3, 12))
        self.assertEqual(result.fertile_start, date(2026, 3, 7))
        self.assertEqual(result.cycle_day, 8)
        self.assertEqual(result.phase, "Folikular")
        self.assertFalse(result.irregular)

    def test_defaults_and_missing_cycles(self):
        self.assertIsNone(predict_cycle([], date(2026, 1, 1)))
        result = predict_cycle([date(2026, 1, 1), date(2026, 1, 29)],
                               date(2026, 1, 10), 30, 5)
        assert result is not None
        self.assertEqual(result.cycle_length, 30)
        self.assertEqual(result.next_period, date(2026, 2, 28))

    def test_irregular_cycles_are_flagged_and_outliers_ignored(self):
        starts = [
            date(2025, 10, 1), date(2025, 10, 29), date(2025, 11, 27),
            date(2025, 12, 28), date(2026, 1, 29), date(2026, 3, 10),
        ]
        result = predict_cycle(starts, date(2026, 2, 2))
        assert result is not None
        self.assertTrue(result.irregular)
        self.assertGreater(result.uncertainty_days, 0)

    def test_cycle_outliers_are_excluded_from_average(self):
        starts = [
            date(2025, 1, 1), date(2025, 1, 29), date(2025, 3, 5),
            date(2025, 5, 20), date(2025, 6, 17), date(2025, 7, 15),
            date(2025, 8, 12),
        ]
        result = predict_cycle(starts, date(2025, 8, 13))
        assert result is not None
        self.assertEqual(result.cycle_length, 29)
        self.assertEqual(result.next_period, date(2025, 9, 10))

    def test_date_rollover_and_menstrual_phase(self):
        result = predict_cycle([date(2024, 12, 20)], date(2024, 12, 21), 28, 5)
        assert result is not None
        self.assertEqual(result.next_period, date(2025, 1, 17))
        self.assertEqual(result.phase, "Menstruasi")


class SecurityTests(unittest.TestCase):
    def test_pin_is_salted_and_verified(self):
        first = hash_pin("0427")
        second = hash_pin("0427")
        self.assertNotEqual(first, second)
        self.assertTrue(verify_pin("0427", first))
        self.assertFalse(verify_pin("0000", first))
        self.assertFalse(verify_pin("bad", first))

    def test_pin_requires_four_digits(self):
        with self.assertRaises(ValueError):
            hash_pin("123")


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = LunaDatabase(Path(self.temp.name) / "luna.db")

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_log_create_update_delete_and_symptoms(self):
        day = date(2026, 6, 3)
        self.db.save_log(
            {"log_date": day, "is_period": True, "flow": "medium",
             "mood": "😊", "note": "Kram ringan", "symptoms": ["cramps", "fatigue"]}
        )
        log = self.db.get_log(day)
        self.assertIsNotNone(log)
        assert log is not None
        self.assertEqual(set(log["symptoms"]), {"cramps", "fatigue"})
        self.db.save_log({"log_date": day, "note": "Sudah membaik", "symptoms": []})
        updated = self.db.get_log(day)
        assert updated is not None
        self.assertEqual(updated["note"], "Sudah membaik")
        self.assertEqual(updated["symptoms"], [])
        self.db.delete_log(day)
        self.assertIsNone(self.db.get_log(day))

    def test_cycle_validation_and_finish(self):
        start = date(2026, 5, 1)
        self.db.add_cycle(start)
        self.assertTrue(self.db.finish_active_cycle(date(2026, 5, 5)))
        self.assertEqual(self.db.get_cycles()[0]["end_date"], "2026-05-05")
        with self.assertRaises(ValueError):
            self.db.add_cycle(date(2026, 5, 8), date(2026, 5, 7))
        self.db.delete_cycle(start)
        self.assertEqual(self.db.get_cycles(), [])

    def test_backup_restore_and_csv_export(self):
        day = date(2026, 4, 9)
        self.db.set_settings({"name": "Nadia"})
        self.db.save_log({"log_date": day, "note": "Cadangan", "symptoms": ["cramps"]})
        backup = Path(self.temp.name) / "backup.luna"
        self.db.backup_to(backup)
        self.db.clear_all()
        self.db.restore_from(backup)
        self.assertEqual(self.db.get_setting("name"), "Nadia")
        self.assertEqual(self.db.get_log(day)["note"], "Cadangan")
        csv_path = Path(self.temp.name) / "export.csv"
        self.db.export_csv(csv_path)
        self.assertIn("2026-04-09", csv_path.read_text(encoding="utf-8-sig"))

    def test_note_length_is_limited(self):
        with self.assertRaises(ValueError):
            self.db.save_log({"log_date": date.today(), "note": "x" * 501})

    def test_restore_rejects_non_luna_database(self):
        invalid = Path(self.temp.name) / "not-luna.db"
        invalid.write_text("not a database")
        with self.assertRaises(sqlite3.DatabaseError):
            self.db.restore_from(invalid)


if __name__ == "__main__":
    unittest.main()
