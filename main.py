# Copyright (c) 2026 Kurmanji-TTS Team. All Rights Reserved.
# Proprietary and Confidential. Unauthorized copying, distribution, or modification
# of this file, via any medium, is strictly prohibited.

"""Flet Material 3 window for Kurmanji-TTS.

The window is built in four passes, and this file is ordered the same way:

1. ``create_screen`` reads the settings and builds the engine and the player.
2. ``create_widgets`` builds every control (layout lives in ``ui_components``).
3. the ``handle_*``/``on_*`` functions react to one event each.
4. ``main`` assembles the window and hands control to Flet.

No function here runs synthesis on the UI thread: the engine call goes through
``asyncio.to_thread`` so the window keeps repainting while the CPU is busy.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import flet as ft

from audio_player import (
    AudioSessionManager,
    InAppAudioPlayer,
    PlaybackState,
    WavInfo,
    format_seconds,
)
from config import (
    APP_NAME,
    APP_VERSION,
    AppSettings,
    DEFAULT_SPEAKER_ID,
    ENGINE_PROFILES,
    get_app_root,
    model_path_for_profile,
)
from locales import is_rtl, set_current_language
from locales import tr as translate
from text_utils import (
    SAMPLE_ARABIC_TEXTS,
    SAMPLE_KURMANJI_TEXTS,
    analyze_text,
    prepare_text_for_mms,
    prepare_text_for_tts,
    validate_kurmanji_input,
)
from tts_engine import (
    ModelMetadata,
    SynthesisResult,
    TTSEngineError,
    UnifiedTTSEngine,
)
from ui_components import (
    build_controls_card,
    build_counter_bar,
    build_editor,
    build_error_banner,
    build_metrics_row,
    build_player_card,
    build_player_controls,
    build_sample_chips,
    build_samples,
    build_selectors,
    build_speed_control,
    build_top_bar,
    ltr,
    mixed_text_row,
)

# Models that ship inside the app's own models/ folder. A saved path pointing at
# one of these is re-derived from the active profile; any other path is a
# deliberate user choice and must survive a restart untouched.
BUNDLED_MODEL_FILES = ("model.onnx", "mms_kmr/model.onnx", "mms_ara/model.onnx")

LANGUAGE_CODES = ("ar", "ku", "en")

# Some Python builds (e.g. MSYS2 on Windows) have no configured CA bundle.
# Flet downloads its desktop client on first run via urllib, which would fail
# with CERTIFICATE_VERIFY_FAILED without this.
try:
    import certifi

    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except ImportError:
    pass


@dataclass
class Screen:
    """Mutable window state shared by the small handler functions below.

    Passing one object instead of a dozen parameters is what lets every handler
    stay a flat module-level function with a single responsibility.
    """

    page: ft.Page
    settings: AppSettings
    root: Path
    engine: UnifiedTTSEngine
    session: AudioSessionManager
    player: InAppAudioPlayer
    w: SimpleNamespace
    lang: str
    is_generating: bool = False
    last_rtf: Optional[float] = None
    progress_task: Optional[asyncio.Task] = None

    def tr(self, key: str, **kwargs: object) -> str:
        """Translate through the language currently selected in the window."""
        return translate(self.lang, key, **kwargs)


# --------------------------------------------------------------- pure helpers
def resolve_startup_model_path(settings: AppSettings, root: Path) -> None:
    """Keep a saved engine profile and its bundled model path in sync on startup.

    Only paths inside ``models/`` are rewritten, so a custom model the user
    picked from another folder is never silently replaced by a bundled one.
    """
    current = Path(settings.model_path)
    expected = model_path_for_profile(root, settings.engine_profile)
    try:
        relative = current.relative_to(root / "models").as_posix()
    except ValueError:
        return
    if relative in BUNDLED_MODEL_FILES and current != expected:
        settings.model_path = str(expected)


def build_tts_text(engine_profile: str, normalized_text: str) -> str:
    """Return the text exactly as the selected engine should speak it.

    Each engine has its own idea of a friendly input: Piper reads eSpeak
    phonemes, while the MMS voices need digits spelled out in Kurmanji and
    unknown symbols removed. Keeping the choice here means the UI never needs to
    know which engine is active.
    """
    if engine_profile == "mms_kmr":
        return prepare_text_for_mms(normalized_text, "kmr")
    if engine_profile == "mms_ara":
        return prepare_text_for_mms(normalized_text, "ar")
    return prepare_text_for_tts(normalized_text, voice_lang="ku")


def selected_value(event: object, allowed: tuple) -> Optional[str]:
    """Read a dropdown value from ``data`` (Flet 0.86) or from the control.

    Newer Flet fires ``on_select`` with the value in ``data``; older builds only
    updated ``control.value``. Accepting both keeps the window working on either.
    """
    selected = getattr(event, "data", None)
    if selected not in allowed:
        control = getattr(event, "control", None)
        selected = getattr(control, "value", None) if control is not None else None
    return selected if selected in allowed else None


# ------------------------------------------------------------------- widgets
def create_widgets(t, settings: AppSettings) -> SimpleNamespace:
    """Build every control once, from the top bar down to the player row."""
    parts: dict = {}
    parts.update(vars(build_top_bar(t, settings.ui_language, settings.theme_mode == "dark")))
    parts.update(vars(build_error_banner(t)))
    parts.update(vars(build_counter_bar(t)))
    parts.update(vars(build_editor(t)))
    parts.update(vars(build_samples(t)))
    parts.update(vars(build_selectors(t, settings)))
    parts.update(vars(build_speed_control(t, settings)))
    parts.update(vars(build_player_controls(t)))
    parts.update(vars(build_metrics_row(t)))
    parts["progress_bar"] = ft.ProgressBar(visible=False, border_radius=6)
    parts["generate_button"] = ft.FilledButton(
        content=t("generate"), icon=ft.Icons.GRAPHIC_EQ, height=46
    )
    for name in ("save_picker", "model_picker", "piper_picker"):
        parts[name] = ft.FilePicker()
    return SimpleNamespace(**parts)


def build_input_card(w: SimpleNamespace) -> ft.Card:
    """Text card: quick samples, the editor itself, and the live counters."""
    text_input = w.text_input
    return ft.Card(
        expand=True,
        content=ft.Container(
            padding=18,
            expand=True,
            content=ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                expand=True,
                controls=[
                    ft.Row(
                        [w.samples_label, w.clear_button],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    w.sample_chips,
                    w.input_label_row,
                    # The field itself stays LTR for Kurmanji; the container keeps
                    # that direction even when the rest of the page is Arabic RTL.
                    ft.Container(content=text_input, rtl=False, expand=True),
                    w.counters_row,
                ],
                spacing=12,
            ),
        ),
    )


# ------------------------------------------------------------- small helpers
def show_error(screen: Screen, message: str) -> None:
    """Show a dismissible inline banner instead of a modal dialog."""
    screen.w.error_text.value = message
    screen.w.error_banner.visible = True
    screen.page.update()


def hide_error(screen: Screen) -> None:
    """Clear and hide the error banner."""
    screen.w.error_banner.visible = False
    screen.w.error_text.value = ""
    screen.page.update()


def notify(screen: Screen, message: str) -> None:
    """Show a short, self-dismissing confirmation."""
    screen.page.show_dialog(ft.SnackBar(content=ft.Text(message), duration=3000))


def on_text_changed(screen: Screen, _: object = None) -> None:
    """Refresh the character, word and Hawar counters while typing."""
    analysis = analyze_text(screen.w.text_input.value or "")
    w = screen.w
    w.char_value.value = ltr(
        f"{analysis.char_count} / {screen.settings.max_text_length}"
    )
    w.word_value.value = ltr(str(analysis.word_count))
    w.hawar_value.value = ltr(
        " ".join(analysis.special_chars_found) if analysis.special_chars_found else "—"
    )
    if _ is not None:
        screen.page.update()


def insert_sample_text(screen: Screen, text: str) -> None:
    """Fill the editor with a ready-made example and refresh the counters."""
    screen.w.text_input.value = text
    hide_error(screen)
    on_text_changed(screen)
    screen.page.update()


def rebuild_sample_chips(screen: Screen) -> None:
    """Offer Kurmanji or Arabic examples, following the active profile."""
    samples = (
        SAMPLE_ARABIC_TEXTS
        if screen.settings.engine_profile == "mms_ara"
        else SAMPLE_KURMANJI_TEXTS
    )
    screen.w.sample_chips.controls = build_sample_chips(
        samples, partial(insert_sample_text, screen)
    )


def refresh_profile_ui(screen: Screen) -> None:
    """Align input direction, speaker list and samples with the engine profile.

    Arabic needs an RTL editor and Arabic samples; both MMS voices have a single
    speaker, so the dropdown is disabled and pinned to id 0.
    """
    w, settings = screen.w, screen.settings
    is_arabic = settings.engine_profile == "mms_ara"
    is_mms = settings.engine_profile != "piper_kmr"
    label_is_rtl = is_arabic or screen.page.rtl

    w.text_input.rtl = is_arabic
    w.text_input.text_align = (
        ft.TextAlign.RIGHT if is_arabic else ft.TextAlign.LEFT
    )
    w.text_input.hint_text = (
        screen.tr("input_hint_ar") if is_arabic else screen.tr("input_hint")
    )
    w.input_label_primary.value = (
        screen.tr("input_label_ar") if is_arabic else screen.tr("input_label_primary")
    )
    w.input_label_primary.rtl = label_is_rtl
    w.input_label_primary.text_align = (
        ft.TextAlign.RIGHT if label_is_rtl else ft.TextAlign.LEFT
    )
    w.input_label_secondary.value = (
        "" if is_arabic else screen.tr("input_label_secondary")
    )
    w.profile_dropdown.label = screen.tr("engine_profile")
    w.profile_dropdown.tooltip = screen.tr("engine_profile_tooltip")
    w.profile_dropdown.value = settings.engine_profile

    w.speaker_dropdown.disabled = is_mms
    if is_mms:
        pin_single_speaker(screen, is_arabic)
    rebuild_sample_chips(screen)


def pin_single_speaker(screen: Screen, is_arabic: bool) -> None:
    """Both MMS voices have one speaker, so the dropdown shows exactly that one."""
    screen.w.speaker_dropdown.options = [
        ft.dropdown.Option(
            key="0",
            text=screen.tr("mms_arabic") if is_arabic else screen.tr("mms_speaker_0"),
        )
    ]
    screen.w.speaker_dropdown.value = "0"


def on_speed_change(screen: Screen, e: ft.ControlEvent) -> None:
    """Persist the slider value; Piper converts it to ``1 / speed`` later."""
    screen.settings.speech_speed = round(float(e.control.value), 2)
    screen.w.speed_value.value = ltr(f"{screen.settings.speech_speed:.2f}x")
    screen.page.update()


# -------------------------------------------------------------------- player
def update_player_buttons(
    screen: Screen, state: PlaybackState, has_audio: bool
) -> None:
    """Enable exactly the buttons that make sense in the given state."""
    w = screen.w
    screen.session.set_state(state)
    w.play_button.disabled = not has_audio or state == PlaybackState.PLAYING
    w.pause_button.disabled = not has_audio or state != PlaybackState.PLAYING
    w.stop_button.disabled = not has_audio or state in (
        PlaybackState.IDLE,
        PlaybackState.STOPPED,
    )
    w.save_button.disabled = not has_audio
    w.playback_slider.disabled = not has_audio


def reset_progress_display(screen: Screen) -> None:
    """Put the progress bar and the time label back to the start."""
    screen.w.playback_slider.value = 0
    info = screen.session.current_info
    screen.w.time_display.value = (
        ltr(f"00:00 / {format_seconds(info.duration_seconds)}")
        if info
        else ltr("00:00 / 00:00")
    )


def cancel_progress_task(screen: Screen) -> None:
    """Stop the 100 ms progress poller if it is still running."""
    if screen.progress_task is not None and not screen.progress_task.done():
        screen.progress_task.cancel()
    screen.progress_task = None


def on_playback_finished(screen: Screen) -> None:
    """React to the audio reaching its end on its own."""
    cancel_progress_task(screen)
    reset_progress_display(screen)
    update_player_buttons(
        screen, PlaybackState.STOPPED, has_audio=screen.session.current_wav is not None
    )
    screen.page.update()


async def progress_loop(screen: Screen) -> None:
    """Poll the embedded player every 100 ms while audio is actually playing.

    Polling instead of a timer keeps the bar honest: if the OS backend stops
    early (end of file, device lost) the UI notices on the next tick.
    """
    try:
        while True:
            await asyncio.sleep(0.1)
            info = screen.session.current_info
            total_s = info.duration_seconds if info is not None else 0.0
            total_ms = max(1, int(total_s * 1000))
            pos_ms = max(0, screen.player.get_position_ms())
            screen.w.playback_slider.value = min(100.0, max(0.0, pos_ms / total_ms * 100.0))
            screen.w.time_display.value = ltr(
                f"{format_seconds(pos_ms / 1000.0)} / {format_seconds(total_s)}"
            )
            if screen.session.state != PlaybackState.PLAYING:
                return
            if not screen.player.is_playing():
                on_playback_finished(screen)
                return
            screen.page.update()
    except asyncio.CancelledError:
        return


async def on_slider_seek(screen: Screen, e: ft.ControlEvent) -> None:
    """Convert the slider percentage back into milliseconds and seek."""
    info = screen.session.current_info
    if info is None:
        return
    target_ms = int((float(e.control.value) / 100.0) * info.duration_seconds * 1000)
    try:
        screen.player.seek(target_ms)
    except Exception as exc:
        show_error(screen, screen.tr("error_seek", error=exc))
        return
    screen.w.time_display.value = ltr(
        f"{format_seconds(target_ms / 1000.0)} / {format_seconds(info.duration_seconds)}"
    )
    screen.page.update()


async def handle_play(screen: Screen, _: object = None) -> None:
    """Start or resume playback and begin polling the position."""
    wav = screen.session.current_wav
    if wav is None or not wav.exists():
        show_error(screen, screen.tr("error_no_audio"))
        return
    try:
        if screen.session.state == PlaybackState.PAUSED:
            screen.player.resume()
        else:
            screen.player.play()
    except Exception as exc:
        show_error(screen, screen.tr("error_play", error=exc))
        return
    update_player_buttons(screen, PlaybackState.PLAYING, has_audio=True)
    cancel_progress_task(screen)
    screen.progress_task = asyncio.create_task(progress_loop(screen))
    screen.page.update()


async def handle_pause(screen: Screen, _: object = None) -> None:
    """Freeze playback where it is; the backend keeps the position."""
    cancel_progress_task(screen)
    update_player_buttons(screen, PlaybackState.PAUSED, has_audio=True)
    try:
        screen.player.pause()
    except Exception:
        pass
    screen.page.update()


async def handle_stop(screen: Screen, _: object = None) -> None:
    """Stop playback and rewind the progress display."""
    cancel_progress_task(screen)
    update_player_buttons(
        screen, PlaybackState.STOPPED, has_audio=screen.session.current_wav is not None
    )
    try:
        screen.player.stop()
    except Exception:
        pass
    reset_progress_display(screen)
    screen.page.update()


async def handle_save_wav(screen: Screen, _: object = None) -> None:
    """Ask for a destination and copy the temporary WAV there."""
    if screen.session.current_wav is None:
        show_error(screen, screen.tr("error_save_first"))
        return
    target = await screen.w.save_picker.save_file(
        dialog_title=screen.tr("save_dialog_title"),
        file_name="kurmanji_tts_output.wav",
        allowed_extensions=["wav"],
    )
    if not target:
        return
    try:
        saved_path = screen.session.export_wav(Path(target))
        notify(screen, screen.tr("save_ok", name=saved_path.name))
    except Exception as exc:
        show_error(screen, screen.tr("save_failed", error=exc))


# ------------------------------------------------------------- engine status
def apply_ready_status(screen: Screen, meta: ModelMetadata) -> None:
    """Turn the badge green and rebuild the speaker list from the model."""
    w = screen.w
    w.status_icon.color = ft.Colors.GREEN
    w.status_text.value = screen.tr("model_ready")
    w.status_details.value = ltr(
        f"{meta.sample_rate} Hz | {meta.num_speakers} | ★ {meta.default_speaker_id}"
    )
    w.speaker_dropdown.options = [
        ft.dropdown.Option(key=str(sid), text=label) for sid, label in meta.speakers
    ]
    default_id = str(meta.default_speaker_id)
    known_ids = {str(sid) for sid, _ in meta.speakers}
    # A model swap can invalidate the saved id; the recommended speaker is
    # the only safe value when the current one is unknown.
    if w.speaker_dropdown.value not in known_ids or w.speaker_dropdown.value != default_id:
        w.speaker_dropdown.value = default_id


def refresh_engine_status(screen: Screen) -> None:
    """Ask the engine whether the model is usable and mirror that in the badge."""
    status = screen.engine.check_status()
    if status.ready and status.metadata is not None:
        apply_ready_status(screen, status.metadata)
        return
    screen.w.status_icon.color = ft.Colors.RED
    screen.w.status_text.value = screen.tr("model_not_ready")
    screen.w.status_details.value = ltr("")
    show_error(screen, f"{status.message}\n{screen.tr('engine_hint')}")


# ------------------------------------------------------------------ generate
async def run_synthesis(screen: Screen, tts_text: str, speaker_id: int, target_wav: Path):
    """Run the blocking ONNX/Piper call on a worker thread.

    ``asyncio.to_thread`` is what keeps the window responsive: the event loop
    stays free to repaint the progress bar while the CPU is busy.
    """
    settings = screen.settings
    return await asyncio.to_thread(
        screen.engine.synthesize,
        tts_text,
        target_wav,
        speaker_id,
        settings.length_scale,
        settings.noise_scale,
        settings.noise_w,
    )


def show_metrics(screen: Screen, result: SynthesisResult, wav_info: WavInfo) -> None:
    """Fill the five metric labels from a finished synthesis."""
    w = screen.w
    w.metric_gen_value.value = ltr(f"{result.generation_time_seconds:.2f}s")
    w.metric_duration_value.value = ltr(f"{wav_info.duration_seconds:.2f}s")
    screen.last_rtf = result.real_time_factor
    w.metric_rtf.value = f"RTF: {screen.last_rtf:.2f}"
    w.metric_rate_value.value = ltr(f"{result.sample_rate} Hz")
    w.metric_speaker_value.value = ltr(str(result.speaker_id))


def load_synthesis_result(screen: Screen, result: SynthesisResult) -> None:
    """Library the new WAV into the player, then refresh metrics and transport."""
    wav_info = screen.session.register_generated_wav(result.wav_path)
    try:
        screen.player.load(wav_info.path)
    except Exception as exc:
        raise TTSEngineError(screen.tr("load_in_app_failed", error=exc)) from exc
    reset_progress_display(screen)
    show_metrics(screen, result, wav_info)
    update_player_buttons(screen, PlaybackState.STOPPED, has_audio=True)


def validate_editor_text(screen: Screen) -> Optional[str]:
    """Validate and normalize the editor text; return the engine text or None.

    The editor keeps the normalized text the user typed, while the engine gets
    its own prepared form; showing an error here means nothing is generated.
    """
    is_valid, normalized_text, validation_error = validate_kurmanji_input(
        screen.w.text_input.value or "",
        max_chars=screen.settings.max_text_length,
    )
    if not is_valid:
        show_error(screen, validation_error)
        return None

    screen.w.text_input.value = normalized_text
    on_text_changed(screen)

    tts_text = build_tts_text(screen.settings.engine_profile, normalized_text)
    if not tts_text.strip():
        show_error(screen, validation_error or screen.tr("validate_symbols"))
        return None
    return tts_text


async def handle_generate(screen: Screen, _: object = None) -> None:
    """Validate the text, synthesize it, then load the WAV into the player."""
    if screen.is_generating:
        return
    hide_error(screen)
    tts_text = validate_editor_text(screen)
    if tts_text is None:
        return

    speaker_id = 0
    if screen.settings.engine_profile == "piper_kmr":
        speaker_id = int(screen.w.speaker_dropdown.value or screen.settings.default_speaker_id)

    cancel_progress_task(screen)
    screen.player.close()
    target_wav = screen.session.allocate_output_path()

    screen.is_generating = True
    screen.w.generate_button.disabled = True
    screen.w.progress_bar.visible = True
    screen.page.update()
    try:
        result = await run_synthesis(screen, tts_text, speaker_id, target_wav)
        load_synthesis_result(screen, result)
        notify(screen, screen.tr("generate_ok"))
    except TTSEngineError as exc:
        show_error(screen, str(exc))
    except Exception as exc:
        show_error(screen, screen.tr("generate_failed", error=exc))
    finally:
        screen.is_generating = False
        screen.w.generate_button.disabled = False
        screen.w.progress_bar.visible = False
        screen.page.update()


# ------------------------------------------------------------ theme/settings
def toggle_theme(screen: Screen, _: object = None) -> None:
    """Flip dark/light mode and remember the choice."""
    go_dark = screen.page.theme_mode != ft.ThemeMode.DARK
    screen.page.theme_mode = ft.ThemeMode.DARK if go_dark else ft.ThemeMode.LIGHT
    screen.settings.theme_mode = "dark" if go_dark else "light"
    screen.w.theme_button.icon = ft.Icons.LIGHT_MODE if go_dark else ft.Icons.DARK_MODE
    screen.settings.save()
    screen.page.update()


def save_settings_and_close(
    screen: Screen,
    model_field: ft.TextField,
    piper_field: ft.TextField,
    persistent_switch: ft.Switch,
    _: object = None,
) -> None:
    """Persist the new paths, rebuild the engine and re-check readiness."""
    settings = screen.settings
    settings.model_path = model_field.value.strip()
    settings.piper_path = piper_field.value.strip()
    settings.use_persistent_process = bool(persistent_switch.value)
    settings.save()
    hide_error(screen)
    screen.engine.update_paths(
        piper_path=Path(settings.piper_path),
        model_path=Path(settings.model_path),
        preferred_speaker=settings.default_speaker_id,
        use_persistent_process=settings.use_persistent_process,
    )
    refresh_engine_status(screen)
    screen.page.pop_dialog()
    screen.page.update()


def browse_field(screen: Screen, picker: ft.FilePicker, field: ft.TextField,
                 title_key: str, extensions=None):
    """Return the async handler that fills one path field from the file picker."""
    async def handler(_: object = None) -> None:
        picked = await picker.pick_files(
            dialog_title=screen.tr(title_key), allowed_extensions=extensions
        )
        if picked:
            field.value = picked[0].path or ""
            screen.page.update()

    return handler


def build_settings_body(screen: Screen, dialog_rtl: bool, model_field: ft.TextField,
                        piper_field: ft.TextField, persistent_switch: ft.Switch) -> ft.Column:
    """Labels, both LTR path rows, the warm-process switch and the note.

    Each Arabic label is its own control so the path itself stays Latin-LTR.
    """
    t = screen.tr
    model_row = ft.Row([
        ft.Container(content=model_field, rtl=False, expand=True),
        ft.IconButton(icon=ft.Icons.FOLDER_OPEN, tooltip=t("browse_model"),
                      on_click=browse_field(screen, screen.w.model_picker, model_field,
                                            "pick_model", ["onnx"])),
    ], spacing=6)
    piper_row = ft.Row([
        ft.Container(content=piper_field, rtl=False, expand=True),
        ft.IconButton(icon=ft.Icons.FOLDER_OPEN, tooltip=t("browse_piper"),
                      on_click=browse_field(screen, screen.w.piper_picker, piper_field,
                                            "pick_piper")),
    ], spacing=6)
    paths = ft.Container(width=650, rtl=dialog_rtl, content=ft.Column(
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        spacing=12,
        controls=[
            mixed_text_row(dialog_rtl, [(t("model_label_primary"), False),
                                        (t("model_label_secondary"), True)]),
            model_row,
            mixed_text_row(dialog_rtl, [(t("piper_label_primary"), False),
                                        (t("piper_label_middle"), True),
                                        (t("piper_label_suffix"), False)]),
            piper_row,
        ],
    ))
    note = ft.Text(t("settings_note_clean"), size=12, color=ft.Colors.OUTLINE,
                   text_align=ft.TextAlign.RIGHT if dialog_rtl else ft.TextAlign.LEFT)
    return ft.Column(horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                     controls=[paths, persistent_switch, note], tight=True, spacing=14)


def open_settings_dialog(screen: Screen, _: object = None) -> None:
    """Modal dialog for the model/Piper paths and the warm-process switch."""
    page, t = screen.page, screen.tr
    dialog_rtl = is_rtl(screen.lang)
    model_field = ft.TextField(value=screen.settings.model_path, rtl=False,
                               text_align=ft.TextAlign.LEFT, text_size=13, expand=True)
    piper_field = ft.TextField(value=screen.settings.piper_path, rtl=False,
                               text_align=ft.TextAlign.LEFT, text_size=13, expand=True)
    persistent_switch = ft.Switch(label=t("persistent"),
                                  value=screen.settings.use_persistent_process)
    page.show_dialog(ft.AlertDialog(
        modal=True,
        rtl=dialog_rtl,
        title=mixed_text_row(dialog_rtl, [(t("settings_title_primary"), False),
                                          (t("settings_title_secondary"), True)],
                             size=20, color=None),
        content=build_settings_body(screen, dialog_rtl, model_field, piper_field,
                                    persistent_switch),
        actions=[
            ft.TextButton(t("cancel"), on_click=lambda _: page.pop_dialog()),
            ft.FilledButton(t("save_settings"), on_click=partial(
                save_settings_and_close, screen, model_field, piper_field,
                persistent_switch)),
        ],
    ))


# ------------------------------------------------------- engine and language
def apply_engine_profile(screen: Screen, profile: str) -> None:
    """Swap synthesis engine, model, speaker list and input direction."""
    chosen = profile if profile in ENGINE_PROFILES else "piper_kmr"
    settings = screen.settings
    settings.engine_profile = chosen
    settings.model_path = str(model_path_for_profile(screen.root, chosen))
    settings.tts_language = "ar" if chosen == "mms_ara" else "ku"
    settings.save()
    screen.engine.set_profile(chosen)
    screen.engine.update_paths(
        piper_path=Path(settings.piper_path),
        model_path=Path(settings.model_path),
        preferred_speaker=DEFAULT_SPEAKER_ID,
        use_persistent_process=settings.use_persistent_process,
    )
    refresh_profile_ui(screen)
    refresh_engine_status(screen)
    screen.page.update()


def on_engine_profile_changed(screen: Screen, e: ft.ControlEvent) -> None:
    """Take the new profile from the dropdown and apply it."""
    apply_engine_profile(
        screen, selected_value(e, ENGINE_PROFILES) or screen.settings.engine_profile
    )


def relabel_ui(screen: Screen) -> None:
    """Re-apply every translated string after a language switch."""
    w, t = screen.w, screen.tr
    w.subtitle.value = t("app_subtitle")
    w.status_text.value = t("model_checking")
    w.error_close.tooltip = t("close_notification")
    w.char_label.value = t("label_chars")
    w.word_label.value = t("label_words")
    w.hawar_label.value = t("label_hawar")
    w.samples_label.value = t("label_samples")
    w.clear_button.content = t("clear_text")
    w.speaker_dropdown.label = t("speaker")
    w.speed_caption.value = t("speed")
    w.speed_slider.tooltip = t("speed_tooltip")
    w.generate_button.content = t("generate")
    w.play_button.content = t("play")
    w.pause_button.content = t("pause")
    w.stop_button.content = t("stop")
    w.save_button.content = t("save_wav")
    w.metric_gen_label.value = t("metric_gen")
    w.metric_duration_label.value = t("metric_duration")
    w.metric_rate_label.value = t("metric_rate")
    w.metric_speaker_label.value = t("metric_speaker")
    w.metric_rtf.value = (
        f"RTF: {screen.last_rtf:.2f}" if screen.last_rtf is not None else "RTF: —"
    )
    w.theme_button.tooltip = t("theme_tooltip")
    w.settings_button.tooltip = t("settings_tooltip")
    w.language_dropdown.tooltip = t("language")


def apply_language(screen: Screen, lang: str) -> None:
    """Switch all visible strings and the page direction instantly."""
    chosen = lang if lang in LANGUAGE_CODES else "ar"
    screen.lang = chosen
    screen.settings.ui_language = chosen
    screen.settings.save()
    set_current_language(chosen)
    screen.page.rtl = is_rtl(chosen)

    relabel_ui(screen)
    refresh_profile_ui(screen)
    screen.w.language_dropdown.value = chosen
    refresh_engine_status(screen)
    screen.page.update()


def on_language_changed(screen: Screen, e: ft.ControlEvent) -> None:
    """Take the new language from the dropdown and apply it."""
    apply_language(screen, selected_value(e, LANGUAGE_CODES) or screen.lang)


def on_disconnect(screen: Screen, _: object = None) -> None:
    """Release audio, engine and temp files when the window closes."""
    cancel_progress_task(screen)
    screen.player.close()
    screen.engine.close()
    screen.session.shutdown()


# ----------------------------------------------------------- window assembly
def create_screen(page: ft.Page) -> Screen:
    """Load the settings, resolve the bundled model and build the engines."""
    settings = AppSettings.load()
    set_current_language(settings.ui_language)
    root = get_app_root()
    resolve_startup_model_path(settings, root)
    engine = UnifiedTTSEngine(
        piper_path=Path(settings.piper_path),
        model_path=Path(settings.model_path),
        preferred_speaker=settings.default_speaker_id,
        use_persistent_process=settings.use_persistent_process,
        root=root,
        engine_profile=settings.engine_profile,
    )
    screen = Screen(
        page=page,
        settings=settings,
        root=root,
        engine=engine,
        session=AudioSessionManager(),
        player=InAppAudioPlayer(),
        w=SimpleNamespace(),
        lang=settings.ui_language,
    )
    screen.w = create_widgets(screen.tr, settings)
    return screen


def configure_window(screen: Screen) -> None:
    """Window size, theme, direction and scroll behaviour."""
    page = screen.page
    page.title = f"{APP_NAME} v{APP_VERSION}"
    page.window.width = 920
    page.window.height = 760
    page.window.min_width = 680
    page.window.min_height = 620
    page.padding = 20
    page.scroll = ft.ScrollMode.AUTO
    page.rtl = is_rtl(screen.lang)
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.TEAL, use_material3=True)
    page.dark_theme = ft.Theme(color_scheme_seed=ft.Colors.TEAL, use_material3=True)
    page.theme_mode = (
        ft.ThemeMode.DARK
        if screen.settings.theme_mode == "dark"
        else ft.ThemeMode.LIGHT
    )
    page.services.extend(
        [screen.w.save_picker, screen.w.model_picker, screen.w.piper_picker]
    )


def build_layout(screen: Screen) -> None:
    """Stack the header, the banner and the three cards on the page."""
    w = screen.w
    w.input_card = build_input_card(w)
    w.controls_card = build_controls_card(
        w.profile_dropdown,
        w.speaker_dropdown,
        w.speed_label,
        w.speed_slider,
        w.generate_button,
        w.progress_bar,
    )
    w.player_card = build_player_card(
        w.play_button,
        w.pause_button,
        w.stop_button,
        w.playback_slider,
        w.time_display,
        w.metrics_row,
        w.save_button,
    )
    screen.page.add(
        ft.Column(
            [w.header, w.error_banner, w.input_card, w.controls_card, w.player_card],
            spacing=14,
        )
    )


def wire_events(screen: Screen) -> None:
    """Attach every handler once, so the layout above stays declarative."""
    w = screen.w
    w.error_close.on_click = lambda _: hide_error(screen)
    w.clear_button.on_click = lambda _: insert_sample_text(screen, "")
    w.text_input.on_change = partial(on_text_changed, screen)
    w.speed_slider.on_change = partial(on_speed_change, screen)
    w.generate_button.on_click = partial(handle_generate, screen)
    w.play_button.on_click = partial(handle_play, screen)
    w.pause_button.on_click = partial(handle_pause, screen)
    w.stop_button.on_click = partial(handle_stop, screen)
    w.save_button.on_click = partial(handle_save_wav, screen)
    w.playback_slider.on_change_end = partial(on_slider_seek, screen)
    w.settings_button.on_click = partial(open_settings_dialog, screen)
    w.theme_button.on_click = partial(toggle_theme, screen)
    w.profile_dropdown.on_select = partial(on_engine_profile_changed, screen)
    w.profile_dropdown.on_change = partial(on_engine_profile_changed, screen)
    w.language_dropdown.on_select = partial(on_language_changed, screen)
    w.language_dropdown.on_change = partial(on_language_changed, screen)
    screen.page.on_disconnect = partial(on_disconnect, screen)


async def main(page: ft.Page) -> None:
    """Build the window, wire the events, and keep the heavy work off the UI thread."""
    screen = create_screen(page)
    configure_window(screen)
    build_layout(screen)
    wire_events(screen)
    refresh_profile_ui(screen)
    refresh_engine_status(screen)
    page.update()


if __name__ == "__main__":
    ft.run(main)
