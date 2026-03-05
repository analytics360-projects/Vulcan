"""
Entity extraction service using Ollama (Gemma 3)
"""
import httpx
from typing import List, Dict, Any, Optional
from config import settings
import structlog
import json

logger = structlog.get_logger()


class EntityExtractionService:
    """Service for extracting entities from text/images using Ollama"""

    def __init__(self):
        self.api_url = settings.ollama_api_url
        self.model = settings.ollama_model
    
    def extract_entities_from_text(self, text: str, context: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Extract entities from text using Ollama

        Args:
            text: Text to analyze
            context: Optional context (e.g., "photo description", "folio narrative")

        Returns:
            List of extracted entities with type, value, confidence, context
        """
        try:
            # Build prompt for entity extraction
            system_message = "You are an expert at extracting named entities from investigative text. Extract entities and return them as JSON."
            user_prompt = self._build_ner_prompt(text, context)

            # Combine system and user messages for Ollama
            full_prompt = f"{system_message}\n\n{user_prompt}"

            # Call Ollama API
            response = httpx.post(
                f"{self.api_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": full_prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 1000
                    }
                },
                timeout=120.0  # Increased to 120 seconds for bulk operations
            )
            response.raise_for_status()

            result = response.json()
            content = result["response"]

            # Parse JSON response
            entities = self._parse_entity_response(content, text)

            logger.info("Entity extraction completed", entities_found=len(entities))
            return entities

        except Exception as e:
            logger.error("Entity extraction failed", error=str(e))
            return []
    
    def _build_ner_prompt(self, text: str, context: Optional[str] = None) -> str:
        """Build prompt for NER task"""
        context_part = f"\nContext: {context}" if context else ""
        
        prompt = f"""Extract all named entities from the following text. Focus on:
- Person names and aliases
- Vehicle license plates
- Phone numbers
- Addresses
- Weapons
- Organizations

Text to analyze:{context_part}
"{text}"

Return a JSON array of entities in this format:
[
  {{"entity_type": "Person", "value": "John Doe", "confidence": 0.95, "context": "mentioned in description"}},
  {{"entity_type": "Vehicle", "value": "ABC-123", "confidence": 0.90, "context": "license plate"}}
]

Only return valid JSON, no additional text."""
        
        return prompt
    
    def _parse_entity_response(self, content: str, original_text: str) -> List[Dict[str, Any]]:
        """Parse Ollama response into entity list"""
        try:
            # Try to extract JSON from response
            content = content.strip()
            
            # Remove markdown code blocks if present
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            # Parse JSON
            entities = json.loads(content)
            
            # Validate and normalize
            if not isinstance(entities, list):
                return []
            
            normalized = []
            for entity in entities:
                if isinstance(entity, dict) and "entity_type" in entity and "value" in entity:
                    normalized.append({
                        "entity_type": entity.get("entity_type", "Unknown"),
                        "value": entity.get("value", ""),
                        "confidence": float(entity.get("confidence", 0.5)),
                        "context": entity.get("context", original_text[:100])
                    })
            
            return normalized
            
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse entity JSON", error=str(e), content=content[:200])
            return []
        except Exception as e:
            logger.error("Failed to parse entity response", error=str(e))
            return []
    
    def extract_entities_from_metadata(self, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract entities from metadata dictionary
        
        Args:
            metadata: Dictionary with text fields
            
        Returns:
            List of extracted entities
        """
        all_entities = []
        
        # Combine all text fields
        text_parts = []
        for key, value in metadata.items():
            if isinstance(value, str) and value.strip():
                text_parts.append(f"{key}: {value}")
        
        if text_parts:
            combined_text = "\n".join(text_parts)
            entities = self.extract_entities_from_text(combined_text, context="metadata")
            all_entities.extend(entities)
        
        return all_entities
