"""Pydantic model validation tests for models.py."""
import pytest
from pydantic import ValidationError

from models import Astronaut, VitalsReading, AdviceRequest, AdviceResponse


def test_astronaut_valid():
    """Valid astronaut creates successfully."""
    a = Astronaut(id="a1", name="Mara Ibáñez", role="Commander")
    assert a.id == "a1"
    assert a.name == "Mara Ibáñez"
    assert a.role == "Commander"


def test_astronaut_invalid_id_rejected():
    """Astronaut id with special chars rejected."""
    with pytest.raises(ValidationError):
        Astronaut(id="a!1", name="Test", role="Pilot")


def test_astronaut_empty_id_rejected():
    """Empty astronaut id rejected."""
    with pytest.raises(ValidationError):
        Astronaut(id="", name="Test", role="Pilot")


def test_astronaut_name_stripped_and_sanitized():
    """Astronaut name is stripped of HTML."""
    a = Astronaut(id="a1", name="<script>alert('x')</script>Mara ", role="Commander")
    assert a.name == "Mara"


def test_vitals_reading_valid():
    """Valid vitals reading creates successfully."""
    v = VitalsReading(heartRate=72, bpSys=120, bpDia=80, spo2=98, tempC=36.5, stressIndex=30)
    assert v.heartRate == 72


def test_vitals_reading_heart_rate_out_of_range_rejected():
    """Heart rate outside [20, 220] rejected."""
    with pytest.raises(ValidationError):
        VitalsReading(heartRate=10, bpSys=120, bpDia=80, spo2=98, tempC=36.5, stressIndex=30)

    with pytest.raises(ValidationError):
        VitalsReading(heartRate=300, bpSys=120, bpDia=80, spo2=98, tempC=36.5, stressIndex=30)


def test_vitals_reading_spo2_out_of_range_rejected():
    """SpO2 outside [50, 100] rejected."""
    with pytest.raises(ValidationError):
        VitalsReading(heartRate=72, bpSys=120, bpDia=80, spo2=40, tempC=36.5, stressIndex=30)


def test_vitals_reading_temp_out_of_range_rejected():
    """Temperature outside [30, 43] rejected."""
    with pytest.raises(ValidationError):
        VitalsReading(heartRate=72, bpSys=120, bpDia=80, spo2=98, tempC=50, stressIndex=30)


def test_vitals_reading_stress_index_out_of_range_rejected():
    """Stress index outside [0, 100] rejected."""
    with pytest.raises(ValidationError):
        VitalsReading(heartRate=72, bpSys=120, bpDia=80, spo2=98, tempC=36.5, stressIndex=150)


def test_vitals_reading_defaults():
    """Optional fields have defaults."""
    v = VitalsReading(heartRate=72, bpSys=120, bpDia=80, spo2=98, tempC=36.5, stressIndex=30)
    assert v.radiationMSv == 0
    assert v.hrv is None


def test_advice_request_valid():
    """Valid AdviceRequest creates successfully."""
    req = AdviceRequest(
        astronaut=Astronaut(id="a1", name="Mara", role="Commander"),
        vitals=VitalsReading(heartRate=72, bpSys=120, bpDia=80, spo2=98, tempC=36.5, stressIndex=30),
        radiationMSv=0, alerts=[]
    )
    assert req.astronaut.id == "a1"


def test_advice_response_valid():
    """Valid AdviceResponse creates successfully."""
    resp = AdviceResponse(advice="Stay hydrated.", source="local")
    assert resp.advice == "Stay hydrated."
    assert resp.source == "local"


def test_vitals_reading_extra_fields_ignored():
    """Extra fields in VitalsReading are ignored (extra='ignore')."""
    v = VitalsReading(heartRate=72, bpSys=120, bpDia=80, spo2=98, tempC=36.5, stressIndex=30, extra_field="ignored")
    assert v.heartRate == 72