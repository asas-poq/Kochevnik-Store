DEFAULT_COLOR_HEX = "#D8CFC4"

COLOR_HEX_MAP: dict[str, str] = {
    "Голубой": "#A5C4D4",
    "Молочный": "#FAF8F5",
    "Капучино": "#C2A894",
    "Серый": "#9E9E9E",
    "Тёмно-коричневый": "#4A3525",
    "Темно-коричневый": "#4A3525",
    "Белый": "#FFFFFF",
    "Бежевый": "#E3D3C1",
    "Коричневый": "#6E4F3A",
    "Черный": "#2C2623",
    "Бордовый": "#6E2631",
    "Фиолетовый": "#6C5B7B",
    "Оранжевый": "#D97B43",
    "Малиновый": "#A8385D",
    "Синий": "#34568B",
}


def hex_for(color: str | None, fallback: str | None = None) -> str:
    return COLOR_HEX_MAP.get(color or "") or fallback or DEFAULT_COLOR_HEX
