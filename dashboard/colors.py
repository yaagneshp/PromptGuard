# Palette from the project's dataviz standard: status colors for risk levels
# (fixed, never reused for anything else) and the validated 8-slot
# categorical order for platform identity. Both sets pass adjacent-pair
# colorblind-safety checks in light mode.

STATUS_COLORS = {
    "low": "#0ca30c",
    "medium": "#fab219",
    "high": "#ec835a",
    "critical": "#d03b3b",
}
RISK_LEVEL_ORDER = ["low", "medium", "high", "critical"]

CATEGORICAL_SLOTS = [
    "#2a78d6",  # blue
    "#eb6834",  # orange
    "#1baf7a",  # aqua
    "#eda100",  # yellow
    "#e87ba4",  # magenta
    "#008300",  # green
    "#4a3aa7",  # violet
    "#e34948",  # red
]
PLATFORM_ORDER = [
    "chatgpt",
    "claude",
    "gemini",
    "copilot",
    "perplexity",
    "deepseek",
    "grok",
    "mistral",
]
PLATFORM_COLORS = dict(zip(PLATFORM_ORDER, CATEGORICAL_SLOTS))

SEQUENTIAL_BLUE = "#2a78d6"
MUTED_INK = "#898781"
