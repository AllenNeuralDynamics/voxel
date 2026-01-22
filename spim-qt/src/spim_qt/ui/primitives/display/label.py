"""Label primitives with consistent styling variants."""

from typing import ClassVar, Literal

from PySide6.QtWidgets import QLabel, QWidget

from spim_qt.ui.theme import BorderRadius, Colors, Spacing

LabelVariant = Literal["default", "title", "section", "value", "muted", "overlay"]


class Label(QLabel):
    """A styled label component with variant support and optional color override.

    Variants:
    - default: Standard gray text (11px)
    - title: Bold, larger text for headings (14px)
    - section: Bold, muted text for section headers (11px)
    - value: Monospace text for displaying values (11px)
    - muted: Lighter gray for secondary text (10px)
    - overlay: Green on transparent background for HUD overlays

    The color parameter can override the variant's default color using any
    color from the Colors class (e.g., Colors.SUCCESS, Colors.ERROR).

    Usage:
        Label("Status")  # default
        Label("Camera Settings", variant="title")
        Label("123.45", variant="value")
        Label("Running", color=Colors.SUCCESS)  # Custom color
        Label("Error!", variant="value", color=Colors.ERROR)  # Variant + color override
    """

    # Base styles per variant (without color - color applied separately)
    STYLES: ClassVar[dict[LabelVariant, tuple[str, str]]] = {
        # (base_style, default_color)
        "default": ("font-size: 11px;", Colors.TEXT_MUTED),
        "title": ("font-size: 14px; font-weight: bold;", Colors.TEXT),
        "section": ("font-size: 11px; font-weight: bold;", Colors.TEXT_MUTED),
        "value": ("font-size: 11px; font-family: monospace;", Colors.TEXT),
        "muted": ("font-size: 10px;", Colors.TEXT_MUTED),
        "overlay": (
            f"font-size: 11px; font-weight: bold; "
            f"background-color: rgba(0, 0, 0, 150); padding: {Spacing.XS}px {Spacing.SM}px; "
            f"border-radius: {BorderRadius.SM}px;",
            Colors.SUCCESS,
        ),
    }

    def __init__(
        self,
        text: str = "",
        variant: LabelVariant = "default",
        color: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent=parent)
        self._variant: LabelVariant = variant
        self._color: str | None = color
        self._apply_style()

    @property
    def variant(self) -> LabelVariant:
        return self._variant

    @variant.setter
    def variant(self, variant: LabelVariant) -> None:
        self._variant = variant
        self._apply_style()

    @property
    def color(self) -> str | None:
        return self._color

    @color.setter
    def color(self, color: str | None) -> None:
        self._color = color
        self._apply_style()

    def _apply_style(self) -> None:
        """Apply style based on current variant and color."""
        base_style, default_color = self.STYLES[self._variant]
        actual_color = self._color if self._color is not None else default_color
        self.setStyleSheet(f"QLabel {{ {base_style} color: {actual_color}; }}")
