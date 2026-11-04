# Mini Yolotzin

Aplicación web académica para explorar estimaciones de afluencia diaria en cinco estaciones de la Línea 3 del Metro de la Ciudad de México.

![Vista principal de Mini Yolotzin](assets/preview.png)

## Sitio público

Después de activar GitHub Pages, la aplicación estará disponible en:

<https://nayibi21.github.io/mini-yolotzin/>

## Qué incluye

- Predicción diaria para Indios Verdes, La Raza, Hidalgo, Centro Médico y Universidad.
- Comparación del modelo Random Forest contra una línea base histórica.
- Mapa esquemático con reproducción por fecha, zoom y selección de estaciones.
- Perfiles locales de clase que se guardan solamente en el navegador.
- Información de metodología, cobertura, errores y limitaciones.

Las estimaciones no representan ocupación dentro de los trenes, saturación de andenes ni datos en tiempo real.

## Abrirla en una computadora

No requiere instalación para visualizarla:

1. Descarga o clona el repositorio.
2. Conserva juntos `index.html` y `model-data.js`.
3. Abre `index.html` con Chrome, Safari, Firefox o Edge.

## Editar con ChatGPT, Codex o Claude

Abre la carpeta completa del repositorio en la herramienta que utilices y describe el cambio deseado. Antes de aceptar un cambio, pide que:

1. Lea `AGENTS.md`.
2. Conserve las limitaciones metodológicas.
3. No agregue contraseñas, tokens o claves dentro del código.
4. Compruebe que `index.html` carga `model-data.js` sin errores.
5. Resuma los archivos modificados.

Ejemplo de solicitud:

> Lee README.md y AGENTS.md. Cambia el texto de la pantalla de bienvenida sin modificar el modelo ni las predicciones. Revisa que la página siga funcionando en celular y dime qué archivos cambiaste.

## Trabajo entre colaboradoras

Antes de comenzar un cambio:

1. Sincronicen o descarguen la versión más reciente.
2. Procuren que una sola persona modifique `index.html` a la vez.
3. Guarden cada tarea en un commit pequeño con un mensaje descriptivo.
4. Suban el cambio y comprueben la página publicada.

Para cambios grandes, creen una rama y una Pull Request antes de mezclarla con `main`. Consulta [CONTRIBUTING.md](CONTRIBUTING.md).

## Publicar con GitHub Pages

En el repositorio, ve a:

`Settings → Pages → Build and deployment → Deploy from a branch`

Selecciona la rama `main`, la carpeta `/(root)` y pulsa **Save**. Los cambios enviados a `main` volverán a publicar la página automáticamente.

## Regenerar las estimaciones

Esto solo es necesario cuando se quiera actualizar el archivo oficial o volver a entrenar el modelo.

1. Descarga el CSV oficial de afluencia y guárdalo en la raíz con el nombre `afluencia_simple.csv`.
2. Crea un entorno de Python e instala las dependencias:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. Ejecuta:

```bash
python scripts/build_model_data.py
```

El script reemplaza `model-data.js`. El CSV está ignorado por Git y no debe subirse al repositorio.

## Fuente de datos

- Portal: [Afluencia diaria del Metro CDMX](https://datos.cdmx.gob.mx/dataset/afluencia-diaria-del-metro-cdmx/resource/0e8ffe58-28bb-4dde-afcd-e5f5b4de4ccb)
- Publicador: Gobierno de la Ciudad de México / SEMOVI.
- Cobertura utilizada por esta versión: 1 de enero de 2021 a 30 de septiembre de 2026.

## Archivos principales

- `index.html`: interfaz, estilos e interacciones.
- `model-data.js`: datos agregados, métricas y predicciones precalculadas.
- `scripts/build_model_data.py`: limpieza, entrenamiento, validación y exportación.
- `AGENTS.md`: reglas para asistentes de programación.
- `CONTRIBUTING.md`: flujo recomendado de colaboración.

