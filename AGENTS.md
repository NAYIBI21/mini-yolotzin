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
- Las únicas estaciones modeladas son Indios Verdes, La Raza, Hidalgo, Centro Médico y Universidad, todas de la Línea 3.
- Mantener visible la fuente oficial, el periodo de datos, el error del modelo y la comparación con la línea base.
- No inventar nuevas cifras. Si cambia `model-data.js`, explicar cómo se generaron y validar cronológicamente el modelo.

## Archivos y publicación

- `index.html` y `model-data.js` deben permanecer en la raíz para GitHub Pages.
- `scripts/build_model_data.py` genera `model-data.js` a partir de `afluencia_simple.csv`.
- El CSV original no se versiona; está incluido en `.gitignore`.
- Un cambio visual ordinario no debe modificar las predicciones.

## Comprobaciones mínimas

Antes de entregar un cambio:

1. Verificar que la página abra sin errores de JavaScript.
2. Probar las pestañas Predicción, Mapa, Metodología y Datos.
3. Confirmar que la selección de estación y fecha actualiza la estimación.
4. Confirmar que el mapa permite reproducir, pausar, seleccionar estaciones y hacer zoom.
5. Probar la creación y edición del perfil local.
6. Revisar la presentación en pantalla pequeña.
7. Resumir los archivos cambiados y cualquier limitación de la verificación.

