"""Tests for database seeding and ROSTER_IDS behavior."""

import os
import sys
import tempfile
from pathlib import Path
import pytest

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set test env BEFORE importing
os.environ['JWT_SECRET'] = 'test-secret-key-for-testing-minimum-32-chars-long'
os.environ['AUTH_REQUIRED'] = 'true'
os.environ['ALLOWED_ORIGINS'] = 'http://localhost:5500,http://127.0.0.1:5500,http://localhost:8000,http://127.0.0.1:8000'

import database
from main import ROSTER, CREW_SIZE, get_roster
from models import Astronaut, VitalsReading
from thresholds import (
    eval_stress, evaluate_vitals, explain, eval_heart_rate, eval_blood_pressure,
    eval_spo2, eval_temp, eval_radiation, worst
)


class TestDatabaseSeeding:
    """Test database initialization and seeding."""

    @pytest.fixture(autouse=True)
    def setup_db(self, tmp_path):
        """Use temporary database for each test."""
        # Save original DB_PATH
        self.original_db_path = database.DB_PATH
        # Use temp file
        self.temp_db = tmp_path / "test_vitanet.db"
        database.DB_PATH = self.temp_db
        yield
        # Restore
        database.DB_PATH = self.original_db_path

    def test_init_db_creates_tables(self):
        """init_db creates astronauts, vitals_log, alerts_log, mission_events tables."""
        database.init_db()

        with database.get_conn() as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('astronauts', 'vitals_log', 'alerts_log', 'mission_events')"
            ).fetchall()
            table_names = {row['name'] for row in tables}

        assert table_names == {'astronauts', 'vitals_log', 'alerts_log', 'mission_events'}

    def test_upsert_astronaut_insert_and_update(self):
        """upsert_astronaut inserts new and updates on conflict."""
        database.init_db()

        # Insert new
        database.upsert_astronaut("test1", "Test One", "Commander")
        astros = database.list_astronauts()
        assert len(astros) == 1
        assert astros[0]['id'] == "test1"
        assert astros[0]['name'] == "Test One"
        assert astros[0]['role'] == "Commander"

        # Update on conflict
        database.upsert_astronaut("test1", "Test One Updated", "Flight Engineer")
        astros = database.list_astronauts()
        assert len(astros) == 1
        assert astros[0]['name'] == "Test One Updated"
        assert astros[0]['role'] == "Flight Engineer"

    def test_list_astronauts_returns_seeded_crew(self):
        """list_astronauts returns seeded crew from ROSTER."""
        database.init_db()

        # Seed from ROSTER (simulating lifespan)
        for a in ROSTER:
            database.upsert_astronaut(a.id, a.name, a.role)

        astros = database.list_astronauts()
        assert len(astros) == len(ROSTER)

        for i, a in enumerate(ROSTER):
            assert astros[i]['id'] == a.id
            assert astros[i]['name'] == a.name
            assert astros[i]['role'] == a.role

    def test_get_seeded_ids_dynamic(self):
        """_get_seeded_ids returns the original seeded roster IDs (not the mutable ROSTER_IDS global)."""
        seeded = database._get_seeded_ids()
        # Should match the original roster size, not the potentially polluted ROSTER_IDS
        assert len(seeded) == CREW_SIZE
        assert all(id_.startswith('a') for id_ in seeded)
        # Should contain the expected default IDs (first CREW_SIZE entries)
        expected = {f"a{i}" for i in range(1, CREW_SIZE + 1)}
        assert seeded == expected


class TestResetAll:
    """Test reset_all preserves seeded astronauts, clears logs."""

    @pytest.fixture(autouse=True)
    def setup_db(self, tmp_path):
        self.original_db_path = database.DB_PATH
        self.temp_db = tmp_path / "test_vitanet.db"
        database.DB_PATH = self.temp_db
        database.init_db()
        # Seed roster
        for a in ROSTER:
            database.upsert_astronaut(a.id, a.name, a.role)
        yield
        database.DB_PATH = self.original_db_path

    def test_reset_all_preserves_seeded_astronauts(self):
        """reset_all keeps seeded astronauts, removes non-seeded."""
        # Add a non-seeded astronaut
        database.upsert_astronaut("injected1", "Hacker", "Intruder")

        # Verify it exists before reset
        astros_before = database.list_astronauts()
        assert any(a['id'] == 'injected1' for a in astros_before)

        # Reset
        database.reset_all()

        # Verify seeded remain, non-seeded removed
        astros_after = database.list_astronauts()
        assert len(astros_after) == len(ROSTER)
        seeded_ids = database._get_seeded_ids()
        assert all(a['id'] in seeded_ids for a in astros_after)
        assert not any(a['id'] == 'injected1' for a in astros_after)

    def test_reset_all_clears_logs(self):
        """reset_all clears vitals_log, alerts_log, mission_events."""
        from models import VitalsReading

        # Add some logs
        reading = VitalsReading(heartRate=70, bpSys=120, bpDia=80, spo2=98, tempC=37.0, stressIndex=30, radiationMSv=10)
        database.insert_reading("a1", reading)
        database.log_alert("a1", "watch", "heartRate", 110, "Elevated HR")

        with database.get_conn() as conn:
            conn.execute("INSERT INTO mission_events (event_type, description) VALUES (?, ?)", ("test", "Test event"))

        # Verify logs exist
        with database.get_conn() as conn:
            vitals_count = conn.execute("SELECT COUNT(*) FROM vitals_log").fetchone()[0]
            alerts_count = conn.execute("SELECT COUNT(*) FROM alerts_log").fetchone()[0]
            events_count = conn.execute("SELECT COUNT(*) FROM mission_events").fetchone()[0]

        assert vitals_count > 0
        assert alerts_count > 0
        assert events_count > 0

        # Reset
        database.reset_all()

        # Verify logs cleared
        with database.get_conn() as conn:
            vitals_count = conn.execute("SELECT COUNT(*) FROM vitals_log").fetchone()[0]
            alerts_count = conn.execute("SELECT COUNT(*) FROM alerts_log").fetchone()[0]
            events_count = conn.execute("SELECT COUNT(*) FROM mission_events").fetchone()[0]

        assert vitals_count == 0
        assert alerts_count == 0
        assert events_count == 0


class TestVitalsOperations:
    """Test insert_reading, get_history, delete_astronaut cascades."""

    @pytest.fixture(autouse=True)
    def setup_db(self, tmp_path):
        self.original_db_path = database.DB_PATH
        self.temp_db = tmp_path / "test_vitanet.db"
        database.DB_PATH = self.temp_db
        database.init_db()
        for a in ROSTER:
            database.upsert_astronaut(a.id, a.name, a.role)
        yield
        database.DB_PATH = self.original_db_path

    def test_insert_reading_and_history(self):
        """insert_reading then retrieve with limit."""
        from models import VitalsReading

        reading = VitalsReading(heartRate=75, bpSys=120, bpDia=80, spo2=98, tempC=37.0, stressIndex=25, radiationMSv=5)
        database.insert_reading("a1", reading)

        history = database.get_history("a1", limit=10)
        assert len(history) == 1
        assert history[0]['astronaut_id'] == "a1"
        assert history[0]['heart_rate'] == 75
        assert history[0]['bp_sys'] == 120

    def test_get_history_respects_limit(self):
        """get_history respects limit parameter."""
        from models import VitalsReading

        for i in range(15):
            r = VitalsReading(heartRate=70+i, bpSys=120, bpDia=80, spo2=98, tempC=37.0, stressIndex=20, radiationMSv=1)
            database.insert_reading("a1", r)

        history = database.get_history("a1", limit=5)
        assert len(history) == 5

        history = database.get_history("a1", limit=100)
        assert len(history) == 15

    def test_delete_astronaut_cascades(self):
        """delete_astronaut removes astronaut and their vitals."""
        from models import VitalsReading

        # Add readings for a1
        for i in range(3):
            r = VitalsReading(heartRate=70+i, bpSys=120, bpDia=80, spo2=98, tempC=37.0, stressIndex=20, radiationMSv=1)
            database.insert_reading("a1", r)

        # Verify data exists
        assert len(database.get_history("a1")) == 3
        assert any(a['id'] == 'a1' for a in database.list_astronauts())

        # Delete
        database.delete_astronaut("a1")

        # Verify cascaded delete
        assert len(database.get_history("a1")) == 0
        assert not any(a['id'] == 'a1' for a in database.list_astronauts())


class TestROSTERIDSDynamic:
    """Test ROSTER_IDS dynamic behavior from main.py."""

    def test_get_roster_matches_CREW_SIZE(self):
        """len(get_roster()) == CREW_SIZE."""
        assert len(get_roster()) == CREW_SIZE

    def test_get_roster_contains_expected_ids(self):
        """get_roster() contains a1..a6 for default CREW_SIZE=6."""
        # Default CREW_SIZE is 6
        expected = {f"a{i}" for i in range(1, CREW_SIZE + 1)}
        roster_ids = {a.id for a in get_roster()}
        assert roster_ids == expected

    def test_ROSTER_matches_CREW_SIZE(self):
        """len(ROSTER) == CREW_SIZE."""
        assert len(ROSTER) == CREW_SIZE

    def test_ROSTER_contains_expected_ids(self):
        """ROSTER contains a1..a6 for default CREW_SIZE=6."""
        # Default CREW_SIZE is 6
        expected = {f"a{i}" for i in range(1, CREW_SIZE + 1)}
        roster_ids = {a.id for a in ROSTER}
        assert roster_ids == expected

    def test_get_roster_respects_CREW_SIZE_env(self, monkeypatch):
        """CREW_SIZE=3 returns 3 astronauts."""
        monkeypatch.setenv("CREW_SIZE", "3")
        # Need to reimport to pick up new env
        import importlib
        import main
        importlib.reload(main)

        assert main.CREW_SIZE == 3
        roster = main.get_roster()
        assert len(roster) == 3
        assert [a.id for a in roster] == ["a1", "a2", "a3"]

        # Restore
        monkeypatch.setenv("CREW_SIZE", "6")
        importlib.reload(main)


class TestThresholdsStressEdgeCases:
    """Test eval_stress boundary conditions."""

    def test_eval_stress_crit_at_80(self):
        """index >= 80 returns 'crit'."""
        assert eval_stress(80) == "crit"
        assert eval_stress(85) == "crit"
        assert eval_stress(100) == "crit"

    def test_eval_stress_watch_at_55(self):
        """index >= 55 returns 'watch'."""
        assert eval_stress(55) == "watch"
        assert eval_stress(60) == "watch"
        assert eval_stress(79) == "watch"

    def test_eval_stress_ok_below_55(self):
        """index < 55 returns 'ok'."""
        assert eval_stress(0) == "ok"
        assert eval_stress(30) == "ok"
        assert eval_stress(54) == "ok"

    def test_eval_stress_boundary_80(self):
        """exactly 80 = 'crit'."""
        assert eval_stress(80) == "crit"

    def test_eval_stress_boundary_55(self):
        """exactly 55 = 'watch'."""
        assert eval_stress(55) == "watch"

    def test_eval_stress_boundary_54_9(self):
        """54.9 = 'ok'."""
        assert eval_stress(54.9) == "ok"

    def test_evaluate_vitals_includes_stress(self):
        """overall includes stress in worst()."""
        # Create vitals where stress is the worst
        v = VitalsReading(
            heartRate=70, bpSys=120, bpDia=80, spo2=98, tempC=37.0,
            stressIndex=90,  # crit stress
            radiationMSv=10
        )
        result = evaluate_vitals(v)
        assert result['per']['stress'] == "crit"
        assert result['overall'] == "crit"

        # Create vitals where stress is watch, others ok
        v2 = VitalsReading(
            heartRate=70, bpSys=120, bpDia=80, spo2=98, tempC=37.0,
            stressIndex=60,  # watch stress
            radiationMSv=10
        )
        result2 = evaluate_vitals(v2)
        assert result2['per']['stress'] == "watch"
        assert result2['overall'] == "watch"


class TestThresholdsParity:
    """Test thresholds.py stays in sync with generate_thresholds.py."""

    def test_thresholds_synced_with_generator(self):
        """Run generate_thresholds.py, compare stress threshold = 55."""
        import subprocess
        import sys
        from pathlib import Path

        # Run generator
        project_root = Path(__file__).parent.parent.parent
        result = subprocess.run(
            [sys.executable, "generate_thresholds.py"],
            cwd=project_root,
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Generator failed: {result.stderr}"

        # Read generated backend/thresholds.py
        generated_path = project_root / "backend" / "thresholds.py"
        generated_content = generated_path.read_text(encoding="utf-8")

        # Check stress threshold is 55 (watchLow from spec)
        assert "if index >= 55:" in generated_content
        assert "if index >= 80:" in generated_content

        # Verify current thresholds.py matches
        current_path = Path(__file__).parent.parent / "thresholds.py"
        current_content = current_path.read_text(encoding="utf-8")

        # Both should have same stress boundaries
        assert "if index >= 80:" in current_content
        assert "if index >= 55:" in current_content
        assert 'return "ok"' in current_content


class TestThresholdsAllEvalFunctions:
    """Test all evaluation functions for full coverage."""

    def test_explain_returns_refs(self):
        """explain returns reference info for known keys."""
        assert explain("heartRate") is not None
        assert explain("bp") is not None
        assert explain("spo2") is not None
        assert explain("temp") is not None
        assert explain("radiation") is not None
        assert explain("stress") is not None
        assert explain("unknown") is None

    def test_worst_returns_highest_severity(self):
        """worst returns highest severity from list."""
        assert worst("ok", "watch", "crit") == "crit"
        assert worst("ok", "watch") == "watch"
        assert worst("ok", "ok") == "ok"
        assert worst("crit") == "crit"

    def test_eval_heart_rate_crit_low(self):
        """HR < 40 returns crit."""
        assert eval_heart_rate(35) == "crit"
        assert eval_heart_rate(39) == "crit"

    def test_eval_heart_rate_crit_high(self):
        """HR > 140 returns crit."""
        assert eval_heart_rate(141) == "crit"
        assert eval_heart_rate(200) == "crit"

    def test_eval_heart_rate_watch_low(self):
        """HR < 50 returns watch."""
        assert eval_heart_rate(40) == "watch"
        assert eval_heart_rate(49) == "watch"

    def test_eval_heart_rate_watch_high(self):
        """HR > 100 returns watch."""
        assert eval_heart_rate(101) == "watch"
        assert eval_heart_rate(139) == "watch"

    def test_eval_heart_rate_ok(self):
        """HR 50-100 returns ok."""
        assert eval_heart_rate(50) == "ok"
        assert eval_heart_rate(75) == "ok"
        assert eval_heart_rate(100) == "ok"

    def test_eval_blood_pressure_grade3_crit(self):
        """BP >= 180/110 returns crit grade3."""
        assert eval_blood_pressure(180, 110) == ("crit", "grade3")
        assert eval_blood_pressure(200, 120) == ("crit", "grade3")
        assert eval_blood_pressure(180, 80) == ("crit", "grade3")
        assert eval_blood_pressure(120, 110) == ("crit", "grade3")

    def test_eval_blood_pressure_grade2_crit(self):
        """BP >= 160/100 returns crit grade2."""
        assert eval_blood_pressure(160, 100) == ("crit", "grade2")
        assert eval_blood_pressure(170, 105) == ("crit", "grade2")
        assert eval_blood_pressure(160, 80) == ("crit", "grade2")
        assert eval_blood_pressure(120, 100) == ("crit", "grade2")

    def test_eval_blood_pressure_grade1_watch(self):
        """BP >= 140/90 returns watch grade1."""
        assert eval_blood_pressure(140, 90) == ("watch", "grade1")
        assert eval_blood_pressure(150, 95) == ("watch", "grade1")
        assert eval_blood_pressure(140, 80) == ("watch", "grade1")
        assert eval_blood_pressure(120, 90) == ("watch", "grade1")

    def test_eval_blood_pressure_high_normal_watch(self):
        """BP >= 130/85 returns watch high-normal."""
        assert eval_blood_pressure(130, 85) == ("watch", "high-normal")
        assert eval_blood_pressure(135, 87) == ("watch", "high-normal")
        assert eval_blood_pressure(130, 80) == ("watch", "high-normal")
        assert eval_blood_pressure(120, 85) == ("watch", "high-normal")

    def test_eval_blood_pressure_low_watch(self):
        """BP < 90/60 returns watch low."""
        assert eval_blood_pressure(85, 55) == ("watch", "low")
        assert eval_blood_pressure(89, 59) == ("watch", "low")
        assert eval_blood_pressure(85, 80) == ("watch", "low")
        assert eval_blood_pressure(120, 55) == ("watch", "low")

    def test_eval_blood_pressure_normal_ok(self):
        """BP 90-129/60-84 returns ok normal."""
        assert eval_blood_pressure(120, 80) == ("ok", "normal")
        assert eval_blood_pressure(110, 70) == ("ok", "normal")
        assert eval_blood_pressure(90, 60) == ("ok", "normal")
        assert eval_blood_pressure(129, 84) == ("ok", "normal")

    def test_eval_spo2_crit(self):
        """SpO2 < 90 returns crit."""
        assert eval_spo2(85) == "crit"
        assert eval_spo2(89) == "crit"

    def test_eval_spo2_watch(self):
        """SpO2 < 95 returns watch."""
        assert eval_spo2(90) == "watch"
        assert eval_spo2(94) == "watch"

    def test_eval_spo2_ok(self):
        """SpO2 >= 95 returns ok."""
        assert eval_spo2(95) == "ok"
        assert eval_spo2(98) == "ok"
        assert eval_spo2(100) == "ok"

    def test_eval_temp_crit_high(self):
        """Temp >= 39 returns crit."""
        assert eval_temp(39) == "crit"
        assert eval_temp(40) == "crit"

    def test_eval_temp_crit_low(self):
        """Temp < 35 returns crit."""
        assert eval_temp(34) == "crit"
        assert eval_temp(34.9) == "crit"

    def test_eval_temp_watch_high(self):
        """Temp >= 37.8 returns watch."""
        assert eval_temp(37.8) == "watch"
        assert eval_temp(38.5) == "watch"

    def test_eval_temp_watch_low(self):
        """Temp < 36 returns watch."""
        assert eval_temp(35.5) == "watch"
        assert eval_temp(35.9) == "watch"

    def test_eval_temp_ok(self):
        """Temp 36-37.7 returns ok."""
        assert eval_temp(36) == "ok"
        assert eval_temp(37) == "ok"
        assert eval_temp(37.7) == "ok"

    def test_eval_radiation_crit(self):
        """Radiation >= 600 * 0.8 = 480 returns crit."""
        assert eval_radiation(480) == "crit"
        assert eval_radiation(500) == "crit"
        assert eval_radiation(600) == "crit"

    def test_eval_radiation_watch(self):
        """Radiation >= 50 returns watch."""
        assert eval_radiation(50) == "watch"
        assert eval_radiation(100) == "watch"
        assert eval_radiation(479) == "watch"

    def test_eval_radiation_ok(self):
        """Radiation < 50 returns ok."""
        assert eval_radiation(0) == "ok"
        assert eval_radiation(25) == "ok"
        assert eval_radiation(49) == "ok"

    def test_evaluate_vitals_full_per_metric(self):
        """evaluate_vitals returns per-metric status and overall."""
        v = VitalsReading(
            heartRate=70, bpSys=120, bpDia=80, spo2=98, tempC=37.0,
            stressIndex=30, radiationMSv=10
        )
        result = evaluate_vitals(v)

        assert "per" in result
        assert "overall" in result
        assert result["per"]["heartRate"] == "ok"
        assert result["per"]["bp"] == "ok"
        assert result["per"]["bpStage"] == "normal"
        assert result["per"]["spo2"] == "ok"
        assert result["per"]["temp"] == "ok"
        assert result["per"]["radiation"] == "ok"
        assert result["per"]["stress"] == "ok"
        assert result["overall"] == "ok"

    def test_evaluate_vitals_overall_crit_from_hr(self):
        """Overall is crit when HR is crit."""
        v = VitalsReading(
            heartRate=35, bpSys=120, bpDia=80, spo2=98, tempC=37.0,
            stressIndex=30, radiationMSv=10
        )
        result = evaluate_vitals(v)
        assert result["overall"] == "crit"

    def test_evaluate_vitals_overall_watch_from_bp(self):
        """Overall is watch when BP is watch."""
        v = VitalsReading(
            heartRate=70, bpSys=135, bpDia=85, spo2=98, tempC=37.0,
            stressIndex=30, radiationMSv=10
        )
        result = evaluate_vitals(v)
        assert result["overall"] == "watch"
        assert result["per"]["bpStage"] == "high-normal"