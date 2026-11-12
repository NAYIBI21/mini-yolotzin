# Instrucciones para asistentes de programación

## Objetivo

Mini Yolotzin es una demostración académica de predicción de afluencia diaria del Metro CDMX. Debe ser clara, verificable y honesta sobre el alcance del modelo.

## Reglas del producto

- Conservar el nombre **Mini Yolotzin** y la interfaz en español.
- Mantener la aplicación como sitio estático compatible con GitHub Pages.
- No introducir dependencias de servidor para cambios visuales o de contenido.
- Mantener accesibilidad básica, diseño adaptable a celular y navegación por teclado.
- Los perfiles se almacenan únicamente con `localStorage`; no son cuentas reales.
- Nunca agregar contraseñas, tokens, claves API ni datos personales al repositorio.

## Reglas metodológicas

- La unidad de predicción es afluencia **diaria**, no por hora ni por minuto.
- No presentar la predicción como ocupación del tren, saturación de andenes o información en tiempo real.
- Se modela cada registro estación-línea del recurso oficial (195 en la versión actual). Indios Verdes, La Raza, Hidalgo, Centro Médico y Universidad (Línea 3) son las estaciones destacadas.
- Los días con afluencia 0 son cierres, no demanda baja: no se usan para entrenar ni validar.
- Mostrar el aviso de confiabilidad baja cuando el error típico supere el 30% de la afluencia habitual.
- Mantener visible la fuente oficial, el periodo de datos, el error del modelo y la comparación con la línea base.
- No inventar nuevas cifras. Si cambia `model-data.js`, explicar cómo se generaron y validar cronológicamente el modelo.

## Archivos y publicación

- `index.html`, `model-data.js` y `metro-catalog.js` deben permanecer en la raíz para GitHub Pages.
- `metro-catalog.js` solo contiene ubicación de estaciones; no debe usarse para mostrar afluencia de estaciones sin modelo. Los nombres del catálogo y del CSV se relacionan con una clave normalizada en `index.html` (`stationKey`).
- `scripts/build_model_data.py` genera `model-data.js` a partir de `afluencia_simple.csv`.
- El CSV original no se versiona; está incluido en `.gitignore`.
- Un cambio visual ordinario no debe modificar las predicciones.

## Comprobaciones mínimas

Antes de entregar un cambio:

1. Verificar que la página abra sin errores de JavaScript.
2. Probar las pestañas Explorar, Metodología y Datos, con clic y con las flechas del teclado.
3. Confirmar que la selección de estación y fecha (lista, barra, fecha exacta y ±1 día) actualiza la estimación y el mapa.
4. Confirmar que el mapa permite reproducir, pausar, seleccionar estaciones (incluida la lista de demanda relativa) y hacer zoom.
5. Confirmar que la búsqueda y el filtro por línea encuentran estaciones, que en las correspondencias se puede cambiar de línea y que todas las estaciones del catálogo tienen su registro del modelo.
6. Probar la creación y edición del perfil local.
7. Revisar la presentación en pantalla pequeña.
8. Resumir los archivos cambiados y cualquier limitación de la verificación.

