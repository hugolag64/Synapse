from pathlib import Path

from backend.state.store import DataStore


def test_datastore_cache_is_inside_persistent_data_directory():
    assert Path(DataStore.CACHE_FILE).parent.name == "data"
