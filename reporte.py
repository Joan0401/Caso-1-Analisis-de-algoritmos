"""Prepara datos de medición y llama al exportador XLSX de Node/Artifact Tool."""
# Importa la lectura de argumentos para regenerar reportes desde la terminal.
import argparse
# Importa contadores que acumulan visitas y operaciones por intervalo.
from collections import Counter
# Importa la lectura y escritura de datos JSON.
import json
# Permite consultar las rutas de dependencias configuradas en el entorno.
import os
# Importa el manejo de archivos y carpetas.
from pathlib import Path
# Permite buscar el ejecutable de Node en el PATH.
import shutil
# Permite iniciar el exportador JavaScript como un proceso externo.
import subprocess

# Localiza la carpeta que contiene este módulo y el exportador.
BASE = Path(__file__).resolve().parent
# Construye la ubicación habitual del entorno de dependencias de Codex en este equipo.
RUNTIME = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies"


# Resuelve las rutas de Node y de la biblioteca que escribe el Excel.
def dependencias():
    # Prefiere NODE_BINARY; si no está definido, busca node en PATH.
    node = os.environ.get("NODE_BINARY") or shutil.which("node")
    # Comprueba si las dos alternativas anteriores no encontraron Node.
    if not node:
        # Usa entonces el ejecutable incluido en el entorno de Codex.
        node = str(RUNTIME / "node/bin/node.exe")
    # Consulta si el usuario indicó una carpeta de paquetes de JavaScript.
    modules = os.environ.get("ARTIFACT_NODE_MODULES")
    # Si no la indicó, aplica las ubicaciones disponibles en el proyecto o en Codex.
    if not modules:
        # Construye la ruta del enlace node_modules situado junto al código.
        local = BASE / "node_modules"
        # Prefiere ese enlace si contiene el paquete; de lo contrario usa la ubicación de Codex.
        modules = str(local if (local / "@oai/artifact-tool").exists() else RUNTIME / "node/node_modules")
    # Devuelve ambas rutas; esta función solo localiza, no instala dependencias.
    return node, modules


# Comprueba los archivos mínimos necesarios antes de comenzar a exportar.
def verificar_dependencias():
    # Obtiene las rutas con el procedimiento anterior.
    node, modules = dependencias()
    # Exige que existan el ejecutable y el descriptor del paquete de Excel.
    if not Path(node).is_file() or not (Path(modules) / "@oai/artifact-tool/package.json").is_file():
        # Explica qué dependencia falta en vez de continuar hasta un fallo de exportación.
        raise RuntimeError("Falta Node o @oai/artifact-tool. Ver README: NODE_BINARY y ARTIFACT_NODE_MODULES")


# Convierte los historiales individuales de una ejecución en cuatro tablas.
def tablas(carpeta):
    # Inicializa las filas de Resumen, Intentos, Bucles y Recorridos.
    resumen, intentos, bucles, recorridos = [], [], [], []
    # Busca archivos por ronda en orden de nombre; no incluye ejecucion.json ni tablas.json.
    for archivo in sorted(carpeta.glob("*_ronda_*.json")):
        # Lee el archivo como texto UTF-8 y convierte su JSON a un diccionario.
        d = json.loads(archivo.read_text(encoding="utf-8"))
        # Extrae el número de ronda de este historial.
        ronda = d["ronda"]
        # Compatibilidad con los historiales anteriores al cambio de nombres.
        # Traduce las etiquetas antiguas al nombre actual; los JSON originales no se modifican.
        algoritmo = {'R3': 'Retroceso', 'V1': 'Voraz'}.get(d['algoritmo'], d['algoritmo'])
        # Recorre los bucles del historial cargado en memoria.
        for bucle in d['bucles']:
            # Actualiza sus etiquetas antiguas para que el reporte muestre los nombres completos.
            bucle['nombre'] = bucle['nombre'].replace('R3', 'Retroceso').replace('V1', 'Voraz')
        # Obtiene únicamente los intentos que el coordinador realmente envió al servidor.
        enviados = d["intentos"]
        # Abrevia el diccionario de operaciones acumuladas para construir la fila de resumen.
        c = d["contadores"]
        # Agrega identificación, resultado, tiempo y cantidad de intentos enviados a la fila.
        resumen.append([ronda, algoritmo, d["resultado"], d["duracion_ms"], len(enviados),
            # Agrega visitas, activaciones y comparaciones de caracteres; un contador ausente vale cero.
            d["iteraciones"], d["total_bucles"], c.get("comparaciones_caracteres", 0),
            # Agrega nodos y la suma de los contadores cuyo nombre empieza con podas_.
            c.get("nodos", 0), sum(v for k, v in c.items() if k.startswith("podas_")),
            # Agrega los filtros de hojas completas y el máximo avance registrado.
            c.get("hojas_descartadas_distancia", 0), d["avance_maximo"],
            # Agrega la fase y asignación del último punto de control antes del cierre.
            d["estado"]["fase"], d["estado"]["asignacion"],
            # Agrega el último intento o vacío; solicitudes menos envíos son las canceladas.
            enviados[-1]["password"] if enviados else "", d["solicitudes"] - len(enviados)])
        # Construye un índice por identificador para consultar rápidamente los datos de cada bucle.
        por_bucle = {b["id"]: b for b in d["bucles"]}
        # Recorre cada activación registrada de un bucle de búsqueda.
        for b in d["bucles"]:
            # Crea una fila con su nombre, conjunto disponible y visitas efectivamente realizadas.
            bucles.append([ronda, algoritmo, b["id"], b["nombre"], b["disponibles"], b["visitados"]])
        # Intervalo de preparación: desde el envío anterior hasta este envío.
        # Así el trabajo que produce un candidato se atribuye a ese intento.
        # Inicia un índice único que avanzará por el historial de eventos sin volver al comienzo.
        indice = 0
        # Obtiene los eventos que ya fueron recortados al instante común de cierre.
        eventos = d["eventos"]
        # Recorre los intentos y agrega None para representar el intervalo final sin otra consulta.
        for intento in enviados + [None]:
            # Cada intervalo termina en el envío del intento o, para el último, en el corte de la ronda.
            limite = intento["envio"] if intento else d["corte"]
            # Reinicia los contadores locales del intervalo que está construyendo.
            vueltas, contadores = Counter(), Counter()
            # Consume los eventos pendientes cuyo instante no supera el límite de este intervalo.
            while indice < len(eventos) and eventos[indice]["t"] <= limite:
                # Obtiene el siguiente evento todavía no contabilizado en otro intervalo.
                e = eventos[indice]
                # Reconoce una iteración de alguno de los bucles instrumentados.
                if e["tipo"] == "iteracion":
                    # Suma una visita a su identificador de activación dentro de este intervalo.
                    vueltas[e["id"]] += 1
                # Reconoce el incremento de una operación específica.
                elif e["tipo"] == "contador":
                    # Suma esa cantidad bajo su nombre dentro del intervalo.
                    contadores[e["nombre"]] += e["cantidad"]
                # Avanza para que este mismo evento no se cuente otra vez en el siguiente intento.
                indice += 1
            # Usa el identificador del intento o la palabra CIERRE para el trabajo final.
            etiqueta = intento["id"] if intento else "CIERRE"
            # Recorre las activaciones que tuvieron visitas en este intervalo.
            for id_bucle, visitados in vueltas.items():
                # Recupera el nombre y tamaño original de esa activación.
                b = por_bucle[id_bucle]
                # Comienza una fila que vincula ronda, algoritmo, intento y activación.
                recorridos.append([ronda, algoritmo, etiqueta, id_bucle,
                                   # Completa la fila con el conjunto disponible al activar y las visitas de este intervalo.
                                   b["nombre"], b["disponibles"], visitados])
            # Usa la respuesta real si hay consulta; CIERRE no tiene respuesta del servidor.
            r = intento["respuesta"] if intento else {}
            # Comienza la fila de detalle del intento o del cierre.
            intentos.append([ronda, algoritmo, etiqueta,
                # Incluye contraseña y longitud; en CIERRE no hay contraseña enviada.
                intento["password"] if intento else "", len(intento["password"]) if intento else 0,
                # Convierte el envío o corte a milisegundos transcurridos desde el inicio común.
                (limite-d["inicio"])/1e6,
                # Calcula la duración de la transacción TCP; deja vacío ese campo en CIERRE.
                (intento["recepcion"]-intento["envio"])/1e6 if intento else None,
                # Agrega el estado y las pistas; SUCCESS puede no incluir coincidencias, distancia o score.
                r.get("status", "CIERRE"), r.get("matchedLetters"), r.get("distance"), r.get("score"),
                # Agrega visitas totales del intervalo y comparaciones de caracteres de ese intervalo.
                sum(vueltas.values()), contadores.get("comparaciones_caracteres", 0)])
    # Ordena el resumen primero por número de ronda y después por nombre de algoritmo.
    resumen.sort(key=lambda row: (row[0], row[1]))
    # Define el nombre de la primera hoja y sus columnas de identificación y tiempo.
    return {"Resumen": {"encabezados": ["Ronda", "Algoritmo", "Resultado", "Tiempo común (ms)",
        # Define sus columnas de consultas, visitas, activaciones, comparaciones y nodos.
        "Intentos TCP", "Iteraciones / visitas", "Bucles activados", "Comparaciones letras", "Nodos Retroceso",
        # Define las columnas de podas, filtros y punto de avance al cierre.
        "Podas Retroceso", "Hojas filtradas", "Avance máximo", "Fase al cierre", "Asignación al cierre",
        # Completa las columnas y asocia las filas del resumen.
        "Último intento", "Solicitudes canceladas"], "filas": resumen},
        # Define la hoja de consultas y sus columnas de identidad y contraseña.
        "Intentos": {"encabezados": ["Ronda", "Algoritmo", "Intento", "Contraseña", "Longitud",
        # Define tiempos, estado y las pistas originales del servidor.
        "Envío / corte (ms)", "Respuesta TCP (ms)", "Estado", "Coincidencias", "Distancia", "Score",
        # Completa los contadores por intervalo y asocia las filas de intentos.
        "Visitas del intervalo", "Comparaciones intervalo"], "filas": intentos},
        # Define la hoja de activaciones con elementos disponibles y visitados.
        "Bucles": {"encabezados": ["Ronda", "Algoritmo", "Activación", "Bucle", "Disponibles", "Visitados"], "filas": bucles},
        # Define la hoja que relaciona cada intento con las activaciones que recorrió.
        "Recorridos": {"encabezados": ["Ronda", "Algoritmo", "Intento / cierre", "Activación", "Bucle",
        # Completa las columnas de tamaños/visitas y devuelve las cuatro tablas.
        "Disponibles al activar", "Visitados en intervalo"], "filas": recorridos}}


# Genera el Excel de una ejecución; verificar permite añadir comprobaciones y vistas PNG.
def exportar(carpeta, verificar=False):
    # Detiene pronto la exportación si no están sus dependencias.
    verificar_dependencias()
    # Elige el JSON intermedio que consumirá el exportador JavaScript.
    datos = carpeta / "tablas.json"
    # Construye las tablas a partir de los historiales individuales guardados.
    contenido = tablas(carpeta)
    # Localiza los metadatos de origen del servidor.
    origen = carpeta / 'ejecucion.json'
    # Permite exportar también historiales antiguos que no tengan ese archivo.
    if origen.exists():
        # Añade al resumen la procedencia registrada, por ejemplo servidor externo o demostración.
        contenido['Resumen']['nota'] = json.loads(origen.read_text(encoding='utf-8'))['fuente']
    # Escribe las tablas como datos JSON; no vuelve a ejecutar ninguno de los algoritmos.
    datos.write_text(json.dumps(contenido, ensure_ascii=False), encoding='utf-8')
    # Obtiene el ejecutable Node y la carpeta de su paquete de Excel.
    node, modules = dependencias()
    # Pasa esa carpeta mediante el entorno al proceso JavaScript.
    env = {**os.environ, "ARTIFACT_NODE_MODULES": modules}
    # Construye la orden con exportador, JSON de entrada y ruta del XLSX de salida.
    comando = [node, str(BASE / "exportar_excel.mjs"), str(datos), str(carpeta / "resultados.xlsx")]
    # Comprueba si se solicitaron inspección y vistas de verificación.
    if verificar:
        # Agrega la opción correspondiente al comando del exportador.
        comando.append("--verificar")
    # Espera el exportador; check propaga sus errores y timeout limita esta espera a 180 segundos.
    subprocess.run(comando, check=True, env=env, timeout=180)


# Permite ejecutar este módulo como herramienta para regenerar un reporte existente.
if __name__ == "__main__":
    # Crea la ayuda de esa herramienta.
    p = argparse.ArgumentParser(description="Regenerar Excel desde métricas guardadas")
    # Exige la carpeta de los JSON históricos como argumento.
    p.add_argument("carpeta", type=Path)
    # Define la opción booleana para inspeccionar y generar vistas de las hojas.
    p.add_argument("--verificar", action="store_true")
    # Lee las opciones proporcionadas por el usuario.
    a = p.parse_args()
    # Resuelve la ruta absoluta e inicia la exportación con la opción elegida.
    exportar(a.carpeta.resolve(), a.verificar)



