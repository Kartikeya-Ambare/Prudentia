from backend.config import get_config


def test_config_loads_and_substitutes_env():
    cfg = get_config()
    assert cfg.optimizer.strategy == "black_litterman"
    assert cfg.download.workers >= 8
    # DB_HOST is unset in this dev environment -> should resolve to empty string, not "${DB_HOST}"
    assert cfg.database.host == ""


def test_config_node_get_default():
    cfg = get_config()
    assert cfg.database.get("nonexistent_key", "fallback") == "fallback"
