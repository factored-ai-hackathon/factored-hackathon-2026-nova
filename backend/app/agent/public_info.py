"""What the public assistant (outside the login) knows: NovaBank branches, opening hours and the
WhatsApp number where a visitor without an account asks to open one.

All of it is fictitious and team-written: the addresses are invented (one set per country of the
dataset) and the WhatsApp numbers are in reserved or obviously fake ranges. It is the assistant's
whole knowledge, so it can't say anything about customers or accounts: there is nothing else to
read (app/agent/public.py gives the model no tools).
"""

from dataclasses import dataclass

COUNTRIES = ("México", "Colombia", "Argentina")

# Branch hours by day group: (first day, last day, opens, closes). Days: 0 = Monday ... 6 = Sunday.
Hours = tuple[tuple[int, int, str, str], ...]

WEEKDAYS = {
    "es": ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"],
    "pt": [
        "segunda-feira",
        "terça-feira",
        "quarta-feira",
        "quinta-feira",
        "sexta-feira",
        "sábado",
        "domingo",
    ],
}
COUNTRY_NAMES_PT = {"México": "México", "Colombia": "Colômbia", "Argentina": "Argentina"}


@dataclass(frozen=True)
class Branch:
    name: str
    address: str
    city: str
    hours: Hours


@dataclass(frozen=True)
class CountryInfo:
    whatsapp: str  # fictitious
    branches: tuple[Branch, ...]


WEEK = ((0, 4, "09:00", "16:00"),)
WEEK_SAT = ((0, 4, "09:00", "17:00"), (5, 5, "09:00", "13:00"))
WEEK_LATE = ((0, 4, "08:30", "18:00"), (5, 5, "09:00", "14:00"))

PUBLIC_INFO: dict[str, CountryInfo] = {
    "México": CountryInfo(
        whatsapp="+52 55 5555 0142",
        branches=(
            Branch(
                "Sucursal Reforma Norte",
                "Calle Ficticia 123, Col. Centro",
                "Ciudad de México",
                WEEK_SAT,
            ),
            Branch("Sucursal Andares", "Av. Ejemplo 4567, Zapopan", "Guadalajara", WEEK),
            Branch("Sucursal San Pedro", "Calzada Inventada 890, San Pedro", "Monterrey", WEEK_SAT),
        ),
    ),
    "Colombia": CountryInfo(
        whatsapp="+57 300 000 0142",
        branches=(
            Branch("Sucursal Chapinero", "Carrera 99 # 12-34", "Bogotá", WEEK_LATE),
            Branch("Sucursal El Poblado", "Calle 77 # 45-67", "Medellín", WEEK_SAT),
            Branch("Sucursal Granada", "Avenida 5 Norte # 23-45", "Cali", WEEK),
        ),
    ),
    "Argentina": CountryInfo(
        whatsapp="+54 9 11 5555 0142",
        branches=(
            Branch("Sucursal Microcentro", "Calle Imaginaria 1234", "Buenos Aires", WEEK),
            Branch("Sucursal Nueva Córdoba", "Boulevard Inventado 567", "Córdoba", WEEK),
            Branch("Sucursal Pichincha", "Calle Supuesta 890", "Rosario", WEEK),
        ),
    ),
}

DIGITAL = {
    "es": "La banca en línea y el asistente virtual funcionan las 24 horas, todos los días.",
    "pt": "O banco online e o assistente virtual funcionam 24 horas por dia, todos os dias.",
}
CLOSED = {"es": "domingos y feriados: cerrado", "pt": "domingos e feriados: fechado"}


def format_hours(hours: Hours, lang: str) -> str:
    days = WEEKDAYS[lang]
    parts = []
    for first, last, opens, closes in hours:
        span = days[first] if first == last else f"{days[first]} a {days[last]}"
        parts.append(f"{span} {opens}-{closes}")
    return "; ".join(parts) + "; " + CLOSED[lang]


def knowledge(lang: str) -> str:
    """The branches and WhatsApp numbers as text for the system prompt."""
    lines = []
    for country, info in PUBLIC_INFO.items():
        shown = COUNTRY_NAMES_PT[country] if lang == "pt" else country
        lines.append(f"## {shown}")
        label = (
            "WhatsApp para abrir una cuenta" if lang == "es" else "WhatsApp para abrir uma conta"
        )
        lines.append(f"- {label}: {info.whatsapp}")
        for b in info.branches:
            lines.append(f"- {b.name}, {b.address}, {b.city}: {format_hours(b.hours, lang)}")
        lines.append("")
    lines.append(DIGITAL[lang])
    return "\n".join(lines)
