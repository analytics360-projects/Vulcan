# Lecciones Aprendidas

## Arquitectura
- Vulcan usa degradacion graceful: si un modulo falla al init, los demas siguen funcionando
- Cada modulo sigue el patron: models.py, service.py, router.py
- Los servicios usan lazy imports dentro de los endpoints
- Rate limiter con token-bucket pattern en shared/rate_limiter.py
- WebDriver compartido en shared/webdriver.py con context manager
