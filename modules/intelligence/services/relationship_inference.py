"""
Relationship inference service for detecting relationships between persons
"""
from typing import List, Dict, Any, Optional
import structlog

logger = structlog.get_logger()


class RelationshipInferenceService:
    """Service for inferring relationships between persons"""
    
    def __init__(self, graph_writer):
        self.graph_writer = graph_writer
    
    def _safe_get(self, data: Dict[str, Any], *keys) -> Optional[str]:
        """Safely get a value from dict, handling both camelCase and snake_case, and None values"""
        for key in keys:
            # Try exact key first
            if key in data:
                value = data[key]
                if value is None:
                    return None
                return str(value).strip() if value else None
            # Try camelCase version
            camel_key = ''.join(word.capitalize() if i > 0 else word for i, word in enumerate(key.split('_')))
            camel_key_lower = camel_key[0].lower() + camel_key[1:] if camel_key else ''
            if camel_key_lower in data:
                value = data[camel_key_lower]
                if value is None:
                    return None
                return str(value).strip() if value else None
        return None
    
    def _safe_strip(self, value: Any) -> str:
        """Safely strip a value, handling None"""
        if value is None:
            return ""
        return str(value).strip()
    
    def infer_relationships_for_person(
        self,
        person_id: str,
        person_data: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Infer relationships for a person based on various signals
        
        Args:
            person_id: Person ID
            person_data: Optional person data dictionary (from detenidos record)
            
        Returns:
            List of inferred relationships
        """
        relationships = []
        
        # 1. Co-occurrence detection (same folios)
        co_occurrences = self.graph_writer.get_co_occurring_persons(person_id)
        for co_occ in co_occurrences:
            if co_occ["co_occurrence_count"] >= 2:  # Appeared in 2+ folios together
                relationships.append({
                    "person_id": co_occ["person_id"],
                    "person_name": co_occ["person_name"],
                    "relationship_type": "CO_OCCURRED",
                    "confidence": min(0.7 + (co_occ["co_occurrence_count"] * 0.05), 0.95),
                    "metadata": {
                        "folio_ids": co_occ["folio_ids"],
                        "folio_numbers": co_occ["folio_numbers"],
                        "co_occurrence_count": co_occ["co_occurrence_count"]
                    }
                })
        
        # 2. Shared address detection
        if person_data:
            address_parts = self._extract_address_parts(person_data)
            if address_parts:
                same_address_persons = self.graph_writer.find_persons_by_address(address_parts)
                for addr_person in same_address_persons:
                    if addr_person["person_id"] != person_id:
                        relationships.append({
                            "person_id": addr_person["person_id"],
                            "person_name": addr_person["person_name"],
                            "relationship_type": "SHARED_ADDRESS",
                            "confidence": 0.75,
                            "metadata": {
                                "address": self._build_address_string(address_parts)
                            }
                        })
        
        # 3. Family relationship detection (same last names, parent names)
        if person_data:
            family_relationships = self._detect_family_relationships(person_id, person_data)
            relationships.extend(family_relationships)
        
        # 4. Same alias detection (could indicate association)
        if person_data:
            alias = person_data.get("alias") or person_data.get("apodo")
            if alias:
                alias_relationships = self._detect_alias_associations(person_id, alias)
                relationships.extend(alias_relationships)
        
        # Remove duplicates and sort by confidence
        seen = set()
        unique_relationships = []
        for rel in relationships:
            key = (rel["person_id"], rel["relationship_type"])
            if key not in seen:
                seen.add(key)
                unique_relationships.append(rel)
        
        unique_relationships.sort(key=lambda x: x["confidence"], reverse=True)
        
        return unique_relationships
    
    def _extract_address_parts(self, person_data: Dict[str, Any]) -> Dict[str, str]:
        """Extract address parts from person data"""
        address = {}
        
        calle = self._safe_get(person_data, "calle")
        if calle:
            address["calle"] = calle
        
        colonia = self._safe_get(person_data, "colonia")
        if colonia:
            address["colonia"] = colonia
        
        municipio = self._safe_get(person_data, "municipio")
        if municipio:
            address["municipio"] = municipio
        
        entidad = self._safe_get(person_data, "entidad")
        if entidad:
            address["entidad"] = entidad
        
        return address
    
    def _build_address_string(self, address_parts: Dict[str, str]) -> str:
        """Build address string from parts"""
        parts = []
        if address_parts.get("calle"):
            parts.append(address_parts["calle"])
        if address_parts.get("colonia"):
            parts.append(address_parts["colonia"])
        if address_parts.get("municipio"):
            parts.append(address_parts["municipio"])
        return ", ".join(parts)
    
    def _detect_family_relationships(
        self,
        person_id: str,
        person_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Detect family relationships based on last names and parent names"""
        relationships = []
        
        apellido_uno = self._safe_get(person_data, "apellido_uno", "apellidoUno")
        apellido_dos = self._safe_get(person_data, "apellido_dos", "apellidoDos")
        nombre_padre = self._safe_get(person_data, "nombre_padre", "nombrePadre")
        nombre_madre = self._safe_get(person_data, "nombre_madre", "nombreMadre")
        
        # 1. Detect siblings based on same last names
        if apellido_uno or apellido_dos:
            # Find persons with matching last names (potential siblings)
            matching_persons = self.graph_writer.find_persons_by_last_names(
                apellido_uno=apellido_uno,
                apellido_dos=apellido_dos
            )
            for match in matching_persons[:10]:  # Limit to top 10 matches
                if match["person_id"] != person_id:
                    # Check if they share at least one last name (more accurate check)
                    match_apellido_uno = match.get("apellido_uno", "").upper() if match.get("apellido_uno") else ""
                    match_apellido_dos = match.get("apellido_dos", "").upper() if match.get("apellido_dos") else ""
                    match_name = match["person_name"].upper()
                    
                    shares_last_name = False
                    shared_names = []
                    
                    # Check stored last names first (more accurate)
                    if apellido_uno and match_apellido_uno and apellido_uno.upper() == match_apellido_uno:
                        shares_last_name = True
                        shared_names.append(apellido_uno)
                    if apellido_dos and match_apellido_dos and apellido_dos.upper() == match_apellido_dos:
                        shares_last_name = True
                        shared_names.append(apellido_dos)
                    
                    # Fallback: check if last name appears in full name
                    if not shares_last_name:
                        if apellido_uno and apellido_uno.upper() in match_name:
                            shares_last_name = True
                            shared_names.append(apellido_uno)
                        if apellido_dos and apellido_dos.upper() in match_name:
                            shares_last_name = True
                            shared_names.append(apellido_dos)
                    
                    if shares_last_name:
                        # Create bidirectional SIBLING_OF relationship
                        self.graph_writer.create_family_relationship(
                            person1_id=person_id,
                            person2_id=match["person_id"],
                            relationship_type="SIBLING_OF",
                            metadata={
                                "shared_last_names": shared_names,
                                "source": "detenido_record"
                            }
                        )
                        
                        relationships.append({
                            "person_id": match["person_id"],
                            "person_name": match["person_name"],
                            "relationship_type": "SIBLING_OF",
                            "confidence": 0.75 if len(shared_names) >= 2 else 0.7,  # Two shared names = higher confidence
                            "metadata": {
                                "reason": f"Shared last name(s): {', '.join(shared_names)}"
                            }
                        })
        
        # 2. Detect parent relationships
        if nombre_padre:
            # Find or create Person node for father
            padre_person_id = self.graph_writer.create_or_get_person(
                nombre_padre,
                attributes={"source": "detenido_family"}
            )
            
            # Create explicit PARENT_OF relationship (father -> child)
            self.graph_writer.create_family_relationship(
                person1_id=padre_person_id,
                person2_id=person_id,
                relationship_type="PARENT_OF",
                metadata={"parent_type": "father", "source": "detenido_record"}
            )
            
            # Also create CHILD_OF relationship (child -> father)
            self.graph_writer.create_family_relationship(
                person1_id=person_id,
                person2_id=padre_person_id,
                relationship_type="CHILD_OF",
                metadata={"parent_type": "father", "source": "detenido_record"}
            )
            
            relationships.append({
                "person_id": padre_person_id,
                "person_name": nombre_padre,
                "relationship_type": "CHILD_OF",
                "confidence": 0.95,  # Explicit parent name = very high confidence
                "metadata": {
                    "reason": f"Father: {nombre_padre}",
                    "parent_type": "father"
                }
            })
        
        if nombre_madre:
            # Find or create Person node for mother
            madre_person_id = self.graph_writer.create_or_get_person(
                nombre_madre,
                attributes={"source": "detenido_family"}
            )
            
            # Create explicit PARENT_OF relationship (mother -> child)
            self.graph_writer.create_family_relationship(
                person1_id=madre_person_id,
                person2_id=person_id,
                relationship_type="PARENT_OF",
                metadata={"parent_type": "mother", "source": "detenido_record"}
            )
            
            # Also create CHILD_OF relationship (child -> mother)
            self.graph_writer.create_family_relationship(
                person1_id=person_id,
                person2_id=madre_person_id,
                relationship_type="CHILD_OF",
                metadata={"parent_type": "mother", "source": "detenido_record"}
            )
            
            relationships.append({
                "person_id": madre_person_id,
                "person_name": nombre_madre,
                "relationship_type": "CHILD_OF",
                "confidence": 0.95,  # Explicit parent name = very high confidence
                "metadata": {
                    "reason": f"Mother: {nombre_madre}",
                    "parent_type": "mother"
                }
            })
        
        return relationships
    
    def _detect_alias_associations(
        self,
        person_id: str,
        alias: str
    ) -> List[Dict[str, Any]]:
        """Detect associations based on alias matches"""
        relationships = []
        
        # Search for persons with similar aliases or names matching the alias
        matching_persons = self.graph_writer.search_person_by_name(alias)
        
        for match in matching_persons[:5]:  # Limit to top 5 matches
            if match["person_id"] != person_id:
                relationships.append({
                    "person_id": match["person_id"],
                    "person_name": match["person_name"],
                    "relationship_type": "POTENTIAL_ASSOCIATION",
                    "confidence": 0.6,
                    "metadata": {
                        "reason": f"Alias match: {alias}"
                    }
                })
        
        return relationships
    
    def process_detenido_record(
        self,
        detenido_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process a detenido record and infer all relationships
        
        Args:
            detenido_data: Dictionary with detenido fields (from Balder database)
            
        Returns:
            Dictionary with person_id, merge_proposals, and relationships
        """
        # Build person name - handle both camelCase and snake_case
        nombre = self._safe_get(detenido_data, "nombre") or ""
        apellido_uno = self._safe_get(detenido_data, "apellido_uno", "apellidoUno") or ""
        apellido_dos = self._safe_get(detenido_data, "apellido_dos", "apellidoDos") or ""
        
        full_name = " ".join([p for p in [nombre, apellido_uno, apellido_dos] if p]).strip()
        
        if not full_name:
            return {"error": "No name provided"}
        
        # Prepare attributes - handle None values and camelCase
        curp = self._safe_get(detenido_data, "curp")
        fecha_nacimiento = self._safe_get(detenido_data, "fecha_nacimiento", "fechaNacimiento")
        alias = self._safe_get(detenido_data, "alias")
        sexo = self._safe_get(detenido_data, "sexo")
        nacionalidad = self._safe_get(detenido_data, "nacionalidad")
        nombre_padre = self._safe_get(detenido_data, "nombre_padre", "nombrePadre")
        nombre_madre = self._safe_get(detenido_data, "nombre_madre", "nombreMadre")
        apellido_uno = self._safe_get(detenido_data, "apellido_uno", "apellidoUno")
        apellido_dos = self._safe_get(detenido_data, "apellido_dos", "apellidoDos")
        
        attributes = {
            "source": "detenido"  # Mark as from detenido record
        }
        if curp:
            attributes["curp"] = curp
        if fecha_nacimiento and fecha_nacimiento not in ["", "0001-01-01T00:00:00", "0001-01-01"]:
            attributes["birth_date"] = fecha_nacimiento
        if alias:
            attributes["alias"] = alias
        if sexo:
            attributes["sex"] = sexo
        if nacionalidad:
            attributes["nationality"] = nacionalidad
        # Store last names for sibling detection
        if apellido_uno:
            attributes["apellido_uno"] = apellido_uno
        if apellido_dos:
            attributes["apellido_dos"] = apellido_dos
        
        # Create or get person
        person_id = self.graph_writer.create_or_get_person(
            person_name=full_name,
            attributes=attributes
        )
        
        # Link to folio if provided - handle both camelCase and snake_case
        folio_id = (
            self._safe_get(detenido_data, "carpeta_investigacion", "carpetaInvestigacion") or
            self._safe_get(detenido_data, "folio_id", "folioId") or
            self._safe_get(detenido_data, "id_evento", "idEvento")  # Fallback to idEvento
        )
        if folio_id:
            self.graph_writer.create_or_get_folio(str(folio_id))
            self.graph_writer.link_person_to_folio(person_id, str(folio_id))
            
            # Add delito (crime) to folio if provided
            motivo_detencion = self._safe_get(detenido_data, "motivo_detencion", "motivoDetencion")
            if motivo_detencion:
                self.graph_writer.add_folio_delito(
                    folio_id=str(folio_id),
                    delito=motivo_detencion,
                    metadata={
                        "source": "detenido",
                        "detenido_id": detenido_data.get("id")
                    }
                )
        
        # Find potential duplicates (identity matching)
        from modules.intelligence.services.identity_matching import IdentityMatchingService
        identity_service = IdentityMatchingService(self.graph_writer)
        
        person_data = {
            "nombre": nombre,
            "apellido_uno": apellido_uno,
            "apellido_dos": apellido_dos,
            "nombre_padre": nombre_padre,
            "nombre_madre": nombre_madre,
            **attributes
        }
        
        # Get person details for matching
        person_details = self.graph_writer.get_person_details(person_id)
        if person_details:
            person_data.update(person_details)
        
        potential_duplicates = identity_service.find_potential_duplicates(person_id)
        
        # Infer relationships
        relationships = self.infer_relationships_for_person(person_id, person_data)
        
        return {
            "person_id": person_id,
            "person_name": full_name,
            "potential_duplicates": potential_duplicates,
            "relationships": relationships,
            "folio_id": folio_id
        }
