"""Label Taxonomy Service — hardcoded forensic taxonomy + synonym resolution"""
from typing import Optional, List, Dict
from modules.labels.models import (
    LabelNode, TaxonomyResponse, SynonymMap, ResolvedLabel, ResolveResponse
)

# ── Taxonomy tree (parent > children) ──
_TAXONOMY: Dict[str, Dict] = {
    "Vehiculo": {
        "children": {
            "Auto": {
                "children": {"Sedan": {}, "SUV": {}, "Pickup": {}},
            },
            "Motocicleta": {},
            "Camion": {},
            "Autobus": {},
        },
    },
    "Persona": {
        "children": {
            "Hombre": {},
            "Mujer": {},
            "Nino": {},
        },
    },
    "Arma": {
        "children": {
            "Arma de fuego": {
                "children": {"Pistola": {}, "Rifle": {}, "Escopeta": {}},
            },
            "Arma blanca": {
                "children": {"Cuchillo": {}, "Navaja": {}, "Machete": {}},
            },
        },
    },
    "Animal": {
        "children": {
            "Perro": {},
            "Gato": {},
        },
    },
    "Objeto": {
        "children": {
            "Telefono": {},
            "Mochila": {},
            "Bolsa": {},
            "Caja": {},
        },
    },
    "Lugar": {
        "children": {
            "Interior": {},
            "Exterior": {},
            "Calle": {},
            "Edificio": {},
            "Terreno baldio": {},
        },
    },
    "Droga": {
        "children": {
            "Marihuana": {},
            "Cocaina": {},
            "Cristal": {},
            "Pastillas": {},
        },
    },
}

# ── Synonym map: English key -> (Spanish label, category) ──
# All keys are lowercased for lookup
_SYNONYMS: Dict[str, Dict] = {
    # Vehicles
    "car": {"spanish": "Auto", "category": "Vehiculo", "synonyms": ["Auto", "Carro", "Vehiculo", "Automovil"]},
    "auto": {"spanish": "Auto", "category": "Vehiculo", "synonyms": ["Car", "Carro", "Vehiculo", "Automovil"]},
    "carro": {"spanish": "Auto", "category": "Vehiculo", "synonyms": ["Car", "Auto", "Vehiculo", "Automovil"]},
    "automovil": {"spanish": "Auto", "category": "Vehiculo", "synonyms": ["Car", "Auto", "Carro", "Vehiculo"]},
    "vehicle": {"spanish": "Vehiculo", "category": "Vehiculo", "synonyms": ["Auto", "Carro", "Automovil"]},
    "vehiculo": {"spanish": "Vehiculo", "category": "Vehiculo", "synonyms": ["Auto", "Carro", "Automovil", "Vehicle"]},
    "sedan": {"spanish": "Sedan", "category": "Vehiculo", "synonyms": ["Auto", "Carro"]},
    "suv": {"spanish": "SUV", "category": "Vehiculo", "synonyms": ["Camioneta", "Auto"]},
    "pickup": {"spanish": "Pickup", "category": "Vehiculo", "synonyms": ["Camioneta"]},
    "pickup truck": {"spanish": "Pickup", "category": "Vehiculo", "synonyms": ["Camioneta"]},
    "truck": {"spanish": "Camion", "category": "Vehiculo", "synonyms": ["Trailer"]},
    "camion": {"spanish": "Camion", "category": "Vehiculo", "synonyms": ["Truck", "Trailer"]},
    "motorcycle": {"spanish": "Motocicleta", "category": "Vehiculo", "synonyms": ["Moto"]},
    "motocicleta": {"spanish": "Motocicleta", "category": "Vehiculo", "synonyms": ["Moto", "Motorcycle"]},
    "bus": {"spanish": "Autobus", "category": "Vehiculo", "synonyms": ["Camion de pasajeros"]},
    "autobus": {"spanish": "Autobus", "category": "Vehiculo", "synonyms": ["Bus", "Camion de pasajeros"]},

    # Persons
    "person": {"spanish": "Persona", "category": "Persona", "synonyms": ["Individuo", "Sujeto"]},
    "persona": {"spanish": "Persona", "category": "Persona", "synonyms": ["Person", "Individuo", "Sujeto"]},
    "individuo": {"spanish": "Persona", "category": "Persona", "synonyms": ["Person", "Persona", "Sujeto"]},
    "sujeto": {"spanish": "Persona", "category": "Persona", "synonyms": ["Person", "Persona", "Individuo"]},
    "man": {"spanish": "Hombre", "category": "Persona", "synonyms": ["Varon", "Masculino"]},
    "hombre": {"spanish": "Hombre", "category": "Persona", "synonyms": ["Man", "Varon", "Masculino"]},
    "woman": {"spanish": "Mujer", "category": "Persona", "synonyms": ["Femenino", "Dama"]},
    "mujer": {"spanish": "Mujer", "category": "Persona", "synonyms": ["Woman", "Femenino", "Dama"]},
    "boy": {"spanish": "Nino", "category": "Persona", "synonyms": ["Menor", "Infante"]},
    "girl": {"spanish": "Nino", "category": "Persona", "synonyms": ["Menor", "Infante"]},
    "child": {"spanish": "Nino", "category": "Persona", "synonyms": ["Menor", "Infante"]},
    "nino": {"spanish": "Nino", "category": "Persona", "synonyms": ["Child", "Menor", "Infante"]},

    # Weapons
    "gun": {"spanish": "Arma de fuego", "category": "Arma", "synonyms": ["Pistola", "Arma"]},
    "arma": {"spanish": "Arma", "category": "Arma", "synonyms": ["Gun", "Weapon"]},
    "arma de fuego": {"spanish": "Arma de fuego", "category": "Arma", "synonyms": ["Gun", "Pistola", "Firearm"]},
    "pistol": {"spanish": "Pistola", "category": "Arma", "synonyms": ["Gun", "Arma de fuego"]},
    "pistola": {"spanish": "Pistola", "category": "Arma", "synonyms": ["Pistol", "Gun", "Arma de fuego"]},
    "rifle": {"spanish": "Rifle", "category": "Arma", "synonyms": ["Fusil", "Arma larga"]},
    "shotgun": {"spanish": "Escopeta", "category": "Arma", "synonyms": ["Arma larga"]},
    "escopeta": {"spanish": "Escopeta", "category": "Arma", "synonyms": ["Shotgun"]},
    "knife": {"spanish": "Cuchillo", "category": "Arma", "synonyms": ["Navaja", "Arma blanca"]},
    "cuchillo": {"spanish": "Cuchillo", "category": "Arma", "synonyms": ["Knife", "Navaja", "Arma blanca"]},
    "navaja": {"spanish": "Navaja", "category": "Arma", "synonyms": ["Knife", "Cuchillo", "Arma blanca"]},
    "arma blanca": {"spanish": "Arma blanca", "category": "Arma", "synonyms": ["Knife", "Cuchillo", "Navaja"]},
    "machete": {"spanish": "Machete", "category": "Arma", "synonyms": ["Arma blanca"]},
    "weapon": {"spanish": "Arma", "category": "Arma", "synonyms": ["Gun", "Pistola"]},

    # Animals
    "dog": {"spanish": "Perro", "category": "Animal", "synonyms": ["Can", "Canino"]},
    "perro": {"spanish": "Perro", "category": "Animal", "synonyms": ["Dog", "Can", "Canino"]},
    "can": {"spanish": "Perro", "category": "Animal", "synonyms": ["Dog", "Perro", "Canino"]},
    "cat": {"spanish": "Gato", "category": "Animal", "synonyms": ["Felino", "Minino"]},
    "gato": {"spanish": "Gato", "category": "Animal", "synonyms": ["Cat", "Felino", "Minino"]},

    # Objects
    "phone": {"spanish": "Telefono", "category": "Objeto", "synonyms": ["Celular", "Movil"]},
    "telefono": {"spanish": "Telefono", "category": "Objeto", "synonyms": ["Phone", "Celular", "Movil"]},
    "celular": {"spanish": "Telefono", "category": "Objeto", "synonyms": ["Phone", "Telefono", "Movil"]},
    "movil": {"spanish": "Telefono", "category": "Objeto", "synonyms": ["Phone", "Telefono", "Celular"]},
    "cell phone": {"spanish": "Telefono", "category": "Objeto", "synonyms": ["Phone", "Celular", "Movil"]},
    "mobile phone": {"spanish": "Telefono", "category": "Objeto", "synonyms": ["Phone", "Celular", "Movil"]},
    "backpack": {"spanish": "Mochila", "category": "Objeto", "synonyms": ["Bolsa"]},
    "mochila": {"spanish": "Mochila", "category": "Objeto", "synonyms": ["Backpack", "Bolsa"]},
    "bag": {"spanish": "Bolsa", "category": "Objeto", "synonyms": ["Mochila", "Costal"]},
    "bolsa": {"spanish": "Bolsa", "category": "Objeto", "synonyms": ["Bag", "Mochila"]},
    "box": {"spanish": "Caja", "category": "Objeto", "synonyms": ["Paquete"]},
    "caja": {"spanish": "Caja", "category": "Objeto", "synonyms": ["Box", "Paquete"]},

    # Places
    "street": {"spanish": "Calle", "category": "Lugar", "synonyms": ["Via", "Avenida"]},
    "calle": {"spanish": "Calle", "category": "Lugar", "synonyms": ["Street", "Via", "Avenida"]},
    "building": {"spanish": "Edificio", "category": "Lugar", "synonyms": ["Construccion", "Inmueble"]},
    "edificio": {"spanish": "Edificio", "category": "Lugar", "synonyms": ["Building", "Construccion", "Inmueble"]},
    "indoor": {"spanish": "Interior", "category": "Lugar", "synonyms": ["Adentro"]},
    "interior": {"spanish": "Interior", "category": "Lugar", "synonyms": ["Indoor", "Adentro"]},
    "outdoor": {"spanish": "Exterior", "category": "Lugar", "synonyms": ["Afuera", "Al aire libre"]},
    "exterior": {"spanish": "Exterior", "category": "Lugar", "synonyms": ["Outdoor", "Afuera"]},

    # Drugs
    "marihuana": {"spanish": "Marihuana", "category": "Droga", "synonyms": ["Cannabis", "Mota", "Hierba"]},
    "marijuana": {"spanish": "Marihuana", "category": "Droga", "synonyms": ["Cannabis", "Mota", "Hierba"]},
    "cocaina": {"spanish": "Cocaina", "category": "Droga", "synonyms": ["Coca", "Polvo"]},
    "cocaine": {"spanish": "Cocaina", "category": "Droga", "synonyms": ["Coca", "Polvo"]},
    "cristal": {"spanish": "Cristal", "category": "Droga", "synonyms": ["Metanfetamina", "Ice"]},
    "pastillas": {"spanish": "Pastillas", "category": "Droga", "synonyms": ["Pildoras", "Tabletas"]},
}


def _flatten_taxonomy(
    tree: Dict, parent: Optional[str] = None, result: Optional[List[LabelNode]] = None
) -> List[LabelNode]:
    """Recursively flatten taxonomy dict into LabelNode list."""
    if result is None:
        result = []
    for name, data in tree.items():
        children_dict = data.get("children", {})
        children_names = list(children_dict.keys())
        # Find synonyms from synonym map
        synonyms = []
        entry = _SYNONYMS.get(name.lower())
        if entry:
            synonyms = entry.get("synonyms", [])
        result.append(LabelNode(
            name=name,
            parent=parent,
            children=children_names,
            synonyms=synonyms,
        ))
        if children_dict:
            _flatten_taxonomy(children_dict, parent=name, result=result)
    return result


def _build_hierarchy(label: str) -> List[str]:
    """Build hierarchy path from leaf to root."""
    flat = _flatten_taxonomy(_TAXONOMY)
    node_map = {n.name.lower(): n for n in flat}

    key = label.lower()
    # Try direct match first
    node = node_map.get(key)
    if not node:
        # Try synonym lookup
        syn_entry = _SYNONYMS.get(key)
        if syn_entry:
            spanish = syn_entry["spanish"]
            node = node_map.get(spanish.lower())

    if not node:
        return []

    path = [node.name]
    current = node
    while current.parent:
        path.insert(0, current.parent)
        current = node_map.get(current.parent.lower())
        if not current:
            break
    return path


class LabelTaxonomyService:
    """Provides label taxonomy and synonym resolution."""

    def get_taxonomy(self) -> TaxonomyResponse:
        nodes = _flatten_taxonomy(_TAXONOMY)
        return TaxonomyResponse(tree=nodes)

    def get_synonyms(self, label: str) -> SynonymMap:
        key = label.lower().strip()
        entry = _SYNONYMS.get(key)
        if entry:
            return SynonymMap(
                label=entry["spanish"],
                synonyms=entry["synonyms"],
                category=entry["category"],
            )
        # Not found — return the label as-is with empty synonyms
        return SynonymMap(label=label, synonyms=[], category="Desconocido")

    def resolve_label(self, label: str) -> ResolvedLabel:
        key = label.lower().strip()
        entry = _SYNONYMS.get(key)
        if entry:
            hierarchy = _build_hierarchy(entry["spanish"])
            return ResolvedLabel(
                original=label,
                spanish=entry["spanish"],
                category=entry["category"],
                hierarchy=hierarchy if hierarchy else [entry["category"], entry["spanish"]],
            )
        # Try direct taxonomy match
        hierarchy = _build_hierarchy(label)
        if hierarchy:
            return ResolvedLabel(
                original=label,
                spanish=hierarchy[-1],
                category=hierarchy[0],
                hierarchy=hierarchy,
            )
        return ResolvedLabel(
            original=label,
            spanish=label,
            category="Desconocido",
            hierarchy=[label],
        )

    def resolve_labels(self, labels: List[str]) -> ResolveResponse:
        resolved = [self.resolve_label(lbl) for lbl in labels]
        return ResolveResponse(resolved=resolved)


# Singleton
label_taxonomy_service = LabelTaxonomyService()
