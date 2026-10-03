# Mantener el perfil

La actividad aparece inmediatamente después de la presentación. El README principal contiene el diseño, los proyectos y el enlace al CV completo seleccionado por Cristian.

## Actualización de actividad

El workflow **Update profile activity** se ejecuta cada seis horas, a los 17 minutos, y permite ejecución manual desde Actions. GitHub puede retrasar las ejecuciones programadas.

1. `scripts/activity_data.py` lee el calendario visible sin iniciar sesión en GitHub. Si hay token, contrasta también la API GraphQL oficial. Siempre conserva los datos visibles públicamente si existen diferencias.
2. Sólo obtiene repositorios públicos y eventos públicos para la lista de actividad reciente. El calendario puede incluir cantidades agregadas de trabajo privado que el propietario ya decidió mostrar en su perfil; no se obtienen nombres ni contenido privado.
3. `scripts/render_activity.py` valida cifras y fechas y genera las tarjetas de escritorio y móvil. La animación es decorativa: no cambia números ni intensidad del calendario.
4. Los resultados se guardan en `profile-metrics`, con autor `github-actions[bot]`. El bot no genera contribuciones atribuidas a Cristian y sus actualizaciones no aparecen en la lista de trabajo reciente del perfil.

Las imágenes se cargan desde esa rama. No dependen de servicios externos de estadísticas, rachas o insignias. El workflow usa el token automático de GitHub con permiso `contents: write` para publicar los resultados; no necesita un token personal guardado como secreto.

Si GitHub responde con datos incompletos o cambia el formato del calendario, la ejecución falla y preserva las últimas tarjetas válidas. La fecha de actualización se muestra en hora de Ecuador. Los números representan contribuciones, no exclusivamente commits.

## Validación local

Requiere Python 3.10 o superior, sin dependencias adicionales:

```sh
python -B -m unittest discover -s scripts -p 'test_*.py' -v
python -B scripts/activity_data.py
python -B scripts/render_activity.py
```

Los archivos generados locales están excluidos de la rama principal. Para inspeccionar los datos publicados, abrir `data/activity.json` en `profile-metrics`.

## CV y proyectos

El enlace principal apunta a `cv/Cristian_Bravo_Full_Stack_Developer_CV.pdf`. Es el PDF original elegido por Cristian, sin reescrituras. Al actualizarlo, sustituir ese mismo archivo para conservar los enlaces.

La selección y el orden de los repositorios fijados se administra en **Customize your pins** dentro del perfil de GitHub. Sus descripciones se editan en **About** de cada repositorio. El diseño de ese bloque nativo pertenece a GitHub y no admite CSS del README.
