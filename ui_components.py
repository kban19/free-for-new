# Copyright (c) 2026 Kurmanji-TTS Team. All Rights Reserved.
# Proprietary and Confidential. Unauthorized copying, distribution, or modification
# of this file, via any medium, is strictly prohibited.

"""Widget construction for the Kurmanji-TTS window.

Every function here turns plain values into Flet controls: no settings file, no
engine, no event loop and no ``page.update()``. ``main.py`` attaches behaviour to
the objects returned by these builders, so the layout can be read on its own and
the behaviour can be read on its own.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Callable, Mapping, Sequence

import flet as ft

from config import APP_NAME

# Latin/numeric values are wrapped in these two marks inside RTL paragraphs;
# without them "RTF: 0.08" can be reordered into "0.08 :RTF" by the text engine.
ISOLATE_START = "\u2066"
ISOLATE_END = "\u2069"


def ltr(value: object) -> str:
    """Isolate Latin/numeric text so an RTL context cannot reorder it."""
    return f"{ISOLATE_START}{value}{ISOLATE_END}"


def mixed_text_row(
    page_is_rtl: bool,
    parts: Sequence[tuple],
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


def build_top_bar(t: Callable[..., str], lang: str, dark: bool) -> SimpleNamespace:
    """Status pill, app identity, language switcher and the two window actions."""
    icon = ft.Icon(ft.Icons.CIRCLE, size=12, color=ft.Colors.AMBER)
    text = ft.Text(t("model_checking"), size=13, weight=ft.FontWeight.W_500)
    details = ft.Text(ltr(""), size=11, color=ft.Colors.OUTLINE)
    badge = ft.Container(
        content=ft.Row([icon, text, details], spacing=6, tight=True),
        padding=ft.Padding.symmetric(horizontal=12, vertical=6),
        border_radius=20,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
    )
    subtitle = ft.Text(t("app_subtitle"), size=12, color=ft.Colors.OUTLINE)
    language = ft.Dropdown(
        width=125,
        value=lang,
        tooltip=t("language"),
        options=[
            ft.dropdown.Option(key="ar", text="العربية"),
            ft.dropdown.Option(key="ku", text="Kurdî"),
            ft.dropdown.Option(key="en", text="English"),
        ],
    )
    settings_button = ft.IconButton(
        icon=ft.Icons.SETTINGS_OUTLINED, tooltip=t("settings_tooltip")
    )
    theme_button = ft.IconButton(
        icon=ft.Icons.LIGHT_MODE if dark else ft.Icons.DARK_MODE,
        tooltip=t("theme_tooltip"),
    )
    header = build_header(badge, subtitle, language, settings_button, theme_button)
    return SimpleNamespace(
        status_badge=badge,
        status_icon=icon,
        status_text=text,
        status_details=details,
        subtitle=subtitle,
        language_dropdown=language,
        settings_button=settings_button,
        theme_button=theme_button,
        header=header,
    )


def build_header(
    status_badge: ft.Container,
    subtitle: ft.Text,
    language_dropdown: ft.Dropdown,
    settings_button: ft.IconButton,
    theme_button: ft.IconButton,
) -> ft.Row:
    """Top bar: identity on the start side, status and actions on the end side."""
    return ft.Row(
        controls=[
            ft.Row(
                [
                    ft.Icon(
                        ft.Icons.RECORD_VOICE_OVER, size=30, color=ft.Colors.PRIMARY
                    ),
                    ft.Column(
                        [
                            ft.Text(APP_NAME, size=22, weight=ft.FontWeight.BOLD),
                            subtitle,
                        ],
                        spacing=0,
                    ),
                ],
                spacing=12,
            ),
            ft.Row(
                [status_badge, language_dropdown, settings_button, theme_button],
                spacing=6,
            ),
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
    )


def build_error_banner(t: Callable[..., str]) -> SimpleNamespace:
    """Dismissible inline banner; errors never open a modal in this window."""
    text = ft.Text("", color=ft.Colors.ON_ERROR_CONTAINER, size=13, expand=True)
    close = ft.IconButton(
        icon=ft.Icons.CLOSE, icon_size=16, tooltip=t("close_notification")
    )
    banner = ft.Container(
        content=ft.Row(
            [
                ft.Icon(ft.Icons.ERROR_OUTLINE, color=ft.Colors.ERROR, size=20),
                text,
                close,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        ),
        bgcolor=ft.Colors.ERROR_CONTAINER,
        border_radius=10,
        padding=ft.Padding.symmetric(horizontal=14, vertical=8),
        visible=False,
    )
    return SimpleNamespace(error_banner=banner, error_text=text, error_close=close)


def build_counter_bar(t: Callable[..., str]) -> SimpleNamespace:
    """Character, word and Hawar counters shown under the editor."""
    char_label = ft.Text(t("label_chars"), size=12, color=ft.Colors.OUTLINE)
    word_label = ft.Text(t("label_words"), size=12, color=ft.Colors.OUTLINE)
    hawar_label = ft.Text(t("label_hawar"), size=12, color=ft.Colors.OUTLINE)
    char_value = ft.Text(ltr("0"), size=12, color=ft.Colors.OUTLINE)
    word_value = ft.Text(ltr("0"), size=12, color=ft.Colors.OUTLINE)
    hawar_value = ft.Text(ltr("—"), size=12, color=ft.Colors.PRIMARY)
    row = ft.Row(
        [
            ft.Row([char_label, char_value], spacing=4, tight=True),
            ft.Text("|", size=12, color=ft.Colors.OUTLINE),
            ft.Row([word_label, word_value], spacing=4, tight=True),
            ft.Row([hawar_label, hawar_value], spacing=4, tight=True),
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        wrap=True,
        spacing=10,
    )
    return SimpleNamespace(
        counters_row=row,
        char_label=char_label,
        char_value=char_value,
        word_label=word_label,
        word_value=word_value,
        hawar_label=hawar_label,
        hawar_value=hawar_value,
    )


def build_editor(t: Callable[..., str]) -> SimpleNamespace:
    """Editor label and the multiline field; the card adds the LTR container."""
    primary = ft.Text(
        t("input_label_primary"),
        size=12,
        color=ft.Colors.OUTLINE,
        text_align=ft.TextAlign.LEFT,
    )
    secondary = ft.Text(
        t("input_label_secondary"),
        size=12,
        color=ft.Colors.OUTLINE,
        rtl=False,
        text_align=ft.TextAlign.LEFT,
    )
    field = ft.TextField(
        hint_text=t("input_hint"),
        multiline=True,
        min_lines=5,
        max_lines=9,
        text_size=16,
        rtl=False,
        text_align=ft.TextAlign.LEFT,
        border_radius=12,
        expand=True,
    )
    return SimpleNamespace(
        input_label_primary=primary,
        input_label_secondary=secondary,
        input_label_row=ft.Row([primary, secondary], spacing=6),
        text_input=field,
    )


def build_samples(t: Callable[..., str]) -> SimpleNamespace:
    """Sample caption, clear button and the empty row the chips are poured into."""
    return SimpleNamespace(
        samples_label=ft.Text(t("label_samples"), size=12, color=ft.Colors.OUTLINE),
        clear_button=ft.TextButton(t("clear_text"), icon=ft.Icons.CLEAR_ALL),
        sample_chips=ft.Row(wrap=True, spacing=8),
    )


def build_sample_chips(
    samples: Mapping[str, str], on_pick: Callable[[str], None]
) -> list:
    """One chip per ready-made example; ``on_pick`` receives the full text."""
    return [
        ft.Chip(
            label=ft.Text(label, size=12),
            leading=ft.Icons.TEXT_SNIPPET_OUTLINED,
            show_checkmark=False,
            on_click=lambda _, txt=content: on_pick(txt),
        )
        for label, content in samples.items()
    ]


def build_selectors(t: Callable[..., str], settings) -> SimpleNamespace:
    """Engine profile and speaker dropdowns, before the first readiness check."""
    speaker = ft.Dropdown(
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
    profile = ft.Dropdown(
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
    return SimpleNamespace(profile_dropdown=profile, speaker_dropdown=speaker)


def build_speed_control(t: Callable[..., str], settings) -> SimpleNamespace:
    """Speed caption, its live value and the 0.50x-1.50x slider."""
    caption = ft.Text(t("speed"), size=13)
    value = ft.Text(ltr(f"{settings.speech_speed:.2f}x"), size=13)
    slider = ft.Slider(
        min=0.5,
        max=1.5,
        divisions=100,
        value=settings.speech_speed,
        width=180,
        tooltip=t("speed_tooltip"),
    )
    return SimpleNamespace(
        speed_caption=caption,
        speed_value=value,
        speed_slider=slider,
        speed_label=ft.Row([caption, value], spacing=4, tight=True),
    )


def build_controls_card(
    profile_dropdown: ft.Dropdown,
    speaker_dropdown: ft.Dropdown,
    speed_label: ft.Row,
    speed_slider: ft.Slider,
    generate_button: ft.FilledButton,
    progress_bar: ft.ProgressBar,
) -> ft.Card:
    """Engine card: which voice, which speaker, how fast, and the generate button."""
    return ft.Card(
        content=ft.Container(
            padding=18,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            profile_dropdown,
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


def build_player_controls(t: Callable[..., str]) -> SimpleNamespace:
    """Transport buttons, seek slider, time label and the export button."""
    play = ft.FilledTonalButton(
        content=t("play"), icon=ft.Icons.PLAY_ARROW, disabled=True
    )
    pause = ft.OutlinedButton(content=t("pause"), icon=ft.Icons.PAUSE, disabled=True)
    stop = ft.OutlinedButton(content=t("stop"), icon=ft.Icons.STOP, disabled=True)
    save = ft.FilledButton(content=t("save_wav"), icon=ft.Icons.DOWNLOAD, disabled=True)
    slider = ft.Slider(min=0, max=100, value=0, disabled=True, expand=True)
    time_label = ft.Text(ltr("00:00 / 00:00"), size=12, weight=ft.FontWeight.W_500)
    return SimpleNamespace(
        play_button=play,
        pause_button=pause,
        stop_button=stop,
        save_button=save,
        playback_slider=slider,
        time_display=time_label,
    )


def build_metrics_row(t: Callable[..., str]) -> SimpleNamespace:
    """Generation time, duration, RTF, sample rate and speaker, all in one row."""
    gen_label = ft.Text(t("metric_gen"), size=12, color=ft.Colors.OUTLINE)
    duration_label = ft.Text(t("metric_duration"), size=12, color=ft.Colors.OUTLINE)
    rate_label = ft.Text(t("metric_rate"), size=12, color=ft.Colors.OUTLINE)
    speaker_label = ft.Text(t("metric_speaker"), size=12, color=ft.Colors.OUTLINE)
    gen_value = ft.Text(ltr("—"), size=12, color=ft.Colors.OUTLINE)
    duration_value = ft.Text(ltr("—"), size=12, color=ft.Colors.OUTLINE)
    rtf_value = ft.Text("RTF: —", size=12, rtl=False, color=ft.Colors.OUTLINE)
    rate_value = ft.Text(ltr("—"), size=12, color=ft.Colors.OUTLINE)
    speaker_value = ft.Text(ltr("—"), size=12, color=ft.Colors.OUTLINE)
    separator = lambda: ft.Text("|", size=12, color=ft.Colors.OUTLINE)
    row = ft.Row(
        [
            ft.Row([gen_label, gen_value], spacing=4, tight=True),
            separator(),
            ft.Row([duration_label, duration_value], spacing=4, tight=True),
            separator(),
            rtf_value,
            separator(),
            ft.Row([rate_label, rate_value], spacing=4, tight=True),
            separator(),
            ft.Row([speaker_label, speaker_value], spacing=4, tight=True),
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        wrap=True,
        spacing=8,
        expand=True,
    )
    return SimpleNamespace(
        metrics_row=row,
        metric_gen_label=gen_label,
        metric_gen_value=gen_value,
        metric_duration_label=duration_label,
        metric_duration_value=duration_value,
        metric_rtf=rtf_value,
        metric_rate_label=rate_label,
        metric_rate_value=rate_value,
        metric_speaker_label=speaker_label,
        metric_speaker_value=speaker_value,
    )


def build_player_card(
    play_button: ft.FilledTonalButton,
    pause_button: ft.OutlinedButton,
    stop_button: ft.OutlinedButton,
    playback_slider: ft.Slider,
    time_display_text: ft.Text,
    metrics_row: ft.Row,
    save_button: ft.FilledButton,
) -> ft.Card:
    """Player card: transport controls, progress, measured metrics and export."""
    return ft.Card(
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
                        [metrics_row, save_button],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                ],
                spacing=12,
            ),
        )
    )
