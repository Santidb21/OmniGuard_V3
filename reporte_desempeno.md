# Reporte de Desempeno - OmniGuard V3

**Fecha:** 2026-05-26 11:53:36

## Resultado: EXITOSO

**Resumen:** El sistema supero la prueba de estres con 500 peticiones concurrentes (50 workers).

## Resultados

| Metrica | Valor |
|---|---|
| Tiempo total | 21.53s |
| Tiempo de respuesta promedio | 2118.1ms |
| Tiempo de respuesta minimo | 2045.5ms |
| Tiempo de respuesta maximo | 2274.2ms |
| Percentil 95 | 2207.7ms |
| Percentil 99 | 2248.0ms |
| Consumo CPU | 16.9% |
| Consumo RAM | 61.1% |
| Peticiones exitosas | 500/500 |
| Peticiones fallidas | 0/500 |

## Conclusion tecnica

El sistema se mantuvo estable y sin bloqueos en SQLite durante toda la prueba. La arquitectura con WAL mode, `busy_timeout` y reintentos con backoff exponencial `@retry_on_locked` demostro ser efectiva para manejar la concurrencia de 50 workers simultaneos sin degradacion critica. No se registraron errores de tipo `database is locked`, timeouts ni respuestas HTTP 500.
