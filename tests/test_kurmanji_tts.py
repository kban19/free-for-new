"""Comprehensive automated verification suite for Kurmanji-TTS."""

from __future__ import annotations

import ast
import array
import json
import math
from dataclasses import asdict
from typing import Dict
import platform
import sys
import tempfile
import time
import unicodedata
import unittest
import wave
from pathlib import Path

try:  # resource is POSIX-only; keep the suite runnable on Windows too
    import resource

    def _peak_rss_mb() -> float:
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
except ImportError:  # pragma: no cover - Windows fallback
    def _peak_rss_mb() -> float:
        return 0.0

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _wav_rms(path: Path) -> float:
    """Simple PCM loudness check used by the Arabic WAV smoke test."""
    with wave.open(str(path), "rb") as wf:
        raw = wf.readframes(wf.getnframes())
    samples = array.array("h", raw)
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples))

from locales import (
    SUPPORTED_LANGUAGES,
    TRANSLATIONS,
    is_rtl,
    set_current_language,
    tr,
)
from audio_player import (
    AudioSessionManager,
    InAppAudioPlayer,
    PlaybackState,
    format_seconds,
    inspect_wav,
)
from config import (
    ENGINE_PROFILES,
    AppSettings,
    discover_default_model,
    model_path_for_profile,
)
from text_utils import (
    KURMANJI_SPECIAL_CHARS,
    SAMPLE_KURMANJI_TEXTS,
    analyze_text,
    kurmanji_number_to_words,
    normalize_kurmanji_text,
    prepare_text_for_mms,
    prepare_text_for_tts,
    split_long_text,
    validate_kurmanji_input,
)
from tts_engine import (
    KurmanjiTTSEngine,
    TTSEngineError,
    UnifiedTTSEngine,
    parse_model_metadata,
)

try:  # sherpa-onnx wheels are unavailable for the MSYS2 Python in .venv
    import sherpa_onnx  # noqa: F401

    SHERPA_AVAILABLE = True
except Exception:  # pragma: no cover - depends on the interpreter
    SHERPA_AVAILABLE = False


class TestKurmanjiTextProcessing(unittest.TestCase):
    def test_unicode_nfc_normalization_and_special_chars(self) -> None:
        nfd_sample = unicodedata.normalize("NFD", "Çiya, Êvar, Îro, Şev, Ûr, Xanî, Welat! ç ê î ş û x w")
        normalized = normalize_kurmanji_text(nfd_sample)
        self.assertTrue(unicodedata.is_normalized("NFC", normalized))
        for ch in KURMANJI_SPECIAL_CHARS:
            self.assertIn(ch, normalized, f"Missing Kurmanji character: {ch}")

    def test_whitespace_and_punctuation_preserved(self) -> None:
        raw = "  Rojbaş!   Tu   çawa   yî?\r\n\r\n\r\nEz baş im; spas: 2026.  "
        cleaned = normalize_kurmanji_text(raw)
        self.assertEqual(cleaned, "Rojbaş! Tu çawa yî?\n\nEz baş im; spas: 2026.")

    def test_validation_and_analysis(self) -> None:
        ok, _, err = validate_kurmanji_input("   \n\t  ")
        self.assertFalse(ok)
        self.assertTrue(len(err) > 0)

        ok_sym, _, _ = validate_kurmanji_input("... !!! ???")
        self.assertFalse(ok_sym)

        ok_long, _, _ = validate_kurmanji_input("a" * 5001, max_chars=5000)
        self.assertFalse(ok_long)

        analysis = analyze_text(SAMPLE_KURMANJI_TEXTS["Tîpên Taybet (Hawar)"])
        self.assertGreater(analysis.char_count, 40)
        self.assertGreater(analysis.word_count, 10)
        self.assertIn("Ç", analysis.special_chars_found)
        self.assertIn("ş", analysis.special_chars_found)

    def test_long_text_sentence_splitting(self) -> None:
        long_text = (SAMPLE_KURMANJI_TEXTS["Paragrafa Dirêj (Long)"] + " ") * 4
        chunks = split_long_text(long_text.strip(), max_chunk_chars=300)
        self.assertGreater(len(chunks), 2)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 300)


class TestConfigAndEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="kurmanji_test_"))
        self.models_dir = self.tmp_dir / "models"
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.model_path = self.models_dir / "kurmanci.onnx"
        self.config_path = self.models_dir / "kurmanci.onnx.json"

        self.model_path.write_bytes(b"ONNX_DUMMY_HEADER_" + (b"0" * 2048))
        speaker_map = {f"spk_{i}": i for i in range(90)}
        cfg_data = {
            "audio": {"sample_rate": 22050, "quality": "medium"},
            "espeak": {"voice": "ku"},
            "num_speakers": 90,
            "speaker_id_map": speaker_map,
        }
        self.config_path.write_text(json.dumps(cfg_data), encoding="utf-8")

        mock_script = PROJECT_ROOT / "tests" / "mock_piper.py"
        if platform.system() == "Windows":
            # Windows cannot execute a .py file directly via CreateProcess.
            # Wrap it in a .cmd launcher that forwards all args and stdin.
            launcher = self.tmp_dir / "mock_piper.cmd"
            launcher.write_text(
                '@echo off\r\n"{}" "{}" %*\r\n'.format(sys.executable, mock_script),
                encoding="utf-8",
            )
            self.mock_piper = launcher
        else:
            mock_script.chmod(mock_script.stat().st_mode | 0o111)
            self.mock_piper = mock_script

    def test_settings_persistence_and_model_discovery(self) -> None:
        canonical = self.models_dir / "model.onnx"
        canonical.write_bytes(self.model_path.read_bytes())
        discovered = discover_default_model(self.models_dir)
        self.assertEqual(discovered, canonical)

        cfg_file = self.tmp_dir / "settings.json"
        s1 = AppSettings(
            model_path=str(self.model_path),
            piper_path=str(self.mock_piper),
            default_speaker_id=54,
            speech_speed=1.25,
            theme_mode="light",
        )
        s1.save(cfg_file)
        s2 = AppSettings.load(cfg_file)
        self.assertEqual(s2.default_speaker_id, 54)
        self.assertEqual(s2.speech_speed, 1.25)
        self.assertEqual(s2.length_scale, 0.8)
        self.assertEqual(s2.theme_mode, "light")

    def test_bundled_model_paths_and_discovery(self) -> None:
        canonical = self.models_dir / "model.onnx"
        canonical.write_bytes(b"ONNX_DUMMY_HEADER_" + (b"0" * 2048))
        self.assertEqual(discover_default_model(self.models_dir), canonical)
        self.assertEqual(
            model_path_for_profile(self.tmp_dir, "mms_kmr").as_posix(),
            (self.tmp_dir / "models" / "mms_kmr" / "model.onnx").as_posix(),
        )
        self.assertEqual(
            model_path_for_profile(self.tmp_dir, "mms_ara").as_posix(),
            (self.tmp_dir / "models" / "mms_ara" / "model.onnx").as_posix(),
        )
        self.assertEqual(
            model_path_for_profile(self.tmp_dir, "piper_kmr").name, "model.onnx"
        )

    def test_engine_profile_is_persisted_and_validated(self) -> None:
        cfg_file = self.tmp_dir / "voice_settings.json"
        AppSettings(engine_profile="mms_ara").save(cfg_file)
        self.assertEqual(AppSettings.load(cfg_file).engine_profile, "mms_ara")
        self.assertEqual(AppSettings(engine_profile="xx").engine_profile, "piper_kmr")

    def test_unified_engine_profile_routing(self) -> None:
        engine = UnifiedTTSEngine(
            piper_path=self.mock_piper,
            model_path=self.model_path,
            root=PROJECT_ROOT,
            engine_profile="piper_kmr",
        )
        self.assertEqual(engine.profile, "piper_kmr")
        for profile in ENGINE_PROFILES:
            self.assertEqual(engine.set_profile(profile), profile)
            self.assertEqual(engine.profile, profile)
        self.assertEqual(engine.set_profile("unknown"), "piper_kmr")
        engine.close()

    @unittest.skipUnless(
        SHERPA_AVAILABLE
        and (PROJECT_ROOT / "models" / "mms_kmr" / "model.onnx").exists()
        and (PROJECT_ROOT / "models" / "mms_ara" / "model.onnx").exists(),
        "sherpa-onnx or bundled MMS models unavailable for this interpreter",
    )
    def test_mms_profiles_generate_non_silent_wav(self) -> None:
        session = AudioSessionManager(session_dir=self.tmp_dir / "mms_audio")
        engine = UnifiedTTSEngine(
            piper_path=self.mock_piper,
            model_path=self.model_path,
            root=PROJECT_ROOT,
            engine_profile="mms_kmr",
        )
        cases = (
            ("mms_kmr", prepare_text_for_mms("Rojbaş! Çiya, êvar, îro.", "kmr")),
            ("mms_ara", prepare_text_for_mms("مرحباً، كيف حالك؟ 2026", "ar")),
        )
        for profile, text in cases:
            engine.set_profile(profile)
            status = engine.check_status()
            self.assertTrue(status.ready, status.message)
            self.assertEqual(status.metadata.default_speaker_id, 0)
            out = session.allocate_output_path()
            result = engine.synthesize(text, out, speaker_id=0)
            self.assertEqual(result.mode_used, "sherpa-onnx-cpu")
            self.assertEqual(result.sample_rate, 16000)
            self.assertGreater(_wav_rms(result.wav_path), 100.0)
        engine.close()
        session.shutdown()

    def test_v2_settings_migrate_to_speech_speed(self) -> None:
        cfg_file = self.tmp_dir / "legacy_settings.json"
        cfg_file.write_text(
            json.dumps({
                "model_path": str(self.model_path),
                "piper_path": str(self.mock_piper),
                "length_scale": 2.0,
                "noise_scale": 0.35,
                "noise_w": 0.45,
                "settings_version": 2,
            }),
            encoding="utf-8",
        )
        legacy = AppSettings.load(cfg_file)
        self.assertEqual(legacy.speech_speed, 0.5)
        self.assertEqual(legacy.settings_version, 4)
        self.assertEqual(legacy.ui_language, "ar")
        self.assertNotIn("length_scale", asdict(legacy))

    def test_speech_speed_maps_to_inverse_length_scale(self) -> None:
        self.assertEqual(AppSettings(speech_speed=0.5).length_scale, 2.0)
        self.assertEqual(AppSettings(speech_speed=1.0).length_scale, 1.0)
        self.assertEqual(AppSettings(speech_speed=1.5).length_scale, 0.667)

        session = AudioSessionManager(session_dir=self.tmp_dir / "speed_audio")
        engine = KurmanjiTTSEngine(
            piper_path=self.mock_piper,
            model_path=self.model_path,
            use_persistent_process=False,
        )
        durations: Dict[int, float] = {}
        for speed in (0.5, 1.5):
            settings = AppSettings(speech_speed=speed)
            result = engine.synthesize(
                text=SAMPLE_KURMANJI_TEXTS["Silav (Short)"],
                output_wav=session.allocate_output_path(),
                speaker_id=54,
                length_scale=settings.length_scale,
            )
            durations[int(speed * 10)] = result.duration_seconds
        self.assertGreater(durations[5], durations[15] * 2.5)
        engine.close()
        session.shutdown()

    def test_metadata_parsing_and_default_speaker_54(self) -> None:
        meta = parse_model_metadata(self.model_path, preferred_speaker=54)
        self.assertEqual(meta.sample_rate, 22050)
        self.assertEqual(meta.espeak_voice, "ku")
        self.assertEqual(meta.num_speakers, 90)
        self.assertEqual(meta.default_speaker_id, 54)

    def test_speaker_metadata_labels_and_default(self) -> None:
        metadata = [
            {"speaker_id": 0, "perceived_voice": "F", "display_name": "Speaker 0", "is_default": False},
            {"speaker_id": 54, "perceived_voice": "M", "display_name": "Speaker 54", "is_default": True},
        ]
        (self.models_dir / "speaker_metadata.json").write_text(
            json.dumps(metadata), encoding="utf-8"
        )
        meta = parse_model_metadata(self.model_path, preferred_speaker=54)
        labels = dict(meta.speakers)
        self.assertEqual(labels[54], "Speaker 54 (M) ★")
        self.assertEqual(labels[0], "Speaker 0 (F)")
        self.assertEqual(meta.default_speaker_id, 54)
        self.assertNotIn("spk_", labels[0])
        self.assertNotIn("spk_", labels[54])

    def test_oneshot_and_persistent_synthesis_with_speakers(self) -> None:
        session = AudioSessionManager(session_dir=self.tmp_dir / "audio_sessions")
        engine = KurmanjiTTSEngine(
            piper_path=self.mock_piper,
            model_path=self.model_path,
            preferred_speaker=54,
            use_persistent_process=False,
        )
        status = engine.check_status()
        self.assertTrue(status.ready)

        out1 = session.allocate_output_path()
        res1 = engine.synthesize(
            text=SAMPLE_KURMANJI_TEXTS["Tîpên Taybet (Hawar)"],
            output_wav=out1,
            speaker_id=54,
        )
        self.assertEqual(res1.mode_used, "oneshot-cli")
        self.assertEqual(res1.speaker_id, 54)
        self.assertGreater(res1.duration_seconds, 0.5)
        info1 = session.register_generated_wav(res1.wav_path)
        self.assertEqual(info1.sample_rate, 22050)
        self.assertEqual(info1.channels, 1)

        engine.update_paths(
            piper_path=self.mock_piper,
            model_path=self.model_path,
            preferred_speaker=54,
            use_persistent_process=True,
        )
        for sid, sample_key in [
            (54, "Silav (Short)"),
            (0, "Nivîsa Navîn (Medium)"),
            (89, "Paragrafa Dirêj (Long)"),
        ]:
            out_wav = session.allocate_output_path()
            res = engine.synthesize(
                text=SAMPLE_KURMANJI_TEXTS[sample_key],
                output_wav=out_wav,
                speaker_id=sid,
            )
            self.assertEqual(res.mode_used, "persistent-json-cli")
            self.assertEqual(res.speaker_id, sid)
            wav_meta = session.register_generated_wav(res.wav_path)
            self.assertGreater(wav_meta.file_size_bytes, 44)

        session.set_state(PlaybackState.PLAYING)
        self.assertEqual(session.state, PlaybackState.PLAYING)
        session.set_state(PlaybackState.PAUSED)
        self.assertEqual(session.state, PlaybackState.PAUSED)
        session.set_state(PlaybackState.STOPPED)
        self.assertEqual(format_seconds(65.4), "01:05")

        exported = session.export_wav(self.tmp_dir / "exports" / "final_kurmanji")
        self.assertTrue(exported.exists())
        self.assertEqual(exported.suffix, ".wav")
        self.assertEqual(inspect_wav(exported).sample_rate, 22050)

        engine.close()
        session.shutdown()

    def test_error_handling_missing_model_and_invalid_speaker(self) -> None:
        engine = KurmanjiTTSEngine(
            piper_path=self.mock_piper,
            model_path=self.tmp_dir / "nonexistent.onnx",
        )
        status = engine.check_status()
        self.assertFalse(status.ready)

        valid_engine = KurmanjiTTSEngine(
            piper_path=self.mock_piper,
            model_path=self.model_path,
            use_persistent_process=False,
        )
        with self.assertRaises(TTSEngineError):
            valid_engine.synthesize("Silav", self.tmp_dir / "bad.wav", speaker_id=999)


class TestLocalization(unittest.TestCase):
    def test_all_languages_have_identical_complete_keys(self) -> None:
        base_keys = set(TRANSLATIONS["ar"])
        self.assertGreater(len(base_keys), 60)
        optional_parts = {
            "input_label_secondary",
            "settings_title_secondary",
            "model_label_secondary",
            "piper_label_middle",
            "piper_label_suffix",
        }
        for lang in SUPPORTED_LANGUAGES:
            self.assertEqual(set(TRANSLATIONS[lang]), base_keys, f"missing keys in {lang}")
            for key, value in TRANSLATIONS[lang].items():
                if key not in optional_parts:
                    self.assertTrue(value.strip(), f"empty translation {lang}/{key}")

    def test_rtl_direction_per_language(self) -> None:
        self.assertTrue(is_rtl("ar"))
        self.assertFalse(is_rtl("ku"))
        self.assertFalse(is_rtl("en"))

    def test_language_dropdown_uses_on_select_and_field_is_ltr(self) -> None:
        tree = ast.parse((PROJECT_ROOT / "main.py").read_text(encoding="utf-8"))
        select_handlers = 0
        text_field_ltr = False
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and node.attr == "on_select"
                and isinstance(node.ctx, ast.Store)
            ):
                select_handlers += 1
            if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "TextField":
                if any(
                    kw.arg == "rtl"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value is False
                    for kw in node.keywords
                ):
                    text_field_ltr = True
        self.assertGreaterEqual(select_handlers, 1)
        self.assertTrue(text_field_ltr)

    def test_arabic_bidi_isolates_and_ltr_containers(self) -> None:
        self.assertIn("\u2066Kurmanji-TTS\u2069", tr("ar", "settings_title"))
        self.assertIn("\u2066(.onnx)\u2069", tr("ar", "model_path_label"))
        self.assertIn("\u2066Piper\u2069", tr("ar", "piper_path_label"))
        self.assertIn("\u2066(CPU)\u2069", tr("ar", "settings_note"))
        self.assertTrue(tr("ar", "metric_rtf").startswith("\u2066RTF\u2069:"))

        source = (PROJECT_ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("ft.Container(content=text_input, rtl=False, expand=True)", source)
        self.assertIn("ft.Container(content=model_field, rtl=False, expand=True)", source)
        self.assertIn("ft.Container(content=piper_field, rtl=False, expand=True)", source)

    def test_settings_dialog_labels_are_separate_and_rtl_set(self) -> None:
        tree = ast.parse((PROJECT_ROOT / "main.py").read_text(encoding="utf-8"))
        dialog_fn = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "open_settings_dialog"
        )
        text_fields = [
            node for node in ast.walk(dialog_fn)
            if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "TextField"
        ]
        self.assertGreaterEqual(len(text_fields), 2)
        for call in text_fields:
            self.assertFalse(any(kw.arg == "label" for kw in call.keywords))
        dialog_calls = [
            node for node in ast.walk(dialog_fn)
            if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "AlertDialog"
        ]
        self.assertTrue(
            any(any(kw.arg == "rtl" for kw in call.keywords) for call in dialog_calls)
        )

    def test_key_translations(self) -> None:
        self.assertEqual(tr("ar", "model_ready"), "النموذج جاهز")
        self.assertEqual(tr("ku", "model_ready"), "Model amade ye")
        self.assertEqual(tr("en", "model_ready"), "Model Ready")
        self.assertEqual(
            tr("en", "save_ok", name="a.wav"), "Audio file saved successfully: a.wav"
        )
        self.assertEqual(tr("xx", "model_ready"), "النموذج جاهز")

    def test_ui_language_is_persisted(self) -> None:
        tmp_dir = Path(tempfile.mkdtemp(prefix="kurmanji_lang_"))
        cfg_file = tmp_dir / "settings.json"
        AppSettings(ui_language="en").save(cfg_file)
        loaded = AppSettings.load(cfg_file)
        self.assertEqual(loaded.ui_language, "en")
        self.assertEqual(loaded.settings_version, 4)
        self.assertEqual(AppSettings(ui_language="xx").ui_language, "ar")

    def test_engine_message_follows_selected_language(self) -> None:
        try:
            set_current_language("en")
            with self.assertRaises(TTSEngineError) as ctx:
                parse_model_metadata(Path("/no/such/model.onnx"))
            self.assertIn("not found", str(ctx.exception))
            set_current_language("ku")
            with self.assertRaises(TTSEngineError) as ctx2:
                parse_model_metadata(Path("/no/such/model.onnx"))
            self.assertIn("nehat dîtin", str(ctx2.exception))
        finally:
            set_current_language("ar")


class TestPronunciationPreparation(unittest.TestCase):
    def test_kurmanji_number_words(self) -> None:
        self.assertEqual(kurmanji_number_to_words(0), "sifir")
        self.assertEqual(kurmanji_number_to_words(15), "panzdeh")
        self.assertEqual(kurmanji_number_to_words(20), "bîst")
        self.assertEqual(kurmanji_number_to_words(2026), "du hezar û bîst û şeş")
        self.assertEqual(kurmanji_number_to_words(1000), "hezar")
        self.assertEqual(
            kurmanji_number_to_words(999999),
            "nehsed û nod û neh hezar û nehsed û nod û neh",
        )
        with self.assertRaises(ValueError):
            kurmanji_number_to_words(1_000_000)

    def test_external_dict_and_acronyms(self) -> None:
        tmp_dir = Path(tempfile.mkdtemp(prefix="kurmanji_dict_"))
        dict_path = tmp_dir / "pronunciation_dict.json"
        dict_path.write_text(
            json.dumps({"Kurmanji": "kurmancî", "TTS": "tî tî es", "WAV": "dabilyû ey vî"}, ensure_ascii=False),
            encoding="utf-8",
        )
        prepared = prepare_text_for_tts(
            "Kurmanji û tts bi WAV. Sala 2026, 50%.", dict_path
        )
        self.assertIn("kurmancî", prepared)
        self.assertIn("tî tî es", prepared)
        self.assertIn("dabilyû ey vî", prepared)
        self.assertIn("du hezar û bîst û şeş", prepared)
        self.assertIn("ji sedî pêncî", prepared)

    def test_default_dict_is_created(self) -> None:
        tmp_dir = Path(tempfile.mkdtemp(prefix="kurmanji_dict_new_"))
        target = tmp_dir / "models" / "pronunciation_dict.json"
        self.assertFalse(target.exists())
        prepare_text_for_tts("Silav", target)
        self.assertTrue(target.exists())
        self.assertIn("TTS", json.loads(target.read_text(encoding="utf-8")))

    def test_acronym_spelling(self) -> None:
        self.assertEqual(
            prepare_text_for_tts("PDF û USB"),
            "pî dî ef û yû es bî",
        )

    def test_arabic_voice_preserves_diacritics_and_digits(self) -> None:
        source = "الطالبُ قرأَ 2026 صفحةً."
        prepared = prepare_text_for_tts(source, voice_lang="ar")
        self.assertEqual(prepared, unicodedata.normalize("NFC", source))
        self.assertTrue(unicodedata.is_normalized("NFC", prepared))
        self.assertIn("\u064f", prepared)  # damma is still present
        self.assertIn("2026", prepared)  # digits are not spelled out

    def test_explicit_kurmanji_voice_keeps_legacy_behavior(self) -> None:
        prepared = prepare_text_for_tts("Sala 2026, 50%.", voice_lang="ku")
        self.assertIn("du hezar û bîst û şeş", prepared)
        self.assertIn("ji sedî pêncî", prepared)

    def test_mms_kmr_text_uses_hawar_and_strips_unknown_symbols(self) -> None:
        prepared = prepare_text_for_mms("Çiya (2026)! Tu çawa yî?", "kmr")
        self.assertIn("ç", prepared)
        self.assertIn("î", prepared)
        self.assertNotIn("(", prepared)
        self.assertNotIn(")", prepared)
        self.assertNotIn("!", prepared)
        self.assertNotIn("2026", prepared)
        self.assertIn("du hezar û bîst û şeş", prepared)

    def test_mms_ara_text_keeps_digits_and_filters_unknown_symbols(self) -> None:
        source = "مَرْحَباً (2026) بالعربية."
        prepared = prepare_text_for_mms(source, "ar")
        self.assertNotIn("(", prepared)
        self.assertNotIn(")", prepared)
        # The MMS Arabic character vocabulary has neither digits nor tashkeel.
        self.assertNotIn("2026", prepared)
        self.assertNotIn("\u064e", prepared)


class TestInAppAudioPlayer(unittest.TestCase):
    """The embedded player must never launch an external media player."""

    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="kurmanji_player_"))
        self.wav = self.tmp_dir / "tone.wav"
        rate = 22050
        with wave.open(str(self.wav), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            wf.writeframes(b"\x00\x00" * (rate * 2))

    @unittest.skipUnless(sys.platform == "win32", "MCI backend is Windows-only")
    def test_mci_full_control_cycle(self) -> None:
        player = InAppAudioPlayer()
        self.assertEqual(player.backend_name, "_MciBackend")
        player.load(self.wav)
        self.assertGreaterEqual(player.get_length_ms(), 1900)
        player.play()
        time.sleep(0.25)
        self.assertTrue(player.is_playing())
        self.assertGreater(player.get_position_ms(), 0)
        player.pause()
        self.assertFalse(player.is_playing())
        player.resume()
        self.assertTrue(player.is_playing())
        player.seek(1000)
        self.assertTrue(player.is_playing())
        self.assertGreaterEqual(player.get_position_ms(), 900)
        player.stop()
        self.assertEqual(player.get_position_ms(), 0)
        player.close()

    def test_no_external_player_symbols_in_source(self) -> None:
        source = (PROJECT_ROOT / "main.py").read_text(encoding="utf-8")
        for forbidden in ("os.startfile", "xdg-open", "flet_audio", "_open_with_os_player"):
            self.assertNotIn(forbidden, source)


class TestSyntaxAndProprietaryCompliance(unittest.TestCase):
    def test_ast_syntax_and_no_gpl_on_proprietary_files(self) -> None:
        py_files = [
            "main.py",
            "config.py",
            "text_utils.py",
            "tts_engine.py",
            "audio_player.py",
            "setup_runtime.py",
        ]
        for fname in py_files:
            fpath = PROJECT_ROOT / fname
            source = fpath.read_text(encoding="utf-8")
            ast.parse(source, filename=fname)
            self.assertIn("Proprietary and Confidential", source)
            self.assertNotIn("GNU GENERAL PUBLIC LICENSE", source.upper())


if __name__ == "__main__":
    t_start = time.perf_counter()
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    elapsed = time.perf_counter() - t_start
    print(f"\nTotal test suite wall time: {elapsed:.3f}s | Python Peak RSS: {_peak_rss_mb():.2f} MB")
    sys.exit(0 if result.wasSuccessful() else 1)
