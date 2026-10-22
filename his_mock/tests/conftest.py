"""Unit tests drive the JSON APIs directly: the test apps open them (a live HIMS needs a login or the integration token)."""
import os

os.environ.setdefault("TB_HIS_MOCK_OPEN_API", "1")
