from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_DIR = ROOT / "schema"
DATA_DIR = ROOT / "data"
SEED_DIR = DATA_DIR / "seed"
SOURCES_DIR = DATA_DIR / "sources"
CACHE_DIR = SOURCES_DIR / "cache"
EXTRACTED_DIR = DATA_DIR / "extracted"
BUILD_DIR = DATA_DIR / "build"
