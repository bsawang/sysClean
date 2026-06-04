import json
from pathlib import Path

_I18N_DIR = Path(__file__).parent
_cache: dict[str, dict[str, str]] = {}

def _load_lang(lang: str) -> dict[str, str]:
    if lang in _cache:
        return _cache[lang]
    file_path = _I18N_DIR / f"{lang}.json"
    if not file_path.exists():
        file_path = _I18N_DIR / "zh.json"
    with open(file_path, "r", encoding="utf-8") as f:
        _cache[lang] = json.load(f)
    return _cache[lang]

def get_text(key: str, lang: str = "zh", **kwargs) -> str:
    pack = _load_lang(lang)
    text = pack.get(key, key)
    if kwargs:
        text = text.format(**kwargs)
    return text

def get_all_texts(lang: str = "zh") -> dict:
    return _load_lang(lang)
