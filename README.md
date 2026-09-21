## 1. Primera ventana de PowerShell: servidor del profesor

Copia los comandos uno por uno:

```powershell
cd "C:\Users\joanc\OneDrive\Desktop\Analisis de algoritmos\Caso #1 prueba"
javac -d servidor/bin servidor/passwordhack/PasswordHackServer.java
java -cp servidor/bin passwordhack.PasswordHackServer
```

Continúa si la compilación terminó sin errores y aparece `PasswordHack server listening on port 4000`. Deja esta ventana abierta. Necesitas JDK 11 o posterior; el procedimiento de instalación usado fue para JDK 21.

El servidor conserva el código proporcionado por el profesor. Con autorización del usuario, únicamente se eliminó la línea con el carácter de acento grave suelto que impedía compilarlo. No se añadieron comentarios ni se cambió su lógica. El archivo original en Descargas permanece intacto. Su fuente original corresponde al repositorio del profesor: https://github.com/vsurak/cursostec/tree/master/algoritmos/src/passwordhack . Los clientes no leen la contraseña que imprime en consola.

## 2. Segunda ventana de PowerShell: competencia

```powershell
cd "C:\Users\joanc\OneDrive\Desktop\Analisis de algoritmos\Caso #1 prueba"
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" ".\competir.py"
```

Este comando inicia Retroceso y Voraz automáticamente. No utiliza scripts `.ps1`. Al iniciar pregunta `¿Cuántas rondas quieres ejecutar? N =`. Escribe un entero positivo y presiona Enter. También puedes agregar `--rondas 10` al comando para ejecutar diez rondas sin pregunta. N se aplica a toda la competencia: ambos algoritmos participan en cada una de las N rondas. Ambos algoritmos envían JSON al mismo servidor a través del coordinador. Cuando uno acierta, ambos guardan métricas y pasan a la siguiente ronda.

Al terminar puedes detener el servidor con Ctrl+C en la primera ventana. No conectes clientes ajenos mientras corre la competencia.

## 3. Resultados para presentar

Cada ejecución crea una carpeta nueva en `resultados` con:

- `resultados.xlsx`: resumen, intentos, bucles y recorridos. Se actualiza después de cada ronda.
- `Retroceso_ronda_XXXX.json` y `Voraz_ronda_XXXX.json`: métricas individuales, necesarias para auditar o regenerar el reporte.
- `ejecucion.json`: origen y configuración de la ejecución.
- `tablas.json`: tablas que alimentan el Excel.

Ejemplo: Se conservó la ejecución de diez rondas `resultados/20260920_133211_487549`. Su origen registrado es el servidor TCP externo en `127.0.0.1:4000`.

Cierra el Excel de una ejecución mientras se está actualizando, para evitar que Windows bloquee su reemplazo. Los JSON guardados permiten regenerarlo si falla la exportación:

```powershell
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" ".\reporte.py" ".\resultados\20260920_133211_487549"
```

## 4. Qué hace cada archivo conservado

| Archivo | Uso |
|---|---|
| `retroceso.py` | Retroceso: cantidades de letras, restricciones, MRV, poda y retroceso |
| `voraz.py` | Voraz: longitud y fijación irreversible de posiciones |
| `competir.py` | Dos procesos, conexión TCP, N rondas y cierre común |
| `cliente.py` | Mensajes y guardado individual de métricas |
| `metricas.py` | Bucles, comparaciones, estados y distancia de Levenshtein |
| `reporte.py` | Convierte los JSON de métricas en tablas |
| `exportar_excel.mjs` | Genera el archivo Excel |
| `servidor/` | Fuente Java y compilación del servidor |
| `node_modules` | Enlace local a la biblioteca necesaria para Excel |

Las demostraciones, pruebas auxiliares y propuesta inicial se retiraron para dejar la carpeta enfocada en la defensa. Los algoritmos de producción no se modificaron durante la limpieza.

## 5. Dependencias y entrega

Python 3.10 o posterior y JDK 11 o posterior. El exportador usa Node.js y `@oai/artifact-tool` del entorno de Codex de este equipo. `node_modules` es un enlace local, no algo para subir a GitHub. En otra computadora hay que disponer de esa biblioteca o adaptar el exportador; no se presupone su disponibilidad pública en npm.

Para usar instalaciones existentes de Node y la biblioteca se pueden definir `NODE_BINARY` y `ARTIFACT_NODE_MODULES`. La conexión al servidor se puede configurar con `--host` y `--puerto` en `competir.py`.

`.gitignore` excluye dependencias, caché, clases compiladas e historiales. Para entregar resultados por GitHub agrega explícitamente el Excel seleccionado. La publicación en un repositorio personal y la validación académica del profesor no se han confirmado.


Los historiales anteriores pueden conservar los prefijos R3 y V1 en sus JSON; el reporte los muestra como Retroceso y Voraz. Las nuevas ejecuciones ya utilizan los nombres completos.

## Cómo estudiar los comentarios línea por línea

Cada línea de código de los seis módulos Python tiene una explicación en español inmediatamente antes. En llamadas y diccionarios que ocupan varias líneas se explica también el significado de sus partes. Se conservaron las explicaciones de complejidad y de los paradigmas. El exportador JavaScript también está comentado. El servidor Java conserva el código del profesor, con la única eliminación autorizada del carácter suelto que impedía compilarlo.

Orden recomendado de lectura:

1. `voraz.py`: preparación, referencia, etapas, óptimo local y decisión irreversible.
2. `retroceso.py`: cantidades de letras, restricciones, dominios, MRV, recursión y restauración.
3. `metricas.py`: registro de eventos, generadores con `yield`, corte común y Levenshtein.
4. `cliente.py`: recepción de mensajes, señal FIN y guardado individual.
5. `competir.py`: procesos separados, turnos TCP, N rondas y notificación del primer acierto.
6. `reporte.py` y `exportar_excel.mjs`: transformación del historial y escritura del Excel.
7. `servidor/passwordhack/PasswordHackServer.java`: formato del protocolo y cambio de contraseña.

Los comentarios explican la versión existente: no cambian las consultas, las mediciones ni el cierre al primer acierto. En particular, el segundo algoritmo continúa registrándose como INCONCLUSO.
