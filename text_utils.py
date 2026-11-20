# Copyright (c) 2026 Kurmanji-TTS Team. All Rights Reserved.
# Proprietary and Confidential. Unauthorized copying, distribution, or modification
# of this file, via any medium, is strictly prohibited.

"""Kurmanji (Hawar Latin) text normalization, validation, and linguistic helpers."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config import get_app_root
from locales import msg

KURMANJI_SPECIAL_CHARS = ("Ç", "ç", "Ê", "ê", "Î", "î", "Ş", "ş", "Û", "û", "X", "x", "W", "w")
KURMANJI_DIACRITIC_BASES = ("Ç", "ç", "Ê", "ê", "Î", "î", "Ş", "ş", "Û", "û")

SAMPLE_KURMANJI_TEXTS: Dict[str, str] = {
    "Silav (Short)": "Rojbaş! Tu çawa yî? Ez baş im, spas.",
    "Tîpên Taybet (Hawar)": "Çiya, êvar, îro, şev, ûr, xanî û welat di zimanê kurdî de pir girîng in.",
    "Nivîsa Navîn (Medium)": (
        "Zimanê kurdî yek ji zimanên kevnar ên Rojhilata Navîn e. "
        "Zaravayê kurmancî bi alfabeya latînî ya Hawarê tê nivîsandin û xwedî wêjeyeke dewlemend e."
    ),
    "Paragrafa Dirêj (Long)": (
        "Teknolojiya veguherandina nivîsê bo deng (Text-to-Speech) ji bo parastin û pêşxistina zimanê kurdî "
        "gaveke gelekî girîng e. Ev bername bi awayekî serbixwe li ser komputerê kar dike û bêyî înternetê "
        "dikare hevokên dirêj û kurt bi dengekî xwezayî û zelal bixwîne. Em hêvî dikin ku ev projeya zanîngehê "
        "ji bo xwendekar û lêkolîneran bibe alîkariyeke mezin."
    ),
}

SAMPLE_ARABIC_TEXTS: Dict[str, str] = {
    "تحية قصيرة": "مرحباً، كيف حالك اليوم؟ أنا بخير، شكراً لك.",
    "نص متوسط": (
        "اللغة العربية الفصحى لغة غنية وتاريخية، ويستخدمها ملايين الناس في مختلف أنحاء العالم. "
        "يعمل هذا التطبيق محلياً على المعالج دون اتصال بالإنترنت."
    ),
    "فقرات طويلة": (
        "يُعد تحويل النص إلى كلام من التقنيات المهمة التي تساعد على حفظ اللغات ونشرها. "
        "يدعم هذا البرنامج اللغة الكورمانجية والعربية الفصحى، ويوفر تحولاً سريعاً وواضحاً "
        "دون الحاجة إلى خادم خارجي أو اتصال بالشبكة."
    ),
    "أرقام وتشكيل": "في عام 2026، قرأ الطالبُ النصَّ المُشكَّلَ بوضوحٍ تامّ.",
}

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b-\u200f\ufeff]")
_MULTI_SPACE_RE = re.compile(r"[ \t\f\v]+")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?؛؟])\s+")


@dataclass(frozen=True)
class TextAnalysis:
    """Metrics describing a normalized Kurmanji input text."""

    normalized_text: str
    char_count: int
    word_count: int
    line_count: int
    special_chars_found: Tuple[str, ...]


def normalize_kurmanji_text(raw_text: str) -> str:
    """Normalize Kurmanji text safely without altering meaning or punctuation."""
    if not raw_text:
        return ""

    # 1. Canonical NFC composition for Kurmanji Hawar characters
    text = unicodedata.normalize("NFC", raw_text)

    # 2. Standardize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 3. Remove invisible control characters
    text = _CONTROL_CHARS_RE.sub("", text)

    # 4. Clean horizontal whitespace per line without deleting punctuation
    cleaned_lines: List[str] = []
    for line in text.split("\n"):
        cleaned = _MULTI_SPACE_RE.sub(" ", line).strip()
        cleaned_lines.append(cleaned)

    text = "\n".join(cleaned_lines)
    text = _MULTI_NEWLINE_RE.sub("\n\n", text).strip()
    return text


def analyze_text(raw_text: str) -> TextAnalysis:
    """Return normalized text along with character, word, and Hawar letter statistics."""
    normalized = normalize_kurmanji_text(raw_text)
    if not normalized:
        return TextAnalysis(
            normalized_text="",
            char_count=0,
            word_count=0,
            line_count=0,
            special_chars_found=(),
        )

    words = [w for w in normalized.split() if w]
    lines = [ln for ln in normalized.split("\n") if ln.strip()]
    found = tuple(ch for ch in KURMANJI_SPECIAL_CHARS if ch in normalized)
    return TextAnalysis(
        normalized_text=normalized,
        char_count=len(normalized),
        word_count=len(words),
        line_count=len(lines),
        special_chars_found=found,
    )


def validate_kurmanji_input(raw_text: str, max_chars: int = 5000) -> Tuple[bool, str, str]:
    """Validate and normalize user input before sending it to the TTS engine."""
    normalized = normalize_kurmanji_text(raw_text)
    if not normalized:
        return False, "", msg("validate_empty")

    if len(normalized) > max_chars:
        return (
            False,
            normalized,
            msg("validate_too_long", count=len(normalized), maximum=max_chars),
        )

    if not any(ch.isalnum() for ch in normalized):
        return (
            False,
            normalized,
            msg("validate_symbols"),
        )

    return True, normalized, ""


def split_long_text(normalized_text: str, max_chunk_chars: int = 400) -> List[str]:
    """Split long paragraphs cleanly on sentence boundaries if chunking is requested."""
    if len(normalized_text) <= max_chunk_chars:
        return [normalized_text] if normalized_text else []

    chunks: List[str] = []
    for paragraph in normalized_text.split("\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) <= max_chunk_chars:
            chunks.append(paragraph)
            continue

        sentences = _SENTENCE_SPLIT_RE.split(paragraph)
        current = ""
        for sentence in sentences:
            if not current:
                current = sentence
            elif len(current) + 1 + len(sentence) <= max_chunk_chars:
                current = f"{current} {sentence}"
            else:
                chunks.append(current)
                current = sentence
        if current:
            chunks.append(current)
    return chunks


# ---------------------------------------------------------------------------
# Pronunciation preparation (eSpeak NG "ku" friendly text)
# ---------------------------------------------------------------------------

_ONES: Dict[int, str] = {
    1: "yek", 2: "du", 3: "sê", 4: "çar", 5: "pênc",
    6: "şeş", 7: "heft", 8: "heşt", 9: "neh",
}

_TEENS: Dict[int, str] = {
    10: "deh", 11: "yanzdeh", 12: "dwanzdeh", 13: "sêzdeh",
    14: "çardeh", 15: "panzdeh", 16: "şanzdeh", 17: "hevdeh",
    18: "hejdeh", 19: "nozdeh",
}

_TENS: Dict[int, str] = {
    2: "bîst", 3: "sî", 4: "çil", 5: "pêncî",
    6: "şêst", 7: "heftê", 8: "heştê", 9: "nod",
}

_HUNDREDS: Dict[int, str] = {
    1: "sed", 2: "dused", 3: "sêsed", 4: "çarsed", 5: "pêncsed",
    6: "şeşsed", 7: "heftsed", 8: "heştsed", 9: "nehsed",
}

_LETTER_SPELLINGS: Dict[str, str] = {
    "A": "ey", "B": "bî", "C": "sî", "D": "dî", "E": "î", "F": "ef",
    "G": "cî", "H": "eyç", "I": "ay", "J": "cey", "K": "key", "L": "el",
    "M": "em", "N": "en", "O": "o", "P": "pî", "Q": "kyû", "R": "ar",
    "S": "es", "T": "tî", "U": "yû", "V": "vî", "W": "dabilyû",
    "X": "eks", "Y": "way", "Z": "zê",
}

_DEFAULT_PRONUNCIATION_DICT: Dict[str, str] = {
    "TTS": "tî tî es",
    "Text-to-Speech": "tekst tu spîç",
    "WAV": "dabilyû ey vî",
    "CPU": "sî pî yû",
    "Kurmanji": "kurmancî",
}

_ACRONYM_RE = re.compile(r"\b[A-Z]{2,}\b")
_PERCENT_RE = re.compile(r"\b(\d{1,6})\s*%")
_NUMBER_RE = re.compile(r"\b(\d{1,6})\b")


def kurmanji_number_to_words(n: int) -> str:
    """Spell an integer 0..999999 in Kurmanji (e.g. 2026 -> du hezar û bîst û şeş)."""
    if isinstance(n, bool) or not isinstance(n, int):
        raise TypeError("n must be an integer")
    if not 0 <= n <= 999_999:
        raise ValueError("n must be between 0 and 999999")
    if n == 0:
        return "sifir"

    parts: List[str] = []
    thousands, rest = divmod(n, 1000)
    if thousands:
        parts.append("hezar" if thousands == 1 else f"{kurmanji_number_to_words(thousands)} hezar")

    if rest:
        hundreds, remainder = divmod(rest, 100)
        if hundreds:
            parts.append(_HUNDREDS[hundreds])
        if remainder:
            if remainder < 10:
                parts.append(_ONES[remainder])
            elif remainder < 20:
                parts.append(_TEENS[remainder])
            else:
                tens, ones = divmod(remainder, 10)
                parts.append(_TENS[tens] if not ones else f"{_TENS[tens]} û {_ONES[ones]}")

    return " û ".join(parts)


def _load_pronunciation_dict(dict_path: Optional[Path] = None) -> Dict[str, str]:
    """Load the external pronunciation dictionary, creating a seeded one if absent."""
    target = Path(dict_path) if dict_path is not None else (
        get_app_root() / "models" / "pronunciation_dict.json"
    )
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(_DEFAULT_PRONUNCIATION_DICT, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return dict(_DEFAULT_PRONUNCIATION_DICT)
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return dict(_DEFAULT_PRONUNCIATION_DICT)
    if not isinstance(raw, dict):
        return dict(_DEFAULT_PRONUNCIATION_DICT)
    return {str(k): str(v) for k, v in raw.items() if str(v).strip()}


def _spell_acronym(match: "re.Match[str]") -> str:
    return " ".join(_LETTER_SPELLINGS.get(ch, ch.lower()) for ch in match.group(0))


def prepare_text_for_tts(
    normalized_text: str,
    dict_path: Optional[Path] = None,
    voice_lang: str = "ku",
) -> str:
    """Turn displayed text into a phonetically friendlier TTS string.

    ``ku`` keeps the existing Kurmanji pronunciation dictionary and number
    spelling. ``ar`` preserves Arabic text and its diacritics verbatim (NFC)
    and leaves digits to the Arabic eSpeak NG voice inside Piper.

    The displayed text is never modified: this output is only what gets piped
    to the eSpeak NG / Piper engine.
    """
    if not normalized_text:
        return ""

    if voice_lang == "ar":
        # Do not strip tashkeel and do not rewrite numbers for the Arabic voice.
        return unicodedata.normalize("NFC", normalized_text)

    text = normalized_text

    # 1. External pronunciation overrides (whole-word, case-insensitive).
    replacements = _load_pronunciation_dict(dict_path)
    for key in sorted(replacements, key=len, reverse=True):
        pattern = re.compile(r"(?<!\w)" + re.escape(key) + r"(?!\w)", re.IGNORECASE)
        text = pattern.sub(replacements[key], text)

    # 2. Percentages and plain integers -> spoken Kurmanji words.
    text = _PERCENT_RE.sub(
        lambda m: f"ji sedî {kurmanji_number_to_words(int(m.group(1)))}", text
    )
    text = _NUMBER_RE.sub(
        lambda m: kurmanji_number_to_words(int(m.group(1))), text
    )

    # 3. Any remaining ALL-CAPS English acronym -> spoken letter names.
    text = _ACRONYM_RE.sub(_spell_acronym, text)
    return text


# ---------------------------------------------------------------------------
# sherpa-onnx Meta MMS friendly text (single-character vocabularies)
# ---------------------------------------------------------------------------

_MMS_TOKEN_DIRS = {"kmr": "mms_kmr", "ar": "mms_ara"}


def _mms_allowed_chars(voice_lang: str) -> frozenset[str]:
    """Read the single-character alphabet from the installed MMS tokens.txt."""
    subdir = _MMS_TOKEN_DIRS.get(voice_lang, "mms_kmr")
    tokens_path = get_app_root() / "models" / subdir / "tokens.txt"
    chars: set[str] = set()
    try:
        for line in tokens_path.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            token = " " if len(parts) == 1 else parts[0]
            if len(token) == 1:
                chars.add(token)
    except (OSError, UnicodeError):
        pass
    if chars:
        return frozenset(chars)
    return frozenset(" abcdefghijklmnopqrstuvwxyzçêîşû'-" if voice_lang == "kmr" else " ابلت")


def prepare_text_for_mms(normalized_text: str, voice_lang: str) -> str:
    """Normalize text for a Meta MTS character-vocabulary voice.

    ``kmr`` spells numbers out in Kurmanji; ``ar`` keeps Arabic digits and
    diacritics. Characters absent from the model's tokens.txt (parentheses,
    stray punctuation, etc.) are removed so sherpa does not warn or split.
    """
    if not normalized_text:
        return ""
    lang = voice_lang if voice_lang in _MMS_TOKEN_DIRS else "kmr"
    text = unicodedata.normalize("NFC", normalized_text)

    if lang == "kmr":
        # sherpa's built-in lowercasing is ASCII-only; normalize here instead.
        text = text.lower()
        text = _PERCENT_RE.sub(
            lambda m: f"ji sedî {kurmanji_number_to_words(int(m.group(1)))}", text
        )
        text = _NUMBER_RE.sub(
            lambda m: kurmanji_number_to_words(int(m.group(1))), text
        )

    allowed = _mms_allowed_chars(lang)
    return "".join(ch for ch in text if ch in allowed)
