"""
Identity matching service for detecting duplicate Person nodes
"""
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import structlog
from difflib import SequenceMatcher
import re

logger = structlog.get_logger()


class IdentityMatchingService:
    """Service for matching and merging Person identities"""
    
    def __init__(self, graph_writer):
        self.graph_writer = graph_writer
    
    def calculate_name_similarity(self, name1: str, name2: str) -> float:
        """
        Calculate similarity between two names using multiple methods
        
        Args:
            name1: First name
            name2: Second name
            
        Returns:
            Similarity score between 0.0 and 1.0
        """
        if not name1 or not name2:
            return 0.0
        
        # Normalize names
        name1_norm = self._normalize_name(name1)
        name2_norm = self._normalize_name(name2)
        
        if name1_norm == name2_norm:
            return 1.0
        
        # Use SequenceMatcher for similarity
        similarity = SequenceMatcher(None, name1_norm, name2_norm).ratio()
        
        # Check for partial matches (one name contains the other)
        if name1_norm in name2_norm or name2_norm in name1_norm:
            similarity = max(similarity, 0.8)
        
        return similarity
    
    def _normalize_name(self, name: str) -> str:
        """Normalize name for comparison"""
        if not name:
            return ""
        # Convert to string and handle None
        name = str(name) if name is not None else ""
        if not name:
            return ""
        # Remove extra spaces, convert to lowercase, remove accents
        name = re.sub(r'\s+', ' ', name.strip().lower())
        # Simple accent removal (can be enhanced)
        replacements = {
            'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
            'ñ': 'n', 'ü': 'u'
        }
        for old, new in replacements.items():
            name = name.replace(old, new)
        return name
    
    def match_persons_by_attributes(
        self,
        person1_data: Dict[str, Any],
        person2_data: Dict[str, Any]
    ) -> Tuple[bool, float, List[str]]:
        """
        Match two persons based on multiple attributes
        
        Args:
            person1_data: First person's data (name, curp, birth_date, etc.)
            person2_data: Second person's data
            
        Returns:
            Tuple of (is_match: bool, confidence: float, reasons: List[str])
        """
        reasons = []
        confidence_scores = []
        
        # 1. CURP match (exact match = very high confidence)
        curp1 = person1_data.get("curp") or ""
        curp2 = person2_data.get("curp") or ""
        if curp1 and curp2:
            curp1 = str(curp1).strip().upper()
            curp2 = str(curp2).strip().upper()
            if curp1 and curp2 and curp1 == curp2:
                reasons.append("CURP exact match")
                confidence_scores.append(0.98)
        
        # 2. Name similarity (fuzzy matching)
        name1 = self._build_full_name(person1_data)
        name2 = self._build_full_name(person2_data)
        name_sim = self.calculate_name_similarity(name1, name2)
        if name_sim > 0.85:
            reasons.append(f"Name similarity: {name_sim:.2f}")
            confidence_scores.append(name_sim * 0.7)  # Name alone is less reliable
        
        # 3. Birth date match (exact match = high confidence)
        birth1 = person1_data.get("fecha_nacimiento") or person1_data.get("birth_date")
        birth2 = person2_data.get("fecha_nacimiento") or person2_data.get("birth_date")
        if birth1 and birth2:
            # Normalize dates
            date1 = self._normalize_date(birth1)
            date2 = self._normalize_date(birth2)
            if date1 and date2 and date1 == date2:
                reasons.append("Birth date match")
                confidence_scores.append(0.85)
        
        # 4. Alias match (check if one person's alias matches another's name)
        alias1 = person1_data.get("alias")
        alias2 = person2_data.get("alias")
        if alias1:
            alias1 = str(alias1).strip()
            if alias1 and name2:
                alias_name_sim = self.calculate_name_similarity(alias1, name2)
                if alias_name_sim > 0.85:
                    reasons.append(f"Alias '{alias1}' matches name")
                    confidence_scores.append(alias_name_sim * 0.6)
        if alias2:
            alias2 = str(alias2).strip()
            if alias2 and name1:
                alias_name_sim = self.calculate_name_similarity(alias2, name1)
                if alias_name_sim > 0.85:
                    reasons.append(f"Alias '{alias2}' matches name")
                    confidence_scores.append(alias_name_sim * 0.6)
        
        # 5. Address match (same address = moderate confidence)
        address1 = self._build_address(person1_data)
        address2 = self._build_address(person2_data)
        if address1 and address2:
            address_sim = self._compare_addresses(address1, address2)
            if address_sim > 0.8:
                reasons.append(f"Address similarity: {address_sim:.2f}")
                confidence_scores.append(address_sim * 0.5)  # Address alone is less reliable
        
        # Calculate final confidence
        if not confidence_scores:
            return (False, 0.0, [])
        
        # Use highest confidence score, but require at least 0.7 for match
        max_confidence = max(confidence_scores)
        
        # If we have multiple strong signals, boost confidence
        strong_signals = [s for s in confidence_scores if s > 0.8]
        if len(strong_signals) >= 2:
            max_confidence = min(0.98, max_confidence + 0.1)
        
        is_match = max_confidence >= 0.7
        
        return (is_match, max_confidence, reasons)
    
    def _build_full_name(self, data: Dict[str, Any]) -> str:
        """Build full name from person data"""
        parts = []
        nombre = data.get("nombre") or data.get("name")
        if nombre:
            parts.append(str(nombre).strip())
        apellido_uno = data.get("apellido_uno") or data.get("apellidoUno")
        if apellido_uno:
            parts.append(str(apellido_uno).strip())
        apellido_dos = data.get("apellido_dos") or data.get("apellidoDos")
        if apellido_dos:
            parts.append(str(apellido_dos).strip())
        return " ".join(parts).strip() if parts else ""
    
    def _normalize_date(self, date_value: Any) -> Optional[str]:
        """Normalize date to YYYY-MM-DD format"""
        if not date_value:
            return None
        
        if isinstance(date_value, datetime):
            return date_value.strftime("%Y-%m-%d")
        
        if isinstance(date_value, str):
            # Try to parse common date formats
            try:
                # Try ISO format first
                dt = datetime.fromisoformat(date_value.replace('Z', '+00:00'))
                return dt.strftime("%Y-%m-%d")
            except:
                # Try other formats
                for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"]:
                    try:
                        dt = datetime.strptime(date_value.split()[0], fmt)
                        return dt.strftime("%Y-%m-%d")
                    except:
                        continue
        
        return None
    
    def _build_address(self, data: Dict[str, Any]) -> str:
        """Build address string from person data"""
        parts = []
        calle = data.get("calle")
        if calle:
            parts.append(str(calle).strip())
        num_ext = data.get("num_ext") or data.get("numExt")
        if num_ext:
            parts.append(str(num_ext).strip())
        colonia = data.get("colonia")
        if colonia:
            parts.append(str(colonia).strip())
        municipio = data.get("municipio")
        if municipio:
            parts.append(str(municipio).strip())
        entidad = data.get("entidad")
        if entidad:
            parts.append(str(entidad).strip())
        return ", ".join(parts).strip() if parts else ""
    
    def _compare_addresses(self, addr1: str, addr2: str) -> float:
        """Compare two addresses for similarity"""
        if not addr1 or not addr2:
            return 0.0
        
        addr1_norm = self._normalize_name(addr1)
        addr2_norm = self._normalize_name(addr2)
        
        if addr1_norm == addr2_norm:
            return 1.0
        
        # Check if one address contains the other (partial match)
        if addr1_norm in addr2_norm or addr2_norm in addr1_norm:
            return 0.85
        
        # Use SequenceMatcher for similarity
        return SequenceMatcher(None, addr1_norm, addr2_norm).ratio()
    
    def find_potential_duplicates(
        self,
        person_id: str,
        threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Find potential duplicate Person nodes for a given person
        
        Args:
            person_id: Person ID to check
            threshold: Minimum confidence threshold (default: 0.7)
            
        Returns:
            List of potential matches with confidence scores
        """
        # Get person details
        person_details = self.graph_writer.get_person_details(person_id)
        if not person_details:
            return []
        
        # Get all persons from graph (or use a more efficient query)
        # For now, we'll search by name similarity
        person_name = person_details.get("person_name", "")
        if not person_name:
            return []
        
        # Search for similar names
        similar_persons = self.graph_writer.search_person_by_name(person_name)
        
        matches = []
        person1_data = {
            "name": person_name,
            "person_id": person_id
        }
        
        for similar_person in similar_persons:
            if similar_person["person_id"] == person_id:
                continue  # Skip self
            
            person2_data = {
                "name": similar_person["person_name"],
                "person_id": similar_person["person_id"]
            }
            
            # Get full details for both persons
            person2_details = self.graph_writer.get_person_details(similar_person["person_id"])
            if person2_details:
                person2_data.update(person2_details)
            
            # Match persons
            is_match, confidence, reasons = self.match_persons_by_attributes(
                person1_data,
                person2_data
            )
            
            if is_match and confidence >= threshold:
                matches.append({
                    "person_id": similar_person["person_id"],
                    "person_name": similar_person["person_name"],
                    "confidence": confidence,
                    "reasons": reasons,
                    "folio_ids": person2_details.get("folio_ids", []) if person2_details else []
                })
        
        # Sort by confidence (highest first)
        matches.sort(key=lambda x: x["confidence"], reverse=True)
        
        return matches
