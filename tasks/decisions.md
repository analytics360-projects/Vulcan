# Decisiones Arquitectonicas

## 2026-03-05: Google Person Search
- Se usa Selenium para buscar en Google y explorar resultados
- Screenshots se guardan en MinIO si esta disponible, si no en disco local (/app/captures/)
- HTML y recursos se guardan junto con los screenshots
- El modulo person_search orquesta todos los demas modulos para una busqueda unificada
