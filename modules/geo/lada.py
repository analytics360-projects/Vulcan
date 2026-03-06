"""Lookup table: Mexican LADA area codes → state, city, coordinates."""

LADA_TABLE: list[dict] = [
    {"lada": "55", "estado": "Ciudad de México", "ciudad": "CDMX", "lat": 19.4326, "lng": -99.1332},
    {"lada": "33", "estado": "Jalisco", "ciudad": "Guadalajara", "lat": 20.6597, "lng": -103.3496},
    {"lada": "81", "estado": "Nuevo León", "ciudad": "Monterrey", "lat": 25.6866, "lng": -100.3161},
    {"lada": "222", "estado": "Puebla", "ciudad": "Puebla", "lat": 19.0414, "lng": -98.2063},
    {"lada": "614", "estado": "Chihuahua", "ciudad": "Chihuahua", "lat": 28.6353, "lng": -106.0889},
    {"lada": "656", "estado": "Chihuahua", "ciudad": "Ciudad Juárez", "lat": 31.6904, "lng": -106.4245},
    {"lada": "442", "estado": "Querétaro", "ciudad": "Querétaro", "lat": 20.5888, "lng": -100.3899},
    {"lada": "449", "estado": "Aguascalientes", "ciudad": "Aguascalientes", "lat": 21.8853, "lng": -102.2916},
    {"lada": "999", "estado": "Yucatán", "ciudad": "Mérida", "lat": 20.9674, "lng": -89.5926},
    {"lada": "998", "estado": "Quintana Roo", "ciudad": "Cancún", "lat": 21.1619, "lng": -86.8515},
    {"lada": "993", "estado": "Tabasco", "ciudad": "Villahermosa", "lat": 17.9892, "lng": -92.9475},
    {"lada": "961", "estado": "Chiapas", "ciudad": "Tuxtla Gutiérrez", "lat": 16.7528, "lng": -93.1152},
    {"lada": "951", "estado": "Oaxaca", "ciudad": "Oaxaca", "lat": 17.0732, "lng": -96.7266},
    {"lada": "228", "estado": "Veracruz", "ciudad": "Veracruz", "lat": 19.1738, "lng": -96.1342},
    {"lada": "229", "estado": "Veracruz", "ciudad": "Boca del Río", "lat": 19.1059, "lng": -96.1073},
    {"lada": "271", "estado": "Veracruz", "ciudad": "Córdoba", "lat": 18.8846, "lng": -96.9342},
    {"lada": "844", "estado": "Coahuila", "ciudad": "Saltillo", "lat": 25.4232, "lng": -100.9924},
    {"lada": "871", "estado": "Coahuila", "ciudad": "Torreón", "lat": 25.5428, "lng": -103.4068},
    {"lada": "667", "estado": "Sinaloa", "ciudad": "Culiacán", "lat": 24.8091, "lng": -107.3940},
    {"lada": "669", "estado": "Sinaloa", "ciudad": "Mazatlán", "lat": 23.2494, "lng": -106.4111},
    {"lada": "662", "estado": "Sonora", "ciudad": "Hermosillo", "lat": 29.0729, "lng": -110.9559},
    {"lada": "664", "estado": "Baja California", "ciudad": "Tijuana", "lat": 32.5149, "lng": -117.0382},
    {"lada": "686", "estado": "Baja California", "ciudad": "Mexicali", "lat": 32.6246, "lng": -115.4523},
    {"lada": "612", "estado": "Baja California Sur", "ciudad": "La Paz", "lat": 24.1426, "lng": -110.3128},
    {"lada": "624", "estado": "Baja California Sur", "ciudad": "Los Cabos", "lat": 22.8905, "lng": -109.9167},
    {"lada": "477", "estado": "Guanajuato", "ciudad": "León", "lat": 21.1250, "lng": -101.6860},
    {"lada": "461", "estado": "Guanajuato", "ciudad": "Celaya", "lat": 20.5233, "lng": -100.8157},
    {"lada": "443", "estado": "Michoacán", "ciudad": "Morelia", "lat": 19.7060, "lng": -101.1950},
    {"lada": "311", "estado": "Nayarit", "ciudad": "Tepic", "lat": 21.5041, "lng": -104.8946},
    {"lada": "744", "estado": "Guerrero", "ciudad": "Acapulco", "lat": 16.8531, "lng": -99.8237},
    {"lada": "777", "estado": "Morelos", "ciudad": "Cuernavaca", "lat": 18.9242, "lng": -99.2216},
    {"lada": "722", "estado": "Estado de México", "ciudad": "Toluca", "lat": 19.2826, "lng": -99.6557},
    {"lada": "246", "estado": "Tlaxcala", "ciudad": "Tlaxcala", "lat": 19.3182, "lng": -98.2375},
    {"lada": "492", "estado": "Zacatecas", "ciudad": "Zacatecas", "lat": 22.7709, "lng": -102.5832},
    {"lada": "444", "estado": "San Luis Potosí", "ciudad": "San Luis Potosí", "lat": 22.1565, "lng": -100.9855},
    {"lada": "618", "estado": "Durango", "ciudad": "Durango", "lat": 24.0277, "lng": -104.6532},
    {"lada": "312", "estado": "Colima", "ciudad": "Colima", "lat": 19.2433, "lng": -103.7250},
    {"lada": "833", "estado": "Tamaulipas", "ciudad": "Tampico", "lat": 22.2331, "lng": -97.8613},
    {"lada": "868", "estado": "Tamaulipas", "ciudad": "Nuevo Laredo", "lat": 27.4757, "lng": -99.5076},
    {"lada": "899", "estado": "Tamaulipas", "ciudad": "Reynosa", "lat": 26.0508, "lng": -98.2979},
    {"lada": "981", "estado": "Campeche", "ciudad": "Campeche", "lat": 19.8301, "lng": -90.5349},
]

_lada_by_code: dict[str, dict] = {entry["lada"]: entry for entry in LADA_TABLE}


def resolve_lada(phone: str) -> dict | None:
    """Given a phone number or LADA code, return geographic info."""
    clean = phone.strip().replace("+52", "").replace(" ", "").replace("-", "")
    # Try 3-digit LADA first, then 2-digit
    for length in (3, 2):
        code = clean[:length]
        if code in _lada_by_code:
            return _lada_by_code[code]
    return None


def get_all_ladas() -> list[dict]:
    return LADA_TABLE
