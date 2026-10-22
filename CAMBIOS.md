# Probador Virtual Inteligente: mejoras de calce por figura y talle

## Qué cambió

Antes, la prenda se dibujaba usando solamente el **ancho de hombros**. Dos personas
con los mismos hombros, pero distinta cintura o cadera, recibían exactamente la misma
remera, y en cuerpos con cadera ancha la prenda no la cubría.

Ahora el sistema **mide la silueta real de la persona** y la prenda se adapta a su figura.

## Cómo funciona

1. **Silueta con MediaPipe.** Además de los 33 puntos del cuerpo, MediaPipe ahora
   entrega una *máscara de segmentación* que indica qué píxeles son de la persona
   (`output_segmentation_masks=True` en `pose_tracker.py`).
2. **Medición a 3 alturas** (`body_measure.py`). Desde el centro del torso se recorre
   hacia cada costado hasta salir de la silueta, a la altura de:
   - **pecho** (debajo de las axilas),
   - **cintura**,
   - **cadera**,

   y además se mide el **grosor del brazo**. Si el recorrido toca el brazo, se detiene:
   así no se mide "torso + brazo" cuando los brazos están pegados al cuerpo.
3. **Suavizado.** Las medidas se promedian entre cuadros (igual que los puntos), para
   que la prenda no tiemble.
4. **Figura estimada.** Con las proporciones pecho/cintura/cadera se estima la figura:
   rectángulo, reloj de arena, pera, triángulo invertido u ovalada. Se muestra en pantalla.
5. **La prenda se apoya en el borde real del cuerpo.** Los costados de la prenda
   (axila, cintura y ruedo) se colocan sobre las medidas, más la holgura:
   - **Talle elegido**: S = ajustado, M, L, XL = más suelto y un poco más largo.
   - **Calce de la prenda**: *entallado* (marca la cintura), *regular* o *holgado*
     (cae recto). Se define en `catalogo.py` con el campo `"calce"`.
   - El ruedo **nunca es más angosto que la cadera**.
6. **Puntos de la prenda sobre su contorno real** (`clothing_geometry.py`). Axilas,
   puños, hombros, cintura y ruedo se buscan sobre el borde verdadero de la imagen PNG,
   en lugar de porcentajes fijos. Esto elimina las "pestañas" en axilas y hombros.
7. **Respaldo.** Si la silueta no está disponible, se usan las proporciones de hombros
   como antes, así el probador nunca deja de funcionar.

## Cambios en la aplicación

- En la pantalla **"Elegiste: ..."** ahora se **elige el talle** antes de abrir la cámara.
- Nuevas teclas en la cámara:
  - **T**: cambia de talle en vivo.
  - **V**: muestra u oculta las líneas de medición de pecho, cintura y cadera (útil para la presentación).
- La barra superior muestra **talle, calce y figura estimada**.

## Archivos

| Archivo | Cambio |
| --- | --- |
| `body_measure.py` | **Nuevo.** Medición de la silueta, figura estimada y suavizado de medidas |
| `siluetas_prueba.py` | **Nuevo.** Genera personas sintéticas de distintas figuras para probar sin cámara |
| `pose_tracker.py` | Pide la silueta a MediaPipe, mide el cuerpo y calcula la prenda con talle y calce |
| `clothing_geometry.py` | Busca los puntos de la prenda sobre su contorno real |
| `catalogo.py` | Holgura por talle, tipo de calce por prenda y margen transparente |
| `main.py` | Selector de talle, teclas T y V, y datos de talle y figura en pantalla |
| `test_pruebas_usuario.py` | 3 pruebas nuevas: figuras, talles y calce, y funcionamiento sin silueta |
| `dia4_crear_prendas.py` | Arreglo: importaba una función que no existía (`crear_remera_png`) |
| `requirements.txt` | Se agrega `pillow`, que `main.py` ya usaba |

## Cómo probarlo

```
python test_pruebas_usuario.py
```

Las 9 pruebas deben pasar. La prueba 7 guarda `temp/validacion_prueba7_figuras.png`
con la misma remera sobre las 5 figuras.

Luego, ejecutá `iniciar_probador.bat`, elegí una prenda y un talle, y presioná
**V** frente a la cámara para ver las medidas.

## Límites a tener en cuenta

- Las medidas son en **píxeles** y de frente: sirven para la forma de la prenda, no
  para recomendar un talle en centímetros (eso necesitaría calibrar la cámara).
- La silueta incluye la ropa que la persona tiene puesta: con ropa muy suelta, el
  cuerpo se mide un poco más ancho.
- Con la persona de costado, la medición pierde precisión.

---

# Segunda etapa: prenda pegada al cuerpo y movimiento real

## Arreglo importante: prendas que se dibujaban rotas

Se agregaron puntos nuevos a las prendas (bajo busto, cadera alta y bíceps) para seguir
mejor las curvas, pero faltaba calcular **dónde van esos puntos sobre el cuerpo**. Por eso
todas las prendas se veían en pedazos. Ahora `pose_tracker.py` los calcula usando las
medidas de bajo busto y cadera alta de la silueta. La **prueba 10** controla que esto no
vuelva a pasar.

## Mejoras

| Mejora | Qué hace | Dónde |
| --- | --- | --- |
| Seguimiento sin atraso | MediaPipe en modo VIDEO y filtro *One Euro*: quieto suaviza el temblor; en movimiento responde rápido (un salto de 40 px se alcanza en 3 cuadros) | `pose_tracker.py`, `body_measure.py` |
| Prenda pegada a la silueta | El torso de la prenda no puede salir del borde del cuerpo más que un margen según el talle (S 2 px, M 4 px, L 7 px, XL 10 px). Las mangas tienen un margen mayor, sólo del lado de afuera del brazo | `body_layering.py` |
| Brazos por delante | Con los brazos al costado, el brazo tapa la tela del torso, como en la realidad | `body_layering.py` |
| Cuello que se adapta | El escote se ajusta al ancho del cuello, medido en la silueta (o con las orejas) | `pose_tracker.py` |
| Ruedo que sigue la cadera | Si la cadera se inclina, el ruedo se inclina con ella | `pose_tracker.py` |
| Giro del torso | Con la profundidad (Z) de hombros y caderas se estima el giro: el centro de la prenda (botones, logo) se corre hacia el lado que se aleja | `pose_tracker.py` |
| Brazos levantados | La axila de ese lado sube y el ruedo se levanta un poco | `pose_tracker.py` |
| Manga del brazo levantado | Antes se borraba al pasar por encima del mentón; ahora la protección del mentón sólo actúa cerca de la cara | `body_layering.py` |
| Sombras del cuerpo | Las luces y sombras del cuerpo pasan suavemente a la tela (máximo 25 %) para que se vea puesta y no pegada encima | `body_layering.py` |
| Más velocidad | La malla se deforma en una sola pasada (`cv2.remap`) en lugar de triángulo por triángulo: 2,4 veces más rápida | `clothing_warper.py` |
| FPS en pantalla | La barra superior muestra los cuadros por segundo | `main.py` |

## Teclas nuevas

- **R**: activa o desactiva el recorte de la prenda a la silueta (para comparar antes y después en la presentación).

## Pruebas nuevas

| Prueba | Qué verifica |
| --- | --- |
| 10 | Todas las prendas se dibujan completas |
| 11 | La tela no sale de la silueta más que el margen del talle |
| 12 | Con la cadera inclinada 10°, el ruedo se inclina entre 8° y 12° |
| 13 | Con el torso girado, el lado lejano es más angosto y el centro se corre |
| 14 | Con un brazo levantado, la axila de ese lado sube |
| 15 | Un movimiento brusco de 40 px se alcanza en menos de 3 cuadros |

La prueba 15 guarda `temp/validacion_prenda_pegada.png` para mostrar en la presentación.

## Límites

- El recorte depende de la silueta de MediaPipe: con poca luz o fondo desordenado puede
  fallar. Si la silueta parece dudosa, el programa **no recorta** (para no comerse la prenda).
- El giro se estima con la profundidad Z de MediaPipe, que es aproximada.
- Todavía no se pone el pelo por delante de la prenda.

---

# Tercera etapa: de frente, de espaldas y de perfil

## Qué hace ahora

| Situación | Qué pasa |
| --- | --- |
| **De frente** | La prenda normal, con logo, botones y escote |
| **Girada** (hasta ~45°) | La prenda acompaña el giro (centro corrido, lado lejano más angosto) |
| **De espaldas** | Se muestra la **espalda** de la prenda: sin logos, letras ni botones, y espejada |
| **De perfil** | La prenda se desvanece suavemente y aparece el aviso "Girá un poco hacia la cámara" (no hay foto de costado, así que mostrarla sería una prenda deformada) |

La barra superior muestra la **vista** detectada: De frente / Girada / De espaldas / De perfil.

## Cómo sabe hacia dónde mirás (`pose_tracker.py`)

- **Espalda:** en la imagen espejada, de frente, el hombro izquierdo real (punto 11 de
  MediaPipe) aparece a la derecha de la pantalla. De espaldas, ese orden se invierte.
  Además, no se ve la cara (nariz y orejas con baja visibilidad).
- **Perfil:** el ancho de los hombros es muy chico comparado con el largo del torso
  (menos del 40 %).
- **Girada:** se usa la profundidad Z de hombros y caderas.
- **Sin parpadeos:** la vista cambia sólo si el nuevo estado se mantiene 4 cuadros seguidos.

## Vista de espalda (`vista_espalda.py`, módulo nuevo)

1. Si existe una foto de la espalda, se usa. Basta con guardarla en `prendas/` con el
   mismo nombre más `_espalda`. Ejemplo: `polo_ralph_lauren_espalda.png`.
2. Si no existe, se genera **automáticamente**: se detectan los detalles del frente
   (logos, letras, botones), se borran rellenándolos con la tela de alrededor
   (*inpainting* de OpenCV) y se espeja la imagen.

## Pruebas nuevas

| Prueba | Qué verifica |
| --- | --- |
| 16 | Detecta bien frente, girada, perfil y espalda, y no parpadea por un cuadro raro |
| 17 | Todas las prendas tienen vista de espalda, con menos detalles que el frente |
| 18 | De perfil la prenda se desvanece de forma gradual |

Se guarda `temp/validacion_frente_espalda.png` para la presentación.

## Límites

- La espalda automática es una aproximación: el color y la silueta son los de la prenda,
  pero los detalles reales de la espalda (costuras, etiquetas, otro estampado) no se conocen.
  Con una foto de espalda real se ve mejor.
- De perfil no se muestra la prenda: haría falta una foto de costado de cada prenda.

---

# Cuarta etapa: ajuste tipo escáner y velocidad en notebooks lentas

## Prueba real con la cámara

En la primera prueba con la cámara, el probador iba a **3 a 5 FPS** y la prenda no copiaba la
forma del cuerpo. Se midió cada etapa en la notebook (`medir_rendimiento.py`):

| Etapa | Antes |
| --- | --- |
| Cámara | 24 ms |
| MediaPipe + medidas | 65 ms |
| Malla | 21 ms |
| Composición | 84 ms |
| **Total** | **194 ms (5 FPS)** |

## Velocidad

- Todo se calcula sobre una imagen de **640 × 360** y se agranda para mostrarla
  (`ANCHO_PROCESO` en `main.py`). Es la mejora más grande en notebooks lentas.
- La detección de brazos por delante de la prenda se calcula sólo en la zona de la
  prenda, no en toda la imagen (`body_layering.py`).

## Ajuste tipo escáner (`ajuste_silueta.py`, módulo nuevo)

La malla ubica la prenda con algunos puntos del cuerpo; entre esos puntos la tela salía
recta. Ahora la prenda **copia la silueta**:

| Parte | Cómo se ajusta |
| --- | --- |
| **Hombros** | Columna por columna: la línea de arriba de la prenda se apoya sobre la línea real del hombro (con un límite para que no se "trepe" al pelo largo) |
| **Mangas** | Fila por fila: el borde de afuera de la manga llega al borde de afuera del brazo |
| **Torso** | Fila por fila, desde debajo de las mangas hasta el ruedo: los bordes de la tela se llevan a los bordes del cuerpo (sin contar los brazos), más la holgura del talle |

- El **calce** se respeta: *entallado* sigue el cuerpo; *regular* cae un poco más recto;
  *holgado* nunca se mete en la cintura.
- Se suaviza entre cuadros para que el borde no tiemble.
- Con la tecla **R** se apaga y se prende (escáner + recorte), para comparar.

## Prueba nueva

| Prueba | Qué verifica |
| --- | --- |
| 19 | El borde de la tela queda a menos de 1 px del borde del cuerpo en cintura y cadera, y la línea de los hombros se acerca a la del cuerpo (13 px → 3,5 px) |

## Consejos para usarlo

- Alejate de la cámara hasta que se vean **los hombros y la cadera** (1,5 a 2 metros).
- Buena luz y fondo liso: la silueta sale mejor y el escáner se ajusta mejor.
- La ropa que tenés puesta puede verse por el escote de la prenda virtual, igual que si te
  probaras una prenda encima de otra.

---

# Quinta etapa: MediaPipe más liviano y proyecto más fácil de instalar

## Dónde se iba el tiempo

Con la persona frente a la cámara, cada cuadro tardaba 91 ms (11 FPS) y **78 ms eran de
MediaPipe**. Se midió qué conviene cambiar:

| Idea | Resultado de la medición |
| --- | --- |
| Bajar la resolución que recibe MediaPipe | 640 → 480 px ahorra ~15-20 ms. Más chico no ayuda: el modelo igual la reduce a 256 px por dentro |
| Pedir la silueta sólo cada N cuadros | La silueta cuesta sólo 3-10 ms, y MediaPipe no deja apagarla por cuadro: haría falta un segundo detector, que cuesta más de lo que ahorra. **No se hizo** |
| Saltear cuadros | Es la mejora grande: el cuadro salteado cuesta ~3 ms en lugar de ~80 ms |

## Qué cambió (`pose_tracker.py`)

- MediaPipe recibe una imagen de **480 px** de ancho (`ANCHO_MEDIAPIPE` en `main.py`).
- MediaPipe corre **1 de cada 2 cuadros** (`CADA_N_CUADROS_MEDIAPIPE`). En el cuadro intermedio:
  - cada punto del cuerpo avanza con la **velocidad** que traía entre las dos últimas detecciones
    (como máximo 0,1 s hacia adelante);
  - la **silueta anterior se corre** lo mismo que se movió el torso, así el escáner y el recorte
    siguen pegados al cuerpo;
  - las medidas (pecho, cintura, cadera, cuello) se reutilizan: el cuerpo no cambia de forma en 30 ms;
  - la vista (frente / espalda / perfil) sólo cambia con detecciones reales.
- Si la persona se pierde, MediaPipe vuelve a correr **en todos los cuadros** hasta encontrarla.
- Para volver al comportamiento anterior: `CADA_N_CUADROS_MEDIAPIPE = 1` y `ANCHO_MEDIAPIPE = 640`.

Estimación: de ~91 ms a ~45-50 ms por cuadro (**~20 FPS**). Para confirmarlo en la notebook:
`python medir_rendimiento.py` parado frente a la cámara.

## Prueba nueva

| Prueba | Qué verifica |
| --- | --- |
| 20 | Con una persona que se mueve 8 px por cuadro, MediaPipe se llama la mitad de las veces y la prenda queda a menos de 3 px de donde estaría detectando siempre (resultado: 0,3 px); la silueta predicha queda en su lugar |

## Instalación y arranque

- `requirements.txt`: pedía `mediapipe==0.10.14`, que no se instala en Python 3.14. Ahora pide
  `mediapipe>=1.0.1` (la versión con la que se probó).
- `iniciar_probador.bat` y `ejecutar.bat`: usan primero el entorno `.venv` del proyecto (antes
  buscaban primero un Python de otra herramienta), funcionan aunque se abran desde otra carpeta,
  y si no encuentran Python explican cómo crear el entorno.
- Las tildes ya no salen rotas (`cat�logo`) cuando la salida se guarda en un archivo o se redirige.
- `.gitignore` deja afuera las carpetas `respaldo_*`, `.venv_viejo`, `capturas/` y `temp/`,
  listo para usar git en lugar de copias a mano.

## Límites

- La predicción supone que el cuerpo sigue moviéndose igual durante un cuadro: en un cambio
  brusco de dirección, la prenda puede pasarse unos píxeles durante 1 cuadro (33 ms) hasta la
  siguiente detección.

---

# Sexta etapa: `main.py` separado en módulos

`main.py` tenía 1275 líneas que mezclaban la interfaz, la cámara y el HUD. Ahora cada parte
está en su archivo. **El funcionamiento no cambió**: el código se movió tal cual (se comprobó
que las 33 funciones, clases y constantes son idénticas a las originales).

| Archivo | Qué tiene |
| --- | --- |
| `main.py` | Sólo el punto de entrada (`python main.py` o `iniciar_probador.bat`, igual que antes) |
| `config.py` | Constantes: rendimiento (`ANCHO_MEDIAPIPE`, `CADA_N_CUADROS_MEDIAPIPE`…), archivos, suavizado y colores |
| `recursos.py` | Descarga del modelo, carpetas y nombres de las capturas |
| `galeria.py` | Interfaz Tkinter: galería, pantalla "Elegiste…" y tabla de medidas |
| `probador_camara.py` | Bucle de la cámara: detección, malla, escáner, capas y teclas |
| `hud.py` | Textos de la barra superior e inferior y líneas de medidas (tecla V) |

- `medir_rendimiento.py` ahora toma la configuración de `config.py` (antes tenía una copia).
- Se quitaron imports que `main.py` no usaba (`datetime`, `mediapipe`, etc.).

---

# Séptima etapa: el dibujo de la prenda más rápido y MediaPipe en paralelo

## Lo que mostró la cámara

Con la persona frente a la cámara, después de la quinta etapa:

| Etapa | Tiempo |
| --- | --- |
| Cámara | 8 ms |
| MediaPipe + medidas | 33 ms (antes 78) |
| **Malla + escáner** | **60 ms** |
| Composición | 20 ms |
| **Total** | **121 ms (8 FPS)** |

MediaPipe ya había mejorado, pero el dibujo de la prenda pasó a ser lo más lento.

## Más velocidad sin cambiar el resultado

Las imágenes que salen son **idénticas píxel por píxel** a las de antes (se compararon 2430
casos del escáner y 810 de malla y composición: todas las prendas, figuras, poses y talles).

| Parte | Qué cambió | Tiempo |
| --- | --- | --- |
| Escáner (`ajuste_silueta.py`) | Hombros, mangas y torso se calculaban fila por fila (o columna por columna) con bucles de Python; ahora todas las filas a la vez con numpy | 45 → 17 ms |
| Malla (`clothing_warper.py`) | Se evita armar una tabla de alto × ancho × 2 × 3 para cada píxel | 10 → 9 ms |
| Composición (`body_layering.py`) | La mezcla de la prenda con la cámara se hace sobre todo el recuadro de una vez; una dilatación de la silueta que se calculaba dos veces ahora se calcula una | 18 → 16 ms |

(Tiempos medidos con la persona sintética al tamaño real del probador.)

## MediaPipe en segundo plano (`pose_tracker.py`)

La notebook tiene 4 núcleos y el probador usaba uno solo. Ahora MediaPipe corre **en otro hilo**:

- El bucle de la cámara le pasa un cuadro a MediaPipe y sigue dibujando la prenda sin esperarlo.
- Cada cuadro usa la última detección **adelantada hasta "ahora"** con la velocidad del cuerpo
  (la misma predicción de la quinta etapa), así la demora de MediaPipe no se nota.
- Las medidas y la vista (frente / espalda / perfil) se actualizan cada vez que llega una detección.
- Se activa con `MEDIAPIPE_EN_SEGUNDO_PLANO = True` en `config.py`. Con `False` vuelve al modo
  de un paso por vez (1 de cada `CADA_N_CUADROS_MEDIAPIPE` cuadros).

## Prueba nueva

| Prueba | Qué verifica |
| --- | --- |
| 21 | Con un MediaPipe simulado que tarda 60 ms y una persona que camina en tiempo real: el probador no espera a MediaPipe (≈4 ms por cuadro), ningún cuadro queda sin prenda y la prenda queda a ~3 px de la persona (lo mismo que detectando en todos los cuadros) |

## Límites

- MediaPipe y el dibujo de la prenda comparten el procesador: cuánto se gana depende de la
  notebook. Para saberlo: `python medir_rendimiento.py` frente a la cámara.
- La prueba 21 usa tiempos reales: en una compu muy cargada podría fallar de vez en cuando.
