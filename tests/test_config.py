from sequoia_x.core.config import Settings

def test_settings_load():
    s = Settings(tickflow_api_key="test_key")
    assert s.db_path == "data/sequoia_v2.db"
    assert s.start_date == "2024-01-01"
