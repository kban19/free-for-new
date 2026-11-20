# Copyright (c) 2026 Kurmanji-TTS Team. All Rights Reserved.
# Proprietary and Confidential. Unauthorized copying, distribution, or modification
# of this file, via any medium, is strictly prohibited.

"""Modern Cross-Platform Desktop GUI for Kurmanji-TTS built with Flet."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Optional

import flet as ft

from audio_player import AudioSessionManager, InAppAudioPlayer, PlaybackState, format_seconds
from config import (
    APP_NAME,
    APP_VERSION,
    AppSettings,
    DEFAULT_SPEAKER_ID,
    ENGINE_PROFILES,
    get_app_root,
    model_path_for_profile,
)
from locales import is_rtl, set_current_language, tr
from text_utils import (
    SAMPLE_ARABIC_TEXTS,
    SAMPLE_KURMANJI_TEXTS,
    analyze_text,
    prepare_text_for_mms,
    prepare_text_for_tts,
    validate_kurmanji_input,
)
from tts_engine import TTSEngineError, UnifiedTTSEngine


def _ltr(value: object) -> str:
    """Isolate Latin/numeric text so an RTL context cannot reorder it."""
    return f"\u2066{value}\u2069"


def _mixed_text_row(
    page_is_rtl: bool,
    parts: "list[tuple[str, bool]]",
    size: int = 12,
    color: object = None,
) -> ft.Row:
    """Build a label from separate RTL/LTR Text nodes instead of mixing scripts."""
    controls = []
    for text, latin in parts:
        if not text:
            continue
        rtl_flag = page_is_rtl and not latin
        controls.append(
            ft.Text(
                text,
                size=size,
                color=color or ft.Colors.OUTLINE,
                rtl=rtl_flag,
                text_align=ft.TextAlign.RIGHT if rtl_flag else ft.TextAlign.LEFT,
            )
        )
    return ft.Row(controls, spacing=6)


# Some Python builds (e.g. MSYS2 on Windows) have no configured CA bundle.
# Flet downloads its desktop client on first run via urllib, which would fail
# with CERTIFICATE_VERIFY_FAILED without this.
try:
    import certifi

    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except ImportError:
    pass


async def main(page: ft.Page) -> None:
    """Main Flet application entry point."""
    settings = AppSettings.load()
    current_lang = settings.ui_language
    set_current_language(current_lang)

    # Keep a saved engine profile and a bundled model path in sync on startup.
    root = get_app_root()
    current_model = Path(settings.model_path)
    expected_model = model_path_for_profile(root, settings.engine_profile)
    models_root = root / "models"
    try:
        relative_model = current_model.relative_to(models_root).as_posix()
    except ValueError:
        relative_model = ""
    if relative_model in (
        "model.onnx", "mms_kmr/model.onnx", "mms_ara/model.onnx"
    ) and current_model != expected_model:
        settings.model_path = str(expected_model)

    def t(key: str, **kwargs: object) -> str:
        return tr(current_lang, key, **kwargs)

    engine = UnifiedTTSEngine(
        piper_path=Path(settings.piper_path),
        model_path=Path(settings.model_path),
        preferred_speaker=settings.default_speaker_id,
        use_persistent_process=settings.use_persistent_process,
        root=root,
        engine_profile=settings.engine_profile,
    )
    audio_session = AudioSessionManager()

    page.title = f"{APP_NAME} v{APP_VERSION}"
    page.window.width = 920
    page.window.height = 760
    page.window.min_width = 680
    page.window.min_height = 620
    page.padding = 20
    page.scroll = ft.ScrollMode.AUTO
    page.rtl = is_rtl(current_lang)
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.TEAL, use_material3=True)
    page.dark_theme = ft.Theme(color_scheme_seed=ft.Colors.TEAL, use_material3=True)
    page.theme_mode = (
        ft.ThemeMode.DARK if settings.theme_mode == "dark" else ft.ThemeMode.LIGHT
    )

    is_generating = False
    inapp_player = InAppAudioPlayer()
    progress_task: Optional[asyncio.Task] = None

    model_status_icon = ft.Icon(ft.Icons.CIRCLE, size=12, color=ft.Colors.AMBER)
    model_status_text = ft.Text(t("model_checking"), size=13, weight=ft.FontWeight.W_500)
    model_status_details = ft.Text(_ltr(""), size=11, color=ft.Colors.OUTLINE)
    model_status_badge = ft.Container(
        content=ft.Row(
            [model_status_icon, model_status_text, model_status_details],
            spacing=6,
            tight=True,
        ),
        padding=ft.Padding.symmetric(horizontal=12, vertical=6),
        border_radius=20,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
    )

    error_text = ft.Text("", color=ft.Colors.ON_ERROR_CONTAINER, size=13, expand=True)
    close_error_button = ft.IconButton(
        icon=ft.Icons.CLOSE,
        icon_size=16,
        tooltip=t("close_notification"),
        on_click=lambda _: hide_error(),
    )
    error_banner = ft.Container(
        content=ft.Row(
            [
                ft.Icon(ft.Icons.ERROR_OUTLINE, color=ft.Colors.ERROR, size=20),
                error_text,
                close_error_button,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        ),
        bgcolor=ft.Colors.ERROR_CONTAINER,
        border_radius=10,
        padding=ft.Padding.symmetric(horizontal=14, vertical=8),
        visible=False,
    )

    def show_error(message: str) -> None:
        error_text.value = message
        error_banner.visible = True
        page.update()

    def hide_error() -> None:
        error_banner.visible = False
        error_text.value = ""
        page.update()

    def show_snack(message: str) -> None:
        page.show_dialog(ft.SnackBar(content=ft.Text(message), duration=3000))

    # Arabic captions and Latin values are separate controls; isolate marks
    # keep numeric/unit order stable when the page flips to RTL.
    char_counter_text = ft.Text(
        _ltr(f"0 / {settings.max_text_length}"), size=12, color=ft.Colors.OUTLINE
    )
    word_counter_text = ft.Text(_ltr("0"), size=12, color=ft.Colors.OUTLINE)
    hawar_badge_text = ft.Text(_ltr("—"), size=12, color=ft.Colors.PRIMARY)
    char_label_text = ft.Text(t("label_chars"), size=12, color=ft.Colors.OUTLINE)
    word_label_text = ft.Text(t("label_words"), size=12, color=ft.Colors.OUTLINE)
    hawar_label_text = ft.Text(t("label_hawar"), size=12, color=ft.Colors.OUTLINE)
    counters_row = ft.Row(
        [
            ft.Row([char_label_text, char_counter_text], spacing=4, tight=True),
            ft.Text("|", size=12, color=ft.Colors.OUTLINE),
            ft.Row([word_label_text, word_counter_text], spacing=4, tight=True),
            ft.Row([hawar_label_text, hawar_badge_text], spacing=4, tight=True),
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        wrap=True,
        spacing=10,
    )

    def on_text_changed(e: Optional[ft.ControlEvent] = None) -> None:
        analysis = analyze_text(text_input.value or "")
        char_counter_text.value = _ltr(
            f"{analysis.char_count} / {settings.max_text_length}"
        )
        word_counter_text.value = _ltr(str(analysis.word_count))
        chars_str = " ".join(analysis.special_chars_found) if analysis.special_chars_found else "—"
        hawar_badge_text.value = _ltr(chars_str)
        if e is not None:
            page.update()

    input_label_primary = ft.Text(
        t("input_label_primary"),
        size=12,
        color=ft.Colors.OUTLINE,
        rtl=page.rtl,
        text_align=ft.TextAlign.RIGHT if page.rtl else ft.TextAlign.LEFT,
    )
    input_label_secondary = ft.Text(
        t("input_label_secondary"),
        size=12,
        color=ft.Colors.OUTLINE,
        rtl=False,
        text_align=ft.TextAlign.LEFT,
    )
    input_label_row = ft.Row([input_label_primary, input_label_secondary], spacing=6)

    text_input = ft.TextField(
        hint_text=t("input_hint"),
        multiline=True,
        min_lines=5,
        max_lines=9,
        text_size=16,
        rtl=False,
        text_align=ft.TextAlign.LEFT,
        border_radius=12,
        expand=True,
        on_change=on_text_changed,
    )

    def insert_sample_text(sample_text: str) -> None:
        text_input.value = sample_text
        hide_error()
        on_text_changed()
        page.update()

    sample_chips = ft.Row(wrap=True, spacing=8)

    def rebuild_sample_chips() -> None:
        samples = (
            SAMPLE_ARABIC_TEXTS
            if settings.engine_profile == "mms_ara"
            else SAMPLE_KURMANJI_TEXTS
        )
        sample_chips.controls = [
            ft.Chip(
                label=ft.Text(label, size=12),
                leading=ft.Icons.TEXT_SNIPPET_OUTLINED,
                show_checkmark=False,
                on_click=lambda _, txt=content: insert_sample_text(txt),
            )
            for label, content in samples.items()
        ]

    rebuild_sample_chips()

    speaker_dropdown = ft.Dropdown(
        label=t("speaker"),
        width=260,
        border_radius=10,
        options=[
            ft.dropdown.Option(
                key=str(settings.default_speaker_id),
                text=f"Speaker {settings.default_speaker_id}",
            )
        ],
        value=str(settings.default_speaker_id),
    )

    engine_profile_dropdown = ft.Dropdown(
        label=t("engine_profile"),
        width=300,
        tooltip=t("engine_profile_tooltip"),
        value=settings.engine_profile,
        options=[
            ft.dropdown.Option(key="piper_kmr", text=t("profile_piper_kmr")),
            ft.dropdown.Option(key="mms_kmr", text=t("profile_mms_kmr")),
            ft.dropdown.Option(key="mms_ara", text=t("profile_mms_ara")),
        ],
    )

    def refresh_profile_ui() -> None:
        """Align input direction, speaker list and samples with the engine profile."""
        is_arabic = settings.engine_profile == "mms_ara"
        is_mms = settings.engine_profile != "piper_kmr"
        text_input.rtl = is_arabic
        text_input.text_align = (
            ft.TextAlign.RIGHT if is_arabic else ft.TextAlign.LEFT
        )
        input_label_primary.value = (
            t("input_label_ar") if is_arabic else t("input_label_primary")
        )
        input_label_primary.rtl = is_arabic or page.rtl
        input_label_primary.text_align = (
            ft.TextAlign.RIGHT if (is_arabic or page.rtl) else ft.TextAlign.LEFT
        )
        text_input.hint_text = (
            t("input_hint_ar") if is_arabic else t("input_hint")
        )
        input_label_secondary.value = (
            "" if is_arabic else t("input_label_secondary")
        )
        speaker_dropdown.disabled = is_mms
        if is_mms:
            speaker_dropdown.options = [
                ft.dropdown.Option(
                    key="0",
                    text=t("mms_arabic") if is_arabic else t("mms_speaker_0"),
                )
            ]
            speaker_dropdown.value = "0"
        engine_profile_dropdown.label = t("engine_profile")
        engine_profile_dropdown.tooltip = t("engine_profile_tooltip")
        engine_profile_dropdown.value = settings.engine_profile
        rebuild_sample_chips()

    speed_value_text = ft.Text(_ltr(f"{settings.speech_speed:.2f}x"), size=13)
    speed_caption_text = ft.Text(t("speed"), size=13)
    speed_label = ft.Row([speed_caption_text, speed_value_text], spacing=4, tight=True)

    def on_speed_change(e: ft.ControlEvent) -> None:
        settings.speech_speed = round(float(e.control.value), 2)
        speed_value_text.value = _ltr(f"{settings.speech_speed:.2f}x")
        page.update()

    speed_slider = ft.Slider(
        min=0.5,
        max=1.5,
        divisions=100,
        value=settings.speech_speed,
        width=180,
        tooltip=t("speed_tooltip"),
        on_change=on_speed_change,
    )

    progress_bar = ft.ProgressBar(visible=False, border_radius=6)

    play_button = ft.FilledTonalButton(
        content=t("play"), icon=ft.Icons.PLAY_ARROW, disabled=True
    )
    pause_button = ft.OutlinedButton(
        content=t("pause"), icon=ft.Icons.PAUSE, disabled=True
    )
    stop_button = ft.OutlinedButton(
        content=t("stop"), icon=ft.Icons.STOP, disabled=True
    )
    save_wav_button = ft.FilledButton(
        content=t("save_wav"), icon=ft.Icons.DOWNLOAD, disabled=True
    )

    playback_slider = ft.Slider(
        min=0, max=100, value=0, disabled=True, expand=True
    )
    time_display_text = ft.Text(
        _ltr("00:00 / 00:00"), size=12, weight=ft.FontWeight.W_500
    )
    metric_gen_text = ft.Text(_ltr("—"), size=12, color=ft.Colors.OUTLINE)
    metric_duration_text = ft.Text(_ltr("—"), size=12, color=ft.Colors.OUTLINE)
    metric_rtf_combined = ft.Text("RTF: —", size=12, rtl=False, color=ft.Colors.OUTLINE)
    last_rtf: Optional[float] = None
    metric_rate_text = ft.Text(_ltr("—"), size=12, color=ft.Colors.OUTLINE)
    metric_speaker_text = ft.Text(_ltr("—"), size=12, color=ft.Colors.OUTLINE)
    metric_gen_label = ft.Text(t("metric_gen"), size=12, color=ft.Colors.OUTLINE)
    metric_duration_label = ft.Text(t("metric_duration"), size=12, color=ft.Colors.OUTLINE)
    metric_rate_label = ft.Text(t("metric_rate"), size=12, color=ft.Colors.OUTLINE)
    metric_speaker_label = ft.Text(t("metric_speaker"), size=12, color=ft.Colors.OUTLINE)
    metrics_row = ft.Row(
        [
            ft.Row([metric_gen_label, metric_gen_text], spacing=4, tight=True),
            ft.Text("|", size=12, color=ft.Colors.OUTLINE),
            ft.Row([metric_duration_label, metric_duration_text], spacing=4, tight=True),
            ft.Text("|", size=12, color=ft.Colors.OUTLINE),
            metric_rtf_combined,
            ft.Text("|", size=12, color=ft.Colors.OUTLINE),
            ft.Row([metric_rate_label, metric_rate_text], spacing=4, tight=True),
            ft.Text("|", size=12, color=ft.Colors.OUTLINE),
            ft.Row([metric_speaker_label, metric_speaker_text], spacing=4, tight=True),
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        wrap=True,
        spacing=8,
        expand=True,
    )

    def update_player_buttons(state: PlaybackState, has_audio: bool) -> None:
        audio_session.set_state(state)
        play_button.disabled = not has_audio or state == PlaybackState.PLAYING
        pause_button.disabled = not has_audio or state != PlaybackState.PLAYING
        stop_button.disabled = not has_audio or state in (PlaybackState.IDLE, PlaybackState.STOPPED)
        save_wav_button.disabled = not has_audio
        playback_slider.disabled = not has_audio

    def _reset_progress_display() -> None:
        playback_slider.value = 0
        if audio_session.current_info:
            time_display_text.value = _ltr(
                f"00:00 / {format_seconds(audio_session.current_info.duration_seconds)}"
            )
        else:
            time_display_text.value = _ltr("00:00 / 00:00")

    def _cancel_progress_task() -> None:
        nonlocal progress_task
        if progress_task is not None and not progress_task.done():
            progress_task.cancel()
        progress_task = None

    def _on_playback_finished() -> None:
        _cancel_progress_task()
        _reset_progress_display()
        update_player_buttons(PlaybackState.STOPPED, has_audio=audio_session.current_wav is not None)
        page.update()

    async def _progress_loop() -> None:
        """Poll the embedded player every 100 ms while audio is actually playing."""
        try:
            while True:
                await asyncio.sleep(0.1)
                total_s = (
                    audio_session.current_info.duration_seconds
                    if audio_session.current_info is not None else 0.0
                )
                total_ms = max(1, int(total_s * 1000))
                pos_ms = max(0, inapp_player.get_position_ms())
                playback_slider.value = min(100.0, max(0.0, pos_ms / total_ms * 100.0))
                time_display_text.value = _ltr(
                    f"{format_seconds(pos_ms / 1000.0)} / {format_seconds(total_s)}"
                )
                if audio_session.state != PlaybackState.PLAYING:
                    return
                if not inapp_player.is_playing():
                    _on_playback_finished()
                    return
                page.update()
        except asyncio.CancelledError:
            return

    async def on_slider_seek(e: ft.ControlEvent) -> None:
        if audio_session.current_info is None:
            return
        target_ms = int(
            (float(e.control.value) / 100.0)
            * audio_session.current_info.duration_seconds * 1000
        )
        try:
            inapp_player.seek(target_ms)
        except Exception as exc:
            show_error(t("error_seek", error=exc))
            return
        time_display_text.value = _ltr(
            f"{format_seconds(target_ms / 1000.0)} / "
            f"{format_seconds(audio_session.current_info.duration_seconds)}"
        )
        page.update()

    playback_slider.on_change_end = on_slider_seek

    async def handle_play(_: ft.ControlEvent) -> None:
        if audio_session.current_wav is None or not audio_session.current_wav.exists():
            show_error(t("error_no_audio"))
            return
        try:
            if audio_session.state == PlaybackState.PAUSED:
                inapp_player.resume()
            else:
                inapp_player.play()
        except Exception as exc:
            show_error(t("error_play", error=exc))
            return

        update_player_buttons(PlaybackState.PLAYING, has_audio=True)
        _cancel_progress_task()
        progress_task = asyncio.create_task(_progress_loop())
        page.update()

    async def handle_pause(_: ft.ControlEvent) -> None:
        _cancel_progress_task()
        update_player_buttons(PlaybackState.PAUSED, has_audio=True)
        try:
            inapp_player.pause()
        except Exception:
            pass
        page.update()

    async def handle_stop(_: ft.ControlEvent) -> None:
        _cancel_progress_task()
        update_player_buttons(PlaybackState.STOPPED, has_audio=audio_session.current_wav is not None)
        try:
            inapp_player.stop()
        except Exception:
            pass
        _reset_progress_display()
        page.update()

    play_button.on_click = handle_play
    pause_button.on_click = handle_pause
    stop_button.on_click = handle_stop

    save_picker = ft.FilePicker()
    model_picker = ft.FilePicker()
    piper_picker = ft.FilePicker()
    page.services.extend([save_picker, model_picker, piper_picker])

    async def handle_save_wav(_: ft.ControlEvent) -> None:
        if audio_session.current_wav is None:
            show_error(t("error_save_first"))
            return
        target = await save_picker.save_file(
            dialog_title=t("save_dialog_title"),
            file_name="kurmanji_tts_output.wav",
            allowed_extensions=["wav"],
        )
        if not target:
            return
        try:
            saved_path = audio_session.export_wav(Path(target))
            show_snack(t("save_ok", name=saved_path.name))
        except Exception as exc:
            show_error(t("save_failed", error=exc))

    save_wav_button.on_click = handle_save_wav

    def refresh_engine_status() -> None:
        status = engine.check_status()
        if status.ready and status.metadata is not None:
            meta = status.metadata
            model_status_icon.color = ft.Colors.GREEN
            model_status_text.value = t("model_ready")
            model_status_details.value = _ltr(
                f"{meta.sample_rate} Hz | {meta.num_speakers} | ★ {meta.default_speaker_id}"
            )
            speaker_dropdown.options = [
                ft.dropdown.Option(key=str(sid), text=label)
                for sid, label in meta.speakers
            ]
            current_val = speaker_dropdown.value
            valid_keys = {str(sid) for sid, _ in meta.speakers}
            if current_val not in valid_keys or current_val != str(meta.default_speaker_id):
                speaker_dropdown.value = str(meta.default_speaker_id)
        else:
            model_status_icon.color = ft.Colors.RED
            model_status_text.value = t("model_not_ready")
            model_status_details.value = _ltr("")
            show_error(f"{status.message}\n{t('engine_hint')}")

    async def handle_generate(_: ft.ControlEvent) -> None:
        nonlocal is_generating, last_rtf
        if is_generating:
            return

        hide_error()
        is_valid, normalized_text, validation_err = validate_kurmanji_input(
            text_input.value or "",
            max_chars=settings.max_text_length,
        )
        if not is_valid:
            show_error(validation_err)
            return

        text_input.value = normalized_text
        on_text_changed()

        if settings.engine_profile == "piper_kmr":
            selected_sid = int(speaker_dropdown.value or settings.default_speaker_id)
        else:
            selected_sid = 0
        _cancel_progress_task()
        inapp_player.close()
        target_wav = audio_session.allocate_output_path()

        is_generating = True
        generate_button.disabled = True
        progress_bar.visible = True
        page.update()

        if settings.engine_profile == "mms_kmr":
            tts_text = prepare_text_for_mms(normalized_text, "kmr")
        elif settings.engine_profile == "mms_ara":
            tts_text = prepare_text_for_mms(normalized_text, "ar")
        else:
            tts_text = prepare_text_for_tts(normalized_text, voice_lang="ku")
        if not tts_text.strip():
            show_error(validation_err or t("validate_symbols"))
            return
        length_scale = round(1.0 / settings.speech_speed, 3)
        try:
            result = await asyncio.to_thread(
                engine.synthesize,
                tts_text,
                target_wav,
                selected_sid,
                length_scale,
                settings.noise_scale,
                settings.noise_w,
            )
            wav_info = audio_session.register_generated_wav(result.wav_path)
            try:
                inapp_player.load(wav_info.path)
            except Exception as exc:
                raise TTSEngineError(t("load_in_app_failed", error=exc)) from exc

            _reset_progress_display()
            metric_gen_text.value = _ltr(f"{result.generation_time_seconds:.2f}s")
            metric_duration_text.value = _ltr(f"{wav_info.duration_seconds:.2f}s")
            last_rtf = result.real_time_factor
            metric_rtf_combined.value = f"RTF: {last_rtf:.2f}"
            metric_rate_text.value = _ltr(f"{result.sample_rate} Hz")
            metric_speaker_text.value = _ltr(str(result.speaker_id))
            update_player_buttons(PlaybackState.STOPPED, has_audio=True)
            show_snack(t("generate_ok"))
        except TTSEngineError as exc:
            show_error(str(exc))
        except Exception as exc:
            show_error(t("generate_failed", error=exc))
        finally:
            is_generating = False
            generate_button.disabled = False
            progress_bar.visible = False
            page.update()

    generate_button = ft.FilledButton(
        content=t("generate"),
        icon=ft.Icons.GRAPHIC_EQ,
        height=46,
        on_click=handle_generate,
    )

    def toggle_theme(_: ft.ControlEvent) -> None:
        if page.theme_mode == ft.ThemeMode.DARK:
            page.theme_mode = ft.ThemeMode.LIGHT
            settings.theme_mode = "light"
            theme_button.icon = ft.Icons.DARK_MODE
        else:
            page.theme_mode = ft.ThemeMode.DARK
            settings.theme_mode = "dark"
            theme_button.icon = ft.Icons.LIGHT_MODE
        settings.save()
        page.update()

    theme_button = ft.IconButton(
        icon=ft.Icons.LIGHT_MODE if page.theme_mode == ft.ThemeMode.DARK else ft.Icons.DARK_MODE,
        tooltip=t("theme_tooltip"),
        on_click=toggle_theme,
    )

    def open_settings_dialog(_: ft.ControlEvent) -> None:
        dialog_rtl = is_rtl(current_lang)

        # Labels are separate controls: the Arabic label follows the page
        # direction while the Latin path itself stays strictly LTR.
        model_label = _mixed_text_row(
            dialog_rtl,
            [(t("model_label_primary"), False), (t("model_label_secondary"), True)],
        )
        piper_label = _mixed_text_row(
            dialog_rtl,
            [
                (t("piper_label_primary"), False),
                (t("piper_label_middle"), True),
                (t("piper_label_suffix"), False),
            ],
        )
        title_row = _mixed_text_row(
            dialog_rtl,
            [(t("settings_title_primary"), False), (t("settings_title_secondary"), True)],
            size=20,
            color=None,
        )
        note_text = ft.Text(
            t("settings_note_clean"),
            size=12,
            color=ft.Colors.OUTLINE,
            text_align=ft.TextAlign.RIGHT if dialog_rtl else ft.TextAlign.LEFT,
        )

        model_field = ft.TextField(
            value=settings.model_path,
            text_align=ft.TextAlign.LEFT,
            text_size=13,
            expand=True,
        )
        piper_field = ft.TextField(
            value=settings.piper_path,
            text_align=ft.TextAlign.LEFT,
            text_size=13,
            expand=True,
        )

        async def browse_model(_: ft.ControlEvent) -> None:
            picked = await model_picker.pick_files(
                dialog_title=t("pick_model"), allowed_extensions=["onnx"]
            )
            if picked:
                model_field.value = picked[0].path or ""
                page.update()

        async def browse_piper(_: ft.ControlEvent) -> None:
            picked = await piper_picker.pick_files(dialog_title=t("pick_piper"))
            if picked:
                piper_field.value = picked[0].path or ""
                page.update()

        settings_fields = ft.Container(
            width=650,
            rtl=dialog_rtl,
            content=ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[
                    model_label,
                    ft.Row(
                        [
                            ft.Container(content=model_field, rtl=False, expand=True),
                            ft.IconButton(
                                icon=ft.Icons.FOLDER_OPEN,
                                tooltip=t("browse_model"),
                                on_click=browse_model,
                            ),
                        ],
                        spacing=6,
                    ),
                    piper_label,
                    ft.Row(
                        [
                            ft.Container(content=piper_field, rtl=False, expand=True),
                            ft.IconButton(
                                icon=ft.Icons.FOLDER_OPEN,
                                tooltip=t("browse_piper"),
                                on_click=browse_piper,
                            ),
                        ],
                        spacing=6,
                    ),
                ],
                spacing=12,
            ),
        )
        persistent_switch = ft.Switch(label=t("persistent"), value=settings.use_persistent_process)

        def save_dialog_settings(_: ft.ControlEvent) -> None:
            settings.model_path = model_field.value.strip()
            settings.piper_path = piper_field.value.strip()
            settings.use_persistent_process = bool(persistent_switch.value)
            settings.save()
            hide_error()
            engine.update_paths(
                piper_path=Path(settings.piper_path),
                model_path=Path(settings.model_path),
                preferred_speaker=settings.default_speaker_id,
                use_persistent_process=settings.use_persistent_process,
            )
            refresh_engine_status()
            page.pop_dialog()
            page.update()

        dialog = ft.AlertDialog(
            modal=True,
            rtl=dialog_rtl,
            title=title_row,
            content=ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[
                    settings_fields,
                    persistent_switch,
                    note_text,
                ],
                tight=True,
                spacing=14,
            ),
            actions=[
                ft.TextButton(t("cancel"), on_click=lambda _: page.pop_dialog()),
                ft.FilledButton(t("save_settings"), on_click=save_dialog_settings),
            ],
        )
        page.show_dialog(dialog)

    settings_button = ft.IconButton(
        icon=ft.Icons.SETTINGS_OUTLINED,
        tooltip=t("settings_tooltip"),
        on_click=open_settings_dialog,
    )

    language_dropdown = ft.Dropdown(
        width=125,
        value=current_lang,
        tooltip=t("language"),
        options=[
            ft.dropdown.Option(key="ar", text="العربية"),
            ft.dropdown.Option(key="ku", text="Kurdî"),
            ft.dropdown.Option(key="en", text="English"),
        ],
    )

    subtitle_text = ft.Text(
        t("app_subtitle"), size=12, color=ft.Colors.OUTLINE
    )
    samples_label_text = ft.Text(
        t("label_samples"), size=12, color=ft.Colors.OUTLINE
    )
    clear_text_button = ft.TextButton(
        t("clear_text"),
        icon=ft.Icons.CLEAR_ALL,
        on_click=lambda _: insert_sample_text(""),
    )

    def apply_engine_profile(profile: str) -> None:
        """Swap synthesis engine, model, speaker list and input direction."""
        chosen = profile if profile in ENGINE_PROFILES else "piper_kmr"
        settings.engine_profile = chosen
        settings.model_path = str(model_path_for_profile(get_app_root(), chosen))
        settings.tts_language = "ar" if chosen == "mms_ara" else "ku"
        settings.save()
        engine.set_profile(chosen)
        engine.update_paths(
            piper_path=Path(settings.piper_path),
            model_path=Path(settings.model_path),
            preferred_speaker=DEFAULT_SPEAKER_ID,
            use_persistent_process=settings.use_persistent_process,
        )
        refresh_profile_ui()
        refresh_engine_status()
        page.update()

    def on_engine_profile_changed(e: ft.ControlEvent) -> None:
        selected = getattr(e, "data", None)
        if selected not in ENGINE_PROFILES:
            control = getattr(e, "control", None)
            selected = getattr(control, "value", None) if control is not None else None
        apply_engine_profile(str(selected) if selected else settings.engine_profile)

    engine_profile_dropdown.on_select = on_engine_profile_changed
    engine_profile_dropdown.on_change = on_engine_profile_changed

    def apply_language(lang: str) -> None:
        """Switch all visible strings and the page direction instantly."""
        nonlocal current_lang
        chosen = lang if lang in ("ar", "ku", "en") else "ar"
        current_lang = chosen
        settings.ui_language = chosen
        settings.save()
        set_current_language(chosen)
        page.rtl = is_rtl(chosen)

        subtitle_text.value = t("app_subtitle")
        model_status_text.value = t("model_checking")
        close_error_button.tooltip = t("close_notification")
        char_label_text.value = t("label_chars")
        word_label_text.value = t("label_words")
        hawar_label_text.value = t("label_hawar")
        samples_label_text.value = t("label_samples")
        clear_text_button.content = t("clear_text")
        refresh_profile_ui()
        speaker_dropdown.label = t("speaker")
        speed_caption_text.value = t("speed")
        speed_slider.tooltip = t("speed_tooltip")
        generate_button.content = t("generate")
        play_button.content = t("play")
        pause_button.content = t("pause")
        stop_button.content = t("stop")
        save_wav_button.content = t("save_wav")
        metric_gen_label.value = t("metric_gen")
        metric_duration_label.value = t("metric_duration")
        metric_rtf_combined.value = (
            f"RTF: {last_rtf:.2f}" if last_rtf is not None else "RTF: —"
        )
        metric_rate_label.value = t("metric_rate")
        metric_speaker_label.value = t("metric_speaker")
        theme_button.tooltip = t("theme_tooltip")
        settings_button.tooltip = t("settings_tooltip")
        language_dropdown.tooltip = t("language")
        language_dropdown.value = chosen
        refresh_engine_status()
        page.update()

    def on_language_changed(e: ft.ControlEvent) -> None:
        """Flet 0.86 Dropdown fires on_select (on_change is a text-field event)."""
        selected = getattr(e, "data", None)
        if selected not in ("ar", "ku", "en"):
            control = getattr(e, "control", None)
            selected = getattr(control, "value", None) if control is not None else None
        apply_language(str(selected) if selected else current_lang)

    language_dropdown.on_select = on_language_changed
    # Kept for compatibility with older Flet builds that still fired on_change.
    language_dropdown.on_change = on_language_changed

    header = ft.Row(
        controls=[
            ft.Row(
                [
                    ft.Icon(ft.Icons.RECORD_VOICE_OVER, size=30, color=ft.Colors.PRIMARY),
                    ft.Column(
                        [
                            ft.Text(APP_NAME, size=22, weight=ft.FontWeight.BOLD),
                            subtitle_text,
                        ],
                        spacing=0,
                    ),
                ],
                spacing=12,
            ),
            ft.Row(
                [model_status_badge, language_dropdown, settings_button, theme_button],
                spacing=6,
            ),
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
    )

    input_card = ft.Card(
        expand=True,
        content=ft.Container(
            padding=18,
            expand=True,
            content=ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                expand=True,
                controls=[
                    ft.Row(
                        [
                            samples_label_text,
                            clear_text_button,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    sample_chips,
                    input_label_row,
                    ft.Container(content=text_input, rtl=False, expand=True),
                    counters_row,
                ],
                spacing=12,
            ),
        ),
    )

    controls_card = ft.Card(
        content=ft.Container(
            padding=18,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            engine_profile_dropdown,
                            speaker_dropdown,
                            ft.Column([speed_label, speed_slider], spacing=0),
                            generate_button,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        wrap=True,
                    ),
                    progress_bar,
                ],
                spacing=12,
            ),
        )
    )

    player_card = ft.Card(
        content=ft.Container(
            padding=18,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            play_button,
                            pause_button,
                            stop_button,
                            playback_slider,
                            time_display_text,
                        ],
                        spacing=10,
                    ),
                    ft.Divider(height=1),
                    ft.Row(
                        [metrics_row, save_wav_button],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                ],
                spacing=12,
            ),
        )
    )

    def on_disconnect(_: ft.ControlEvent) -> None:
        _cancel_progress_task()
        inapp_player.close()
        engine.close()
        audio_session.shutdown()

    page.on_disconnect = on_disconnect

    page.add(
        ft.Column(
            [header, error_banner, input_card, controls_card, player_card],
            spacing=14,
        )
    )

    refresh_profile_ui()
    refresh_engine_status()
    page.update()


if __name__ == "__main__":
    ft.run(main)
