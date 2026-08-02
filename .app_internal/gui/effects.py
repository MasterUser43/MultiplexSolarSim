"""
Small, generic Qt visual-craft helpers w/o business-logic dependency.
Any panel can call these.
"""
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup, QAbstractAnimation
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QGraphicsOpacityEffect


def set_glow(widget, color_hex, enabled, blur_radius=10):
    """Centered glow (no offset), toggled on/off -- Qt QSS has no
    box-shadow equivalent, so the mockup's `.trace.active`/`.pixel-pad.active`
    glow needs a real QGraphicsEffect instead of a QSS rule. Safe to call
    repeatedly (e.g. every time a pin's active state toggles): creates the
    effect once, then just flips visibility after that.
    """
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsDropShadowEffect):
        effect = QGraphicsDropShadowEffect(widget)
        effect.setXOffset(0)
        effect.setYOffset(0)
        widget.setGraphicsEffect(effect)
    effect.setEnabled(enabled)
    if enabled:
        effect.setBlurRadius(blur_radius)
        effect.setColor(QColor(color_hex))


def make_panel_shadow(widget, is_dark_mode=False):
    """Aesthetic choice that adds a shadow for more eye juicing.

    Returns the effect so the caller can keep a reference and later call
    `update_shadow_color()` on it when the theme changes.
    """
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(20)
    effect.setXOffset(0)
    effect.setYOffset(4)
    effect.setColor(QColor(0, 0, 0, 90 if is_dark_mode else 25))
    widget.setGraphicsEffect(effect)
    return effect


def update_shadow_color(effect, is_dark_mode):
    if effect is not None:
        effect.setColor(QColor(0, 0, 0, 90 if is_dark_mode else 25))


def refresh_led_glow(led, colors):
    """LED glower, similar to the shadow function above; purely visual."""
    state = led.property("status")
    glow_color = {"ok": colors["success"], "bad": colors["error"]}.get(state)

    if glow_color:
        effect = led.graphicsEffect()
        if not isinstance(effect, QGraphicsDropShadowEffect):
            effect = QGraphicsDropShadowEffect(led)
            effect.setBlurRadius(14)
            effect.setXOffset(0)
            effect.setYOffset(0)
            led.setGraphicsEffect(effect)
        effect.setColor(QColor(glow_color))
    else:
        led.setGraphicsEffect(None)


def set_status_led(led, label, state):
    """Updates the status property of an LED + its label and repolishes them."""
    led.setProperty("status", state)
    label.setProperty("status", state)

    # Force Qt to reload stylesheet
    led.style().unpolish(led)
    led.style().polish(led)
    label.style().unpolish(label)
    label.style().polish(label)


def animate_tab_switch(tabs, index, anim_owner):
    """Fades the newly-selected tab's content in while sliding it up a few
    pixels."""
    widget = tabs.widget(index)
    if widget is None:
        return None

    animations = []
    already_has_effect = widget.graphicsEffect() is not None

    if not already_has_effect:
        opacity_effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(opacity_effect)

        fade = QPropertyAnimation(opacity_effect, b"opacity", anim_owner)
        fade.setDuration(250)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.OutCubic)
        animations.append(fade)

    end_rect = widget.geometry()
    start_rect = end_rect.translated(0, 8)
    slide = QPropertyAnimation(widget, b"geometry", anim_owner)
    slide.setDuration(250)
    slide.setStartValue(start_rect)
    slide.setEndValue(end_rect)
    slide.setEasingCurve(QEasingCurve.OutCubic)
    animations.append(slide)

    group = QParallelAnimationGroup(anim_owner)
    for anim in animations:
        group.addAnimation(anim)

    if not already_has_effect:
        # Drop the opacity effect once the animation finishes.
        group.finished.connect(lambda: widget.setGraphicsEffect(None))
    group.start(QAbstractAnimation.DeleteWhenStopped)
    return group
