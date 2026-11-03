import sys
from pathlib import Path

import pytest
import yaml

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))


@pytest.fixture
def cfg():
    with open(KOK / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def s_cfg(cfg):
    return cfg["strateji"]


@pytest.fixture
def r_cfg(cfg):
    return cfg["risk"]
