# Instrucciones para asistentes de programación

## Objetivo

Mini Yolotzin es una demostración académica de predicción de afluencia diaria del Metro CDMX. Debe ser clara, verificable y honesta sobre el alcance del modelo.

## Reglas del producto

- Conservar el nombre **Mini Yolotzin** y la interfaz en español.
- Mantener la aplicación como sitio estático compatible con GitHub Pages.
- No introducir dependencias de servidor para cambios visuales o de contenido.
- Mantener accesibilidad básica, diseño adaptable a celular y navegación por teclado.
- Los perfiles y Mis viajes se almacenan únicamente con `localStorage`; no son cuentas reales. El texto que escribe la persona se muestra siempre escapado.
- Nunca agregar contraseñas, tokens, claves API ni datos personales al repositorio.

## Reglas metodológicas

- La unidad de predicción es afluencia **diaria**, no por hora ni por minuto.
- No presentar la predicción como ocupación del tren, saturación de andenes o información en tiempo real.
- Se modela cada registro estación-línea del recurso oficial (195 en la versión actual). Indios Verdes, La Raza, Hidalgo, Centro Médico y Universidad (Línea 3) son las estaciones destacadas.
- Los días con afluencia 0 son cierres, no demanda baja: no se usan para entrenar ni validar.
- Las variables del modelo solo pueden ser información conocida con anticipación para todo el horizonte (calendario, festivos). El clima o los eventos requieren una decisión aparte y su propia validación.
- Cualquier cambio de método se mide contra la versión anterior con la misma partición cronológica y se reporta en la Pull Request.
- Cada fila de `eventos.csv` necesita una fuente pública que confirme la fecha (o una regla de fecha fija). No inventar fechas de eventos ni ajustar con menos de 2 ediciones medidas.
- El clima se midió (`scripts/analizar_clima.py`) y no mejora la estimación diaria: no agregarlo al modelo ni mostrar efectos del clima por estación mientras el análisis no lo respalde. Las cifras del clima en la interfaz salen de `weather-summary.js`, no se escriben a mano.
- Mostrar el aviso de confiabilidad baja cuando el error típico supere el 30% de la afluencia habitual.
- Mantener visible la fuente oficial, el periodo de datos, el error del modelo y la comparación con la línea base.
- No inventar nuevas cifras. Si cambia `model-data.js`, explicar cómo se generaron y validar cronológicamente el modelo.

## Archivos y publicación

- `index.html`, `model-data.js`, `metro-catalog.js`, `weather-summary.js`, `manifest.webmanifest`, `sw.js` e `icons/` deben permanecer en la raíz para GitHub Pages.
- Si cambia la lista de archivos que necesita la app, actualizar `FILES` y el nombre `CACHE` en `sw.js`. Todas las rutas son relativas (`./`) porque el sitio se publica en `/mini-yolotzin/`.
- `metro-catalog.js` solo contiene ubicación de estaciones; no debe usarse para mostrar afluencia de estaciones sin modelo. Los nombres del catálogo y del CSV se relacionan con una clave normalizada en `index.html` (`stationKey`).
- `scripts/build_model_data.py` genera `model-data.js` a partir de `afluencia_simple.csv`.
- El CSV original no se versiona; está incluido en `.gitignore`.
- Un cambio visual ordinario no debe modificar las predicciones.

## Comprobaciones mínimas

Antes de entregar un cambio, corre `pytest` (ver README); las pruebas automatizan la mayoría de estos puntos y deben pasar en la Pull Request. Si agregas una función, agrega su prueba en `tests/`. Además:

1. Verificar que la página abra sin errores de JavaScript.
2. Probar las pestañas Explorar, Metodología y Datos, con clic y con las flechas del teclado.
3. Confirmar que la selección de estación y fecha (lista, barra, fecha exacta y ±1 día) actualiza la estimación y el mapa.
4. Confirmar que el mapa permite reproducir, pausar, seleccionar estaciones (incluida la lista de demanda relativa) y hacer zoom.
5. Confirmar que la búsqueda y el filtro por línea encuentran estaciones, que en las correspondencias se puede cambiar de línea y que todas las estaciones del catálogo tienen su registro del modelo.
6. Probar la vista de 7 días (cambia la fecha al hacer clic) y, servida por http, que la app abra sin conexión.
7. Probar la creación y edición del perfil local, y Mis viajes: guardar una estación, crear y eliminar un viaje, y que persistan al recargar.
8. Revisar la presentación en pantalla pequeña.
9. Resumir los archivos cambiados y cualquier limitación de la verificación.

