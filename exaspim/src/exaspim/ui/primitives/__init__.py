"""Reusable UI primitives for the ExASPIM application.

Design System Structure:
    primitives/
    ├── buttons/         # Button, IconButton
    ├── containers/      # Card, AccordionCard
    ├── display/         # Label, Chip, Separator
    ├── input/           # SpinBox, Toggle, LockableSlider, etc.
    └── layout/          # HStack, VStack, Grid, Field, FormBuilder
"""

# Buttons
from exaspim.ui.primitives.buttons import Button, IconButton

# Containers
from exaspim.ui.primitives.containers import Card

# Display
from exaspim.ui.primitives.display import Chip, Label, Separator

# Inputs
from exaspim.ui.primitives.input import (
    DoubleSpinBox,
    LockableSlider,
    SpinBox,
    Toggle,
)

# Layout
from exaspim.ui.primitives.layout import (
    Field,
    FormBuilder,
    Grid,
    HStack,
    InfoRow,
    VStack,
)

__all__ = [
    # Buttons
    "Button",
    "IconButton",
    # Containers
    "Card",
    # Display
    "Chip",
    "Label",
    "Separator",
    # Input
    "DoubleSpinBox",
    "LockableSlider",
    "SpinBox",
    "Toggle",
    # Layout
    "Field",
    "FormBuilder",
    "Grid",
    "HStack",
    "InfoRow",
    "VStack",
]
