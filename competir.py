"""Competencia entre dos procesos independientes; un solo canal TCP evita mezclar rondas."""
# Importa el analizador de opciones como --rondas, --host y --puerto.
import argparse
# Importa colas deque para retirar solicitudes pendientes por orden de llegada.
from collections import deque
# Importa el formato JSON que usan servidor y clientes.
import json
# Permite copiar las variables de entorno de los procesos hijos.
import os
# Importa operaciones de rutas de archivos y carpetas.
from pathlib import Path
# Queue comunica hilos; Empty indica que venció la espera sin recibir un mensaje.
from queue import Empty, Queue
# Importa expresiones regulares para comprobar la forma de cada contraseña.
import re
# Importa la conexión TCP con el servidor Java.
import socket
# Permite lanzar cada algoritmo como un proceso Python independiente.
import subprocess
# Da acceso al ejecutable Python actual y a la salida de errores.
import sys
# Permite leer las salidas de ambos clientes en hilos separados.
from threading import Thread
# Importa el reloj monotónico en nanosegundos para medir cada ronda.
from time import perf_counter_ns

# Obtiene la carpeta absoluta de este archivo, independientemente de la carpeta de la terminal.
BASE = Path(__file__).resolve().parent


# Coordina los procesos, las consultas TCP, las rondas y el guardado.
class Coordinador:
    # Recibe servidor, salida, N rondas, tiempo máximo de espera y descripción del origen.
    def __init__(self, host, puerto, salida, rondas, timeout=30, fuente="Servidor TCP externo"):
        # Guarda la dirección y el puerto del servidor.
        self.host, self.puerto = host, puerto
        # Guarda la carpeta, el número de rondas y el límite de espera de comunicación.
        self.salida, self.rondas, self.timeout = salida, rondas, timeout
        # Conserva la descripción del servidor para identificar el origen del reporte.
        self.fuente = fuente
        # Prepara un diccionario que asociará cada nombre con su proceso hijo.
        self.procesos = {}
        # Crea la cola común donde ambos hilos receptores entregarán mensajes.
        self.entrada = Queue()
        # Inicializa una lista actualmente sin uso; el historial real se guarda en JSON por cliente.
        self.historial = []

    # Envía una orden a uno de los dos procesos por su nombre.
    def enviar(self, nombre, mensaje):
        # Busca el proceso destinatario en el diccionario.
        proceso = self.procesos[nombre]
        # Escribe el mensaje como una línea JSON en la entrada del cliente.
        proceso.stdin.write(json.dumps(mensaje) + "\n")
        # Vacía el búfer para que el cliente reciba la orden inmediatamente.
        proceso.stdin.flush()

    # Lee los mensajes de un cliente y los identifica con su nombre.
    def leer(self, nombre, proceso):
        # Captura errores de lectura o de conversión JSON del proceso.
        try:
            # Recorre las líneas que el cliente escribe en su salida estándar.
            for linea in proceso.stdout:
                # Decodifica cada mensaje y lo coloca en la cola junto a su emisor.
                self.entrada.put((nombre, json.loads(linea)))
        # Captura cualquier fallo de lectura o mensaje inválido.
        except Exception as error:
            # Envía el error al hilo principal mediante la misma cola.
            self.entrada.put((nombre, {"tipo": "ERROR", "mensaje": repr(error)}))
        # Se ejecuta al terminar la lectura, aunque haya ocurrido una excepción.
        finally:
            # Notifica que el proceso dejó de producir mensajes; durante la competencia es un fallo.
            self.entrada.put((nombre, {"tipo": "ERROR", "mensaje": "Cliente desconectado"}))

    # Obtiene el siguiente mensaje con un tiempo máximo de espera.
    def recibir(self, espera=None):
        # Permite transformar el agotamiento de la espera en un error explicativo.
        try:
            # Espera en la cola usando el límite configurado, salvo que se haya indicado otro.
            nombre, mensaje = self.entrada.get(timeout=self.timeout if espera is None else espera)
        # Detecta que no llegó ningún mensaje durante la espera permitida.
        except Empty:
            # Informa el problema y detiene la ejecución en vez de quedar esperando indefinidamente.
            raise TimeoutError("El cliente no respondió dentro del tiempo configurado")
        # Reconoce un error notificado por un cliente o por su hilo receptor.
        if mensaje["tipo"] == "ERROR":
            # Propaga el error indicando qué algoritmo lo produjo.
            raise RuntimeError(f"{nombre}: {mensaje['mensaje']}")
        # Entrega el nombre del emisor y el mensaje cuando no hay error.
        return nombre, mensaje

    # Ejecuta la competencia completa y recibe una función para exportar cada ronda.
    def ejecutar(self, exportar):
        # Crea una carpeta nueva; exist_ok=False evita sobrescribir una ejecución anterior.
        self.salida.mkdir(parents=True, exist_ok=False)
        # Abre la construcción del JSON con los metadatos de la ejecución.
        (self.salida / 'ejecucion.json').write_text(json.dumps({
            # Incluye procedencia, dirección y puerto del servidor usado.
            'fuente': self.fuente, 'host': self.host, 'puerto': self.puerto,
            # Incluye N y escribe los metadatos con sangría y codificación UTF-8.
            'rondas_configuradas': self.rondas}, ensure_ascii=False, indent=2), encoding='utf-8')
        # Copia el entorno y configura UTF-8 en los canales de texto de los procesos hijos.
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        # Garantiza que la limpieza de procesos ocurra también si falla alguna ronda.
        try:
            # Cada script tiene su propio intérprete, clase, memoria y métricas.
            # Asocia cada nombre de algoritmo con su archivo ejecutable.
            for nombre, archivo in (("Retroceso", "retroceso.py"), ("Voraz", "voraz.py")):
                # Inicia un proceso del sistema operativo; no es una llamada secuencial al algoritmo.
                proceso = subprocess.Popen(
                    # Usa el mismo Python; -u desactiva el búfer y --controlado activa el canal de coordinación.
                    [sys.executable, "-u", str(BASE / archivo), "--controlado",
                     # Pasa la carpeta de salida y crea una tubería hacia la entrada del hijo.
                     "--salida", str(self.salida)], stdin=subprocess.PIPE,
                    # Captura la salida del hijo como texto UTF-8 y utiliza el entorno preparado.
                    stdout=subprocess.PIPE, text=True, encoding="utf-8", env=env)
                # Conserva el proceso para poder enviarle órdenes y cerrarlo después.
                self.procesos[nombre] = proceso
                # Arranca un lector en segundo plano dedicado a ese cliente.
                Thread(target=self.leer, args=(nombre, proceso), daemon=True).start()
            # Crea un conjunto para contar clientes listos sin duplicarlos.
            listos = set()
            # No inicia la conexión de competencia hasta recibir ambos saludos.
            while len(listos) < 2:
                # Obtiene el siguiente mensaje y su emisor.
                nombre, mensaje = self.recibir()
                # Comprueba que el mensaje sea el saludo de arranque esperado.
                if mensaje["tipo"] != "LISTO":
                    # Detiene la competencia si un cliente incumple el protocolo de inicio.
                    raise RuntimeError("Falta saludo LISTO")
                # Marca a ese algoritmo como listo.
                listos.add(nombre)
            # Abre TCP con cierre automático al abandonar el bloque with.
            with socket.create_connection((self.host, self.puerto), self.timeout) as conexion:
                # Desactiva Nagle para reducir la espera de mensajes pequeños.
                conexion.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                # Crea una interfaz binaria de lectura y escritura sobre el socket.
                with conexion.makefile("rwb") as canal:
                    # Recorre las rondas 1 a N; el límite superior de range es exclusivo.
                    for ronda in range(1, self.rondas + 1):
                        # Ejecuta una ronda completa, incluida la espera de ambos guardados.
                        self.ronda(canal, ronda)
                        # Fuera del tiempo de competencia; ambos ya guardaron su JSON.
                        # Actualiza el Excel después del cierre; esta exportación queda fuera del tiempo de búsqueda.
                        exportar(self.salida)
        # Comienza la limpieza que siempre ocurre al terminar o fallar la competencia.
        finally:
            # Recorre los procesos que alcanzaron a iniciarse.
            for nombre, proceso in self.procesos.items():
                # poll devuelve None si el proceso todavía está ejecutándose.
                if proceso.poll() is None:
                    # Primero intenta un cierre ordenado mediante el protocolo.
                    try:
                        # Solicita al cliente que salga.
                        self.enviar(nombre, {"tipo": "SALIR"})
                        # Espera hasta tres segundos a que el cliente termine por sí mismo.
                        proceso.wait(timeout=3)
                    # Si el canal falla o el hijo no termina a tiempo, aplica el cierre de respaldo.
                    except (OSError, subprocess.TimeoutExpired):
                        # Termina ese proceso hijo que no respondió al cierre normal.
                        proceso.terminate()
                        # Espera su terminación para no dejarlo ejecutándose en segundo plano.
                        proceso.wait(timeout=3)
                # Comprueba que exista la tubería de entrada antes de cerrarla.
                if proceso.stdin:
                    # Libera la tubería usada para enviar órdenes al hijo.
                    proceso.stdin.close()
                # Comprueba que exista la tubería de salida antes de cerrarla.
                if proceso.stdout:
                    # Libera la tubería usada para recibir mensajes del hijo.
                    proceso.stdout.close()

    # Administra una sola contraseña compartida por ambos algoritmos.
    def ronda(self, canal, numero):
        # Marca el inicio común antes de comunicar la ronda a los clientes.
        inicio = perf_counter_ns()
        # Alterna qué cliente recibe primero INICIO para reducir un sesgo fijo de despacho.
        orden = ["Retroceso", "Voraz"] if numero % 2 else ["Voraz", "Retroceso"]
        # Recorre ambos nombres en el orden elegido para esta ronda.
        for nombre in orden:
            # Envía el mismo número de ronda y el mismo instante de inicio a cada cliente.
            self.enviar(nombre, {"tipo": "INICIO", "ronda": numero, "inicio": inicio})
        # Crea una cola independiente de solicitudes listas para cada algoritmo.
        pendientes = {nombre: deque() for nombre in orden}
        # Crea un historial de consultas TCP separado por algoritmo.
        intentos = {nombre: [] for nombre in orden}
        # Da prioridad inicial al primer nombre del orden de esta ronda.
        preferido = orden[0]
        # Atiende solicitudes hasta que un SUCCESS cierre la ronda.
        while True:
            # Comprueba si ninguna de las dos colas tiene solicitudes pendientes.
            if not any(pendientes.values()):
                # Espera una solicitud si todavía no hay trabajo listo.
                nombre, mensaje = self.recibir()
                # Agrega el mensaje a la cola de su emisor.
                pendientes[nombre].append(mensaje)
            # Reunir mensajes disponibles. Alternar si ambos están esperando.
            # Recoge también los mensajes ya disponibles sin esperar a nuevos.
            while not self.entrada.empty():
                # Obtiene el siguiente mensaje que el hilo receptor dejó en la cola.
                nombre, mensaje = self.recibir()
                # Lo coloca al final de la cola de su algoritmo.
                pendientes[nombre].append(mensaje)
            # Calcula el nombre del competidor que no tiene la prioridad actual.
            otro = "Voraz" if preferido == "Retroceso" else "Retroceso"
            # Atiende al preferido si tiene trabajo; si no, atiende al otro.
            nombre = preferido if pendientes[preferido] else otro
            # Retira la solicitud más antigua del cliente elegido.
            mensaje = pendientes[nombre].popleft()
            # Cambia la preferencia para alternar cuando ambos tienen solicitudes listas.
            preferido = "Voraz" if nombre == "Retroceso" else "Retroceso"
            # Exige un INTENTO que pertenezca a la ronda actual.
            if mensaje["tipo"] != "INTENTO" or mensaje["ronda"] != numero:
                # Rechaza un mensaje inesperado o de otra ronda para evitar contaminar resultados.
                raise RuntimeError("Solicitud fuera de su ronda")
            # Extrae la contraseña que propone el algoritmo.
            candidato = mensaje["password"]
            # Comprueba que toda la cadena tenga entre dos y cuatro letras minúsculas.
            if not re.fullmatch("[a-z]{2,4}", candidato):
                # Rechaza candidatos inválidos antes de enviarlos al servidor.
                raise RuntimeError("El cliente produjo una contraseña inválida")
            # Registra el instante en que comienza el envío de esta consulta TCP.
            envio = perf_counter_ns()
            # Codifica password en JSON, agrega el salto de línea y lo convierte a bytes.
            canal.write((json.dumps({"password": candidato}) + "\n").encode())
            # Fuerza el envío de la consulta que podría quedar en el búfer.
            canal.flush()
            # Lee una respuesta con un límite de tamaño para no aceptar una línea ilimitada.
            linea = canal.readline(65537)
            # Detecta cierre de conexión o una respuesta demasiado larga.
            if not linea or len(linea) > 65536:
                # Detiene la competencia cuando no puede confiar en la respuesta.
                raise ConnectionError("Respuesta ausente o demasiado grande")
            # Convierte los bytes JSON del servidor en un diccionario.
            respuesta = json.loads(linea)
            # Registra el instante de recepción; si hay éxito, será el corte común de la ronda.
            recepcion = perf_counter_ns()
            # Acepta únicamente los estados normales del protocolo.
            if respuesta.get("status") not in ("FAIL", "SUCCESS"):
                # Informa respuestas ERROR u otros estados desconocidos.
                raise RuntimeError(f"Error del servidor: {respuesta}")
            # Verifica las pistas solo en FAIL; SUCCESS no las incluye.
            if respuesta["status"] == "FAIL":
                # Recorre los tres campos numéricos requeridos en una respuesta fallida.
                for clave in ("matchedLetters", "distance", "score"):
                    # Comprueba que cada valor sea exactamente un entero, no un campo ausente u otro tipo.
                    if type(respuesta.get(clave)) is not int:
                        # Detiene la ronda ante una pista de formato inválido.
                        raise RuntimeError(f"Respuesta inválida: falta {clave}")
            # Prepara el registro de la consulta con su identificador y contraseña.
            intento = {"id": mensaje["id"], "password": candidato,
                       # Agrega las marcas de tiempo y la respuesta completa recibida.
                       "envio": envio, "recepcion": recepcion, "respuesta": respuesta}
            # Registra este intento únicamente después de realizar la transacción TCP.
            intentos[nombre].append(intento)
            # Detecta el primer acierto confirmado por el servidor.
            if respuesta["status"] == "SUCCESS":
                # FRONTERA ATÓMICA: no se envía ninguna otra consulta de esta ronda.
                # El servidor ya generó el siguiente secreto, pero no se tocará
                # hasta que ambos clientes confirmen que guardaron sus métricas.
                # Notifica el cierre tanto al ganador como al otro competidor.
                for cliente in orden:
                    # Envía una orden FIN con el número de ronda.
                    self.enviar(cliente, {"tipo": "FIN", "ronda": numero,
                        # Comunica el ganador y el mismo instante de corte para ambos procesos.
                        "ganador": nombre, "corte": recepcion,
                        # Entrega a cada cliente únicamente su lista de intentos realmente enviados.
                        "intentos": intentos[cliente]})
                # Prepara un conjunto para las confirmaciones de guardado.
                guardados = set()
                # Impide empezar otra ronda hasta que ambos clientes hayan guardado sus métricas.
                while len(guardados) < 2:
                    # Recibe confirmaciones o solicitudes que quedaron en tránsito antes de FIN.
                    cliente, notificacion = self.recibir()
                    # Reconoce una solicitud tardía que ya no debe enviarse al servidor.
                    if notificacion["tipo"] == "INTENTO":
                        # Petición enviada antes de recibir FIN: CANCELADA, jamás TCP.
                        # Comprueba que esa solicitud cancelada pertenezca a la ronda que está cerrando.
                        if notificacion["ronda"] != numero:
                            # Informa una mezcla de rondas si la solicitud no corresponde.
                            raise RuntimeError("Intento cancelado con ronda incorrecta")
                        # Descarta la solicitud sin convertirla en un intento TCP.
                        continue
                    # Exige que cualquier otro mensaje confirme el guardado de esta ronda.
                    if notificacion["tipo"] != "GUARDADO" or notificacion["ronda"] != numero:
                        # Detiene la ejecución si no recibe una confirmación coherente.
                        raise RuntimeError("Confirmación de cierre inválida")
                    # Registra quién terminó de guardar; un conjunto evita contar dos veces al mismo cliente.
                    guardados.add(cliente)
                # Muestra número de ronda, ganador y la contraseña que obtuvo SUCCESS.
                print(f"Ronda {numero}/{self.rondas}: {nombre} ÉXITO; contraseña={candidato}; "
                      # Añade las cantidades de consultas TCP de cada algoritmo.
                      f"Retroceso={len(intentos['Retroceso'])}, Voraz={len(intentos['Voraz'])} intentos; "
                      # Muestra el tiempo común en milisegundos con dos decimales y vacía la salida.
                      f"{(recepcion-inicio)/1e6:.2f} ms", flush=True)
                # Termina esta ronda; el bucle de ejecutar podrá iniciar la siguiente.
                return
            # Si no hubo éxito, prepara la respuesta para el cliente que hizo la consulta.
            self.enviar(nombre, {"tipo": "RESPUESTA", "id": mensaje["id"],
                                 # Le devuelve las pistas del servidor; el otro algoritmo no recibe esta información.
                                 "respuesta": respuesta})


# Solicita N por teclado cuando no se indicó --rondas.
def solicitar_rondas():
    """N es la cantidad de rondas completas, compartida por ambos algoritmos."""
    # Repite la pregunta hasta obtener un entero positivo o una interrupción.
    while True:
        # Captura errores al convertir el texto introducido a entero.
        try:
            # Muestra la pregunta y convierte la respuesta con int.
            rondas = int(input("¿Cuántas rondas quieres ejecutar? N = "))
            # Comprueba que N sea mayor que cero.
            if rondas > 0:
                # Devuelve el valor válido y termina las preguntas.
                return rondas
        # Captura entradas como letras, vacío o números decimales no aceptados por int.
        except ValueError:
            # Continúa para mostrar la explicación y repetir la pregunta.
            pass
        # Explica el formato aceptado después de una entrada inválida.
        print("Ingresa un número entero mayor que cero, por ejemplo 5 o 20.")


# Punto de entrada que lee la configuración y arranca el coordinador.
def main():
    # Crea la ayuda general del programa.
    parser = argparse.ArgumentParser(description="Competencia Retroceso contra Voraz")
    # Define N como entero opcional; omitirlo deja None para activar la pregunta interactiva.
    parser.add_argument("--rondas", type=int, help="N rondas; si se omite, se pregunta al iniciar")
    # Define la dirección del servidor; por defecto busca en esta misma computadora.
    parser.add_argument("--host", default="127.0.0.1")
    # Define el puerto TCP; por defecto coincide con el 4000 del servidor Java.
    parser.add_argument("--puerto", type=int, default=4000)
    # Permite elegir la carpeta de resultados mediante una ruta.
    parser.add_argument("--salida", type=Path)
    # Configura el límite de espera de mensajes/conexión; no es la cantidad de rondas.
    parser.add_argument("--timeout", type=float, default=30)
    # Procesa los argumentos de la terminal.
    args = parser.parse_args()
    # Comprueba que el tiempo de espera sea positivo.
    if args.timeout <= 0:
        # Muestra un error de argumentos y sale si timeout no es válido.
        parser.error("timeout debe ser positivo")
    # Comprueba si falta N en la línea de comandos.
    if args.rondas is None:
        # Permite manejar fin de entrada y Ctrl+C durante la pregunta.
        try:
            # Obtiene N mediante la función interactiva.
            args.rondas = solicitar_rondas()
        # Detecta que terminó la entrada sin poder recibir una cantidad.
        except EOFError:
            # Indica cómo proporcionar N sin interacción, por ejemplo en una ejecución automatizada.
            parser.error("No se recibió N. Indica la cantidad con --rondas N")
        # Detecta la interrupción manual con Ctrl+C antes de iniciar la competencia.
        except KeyboardInterrupt:
            # Informa que no llegó a comenzar la ejecución.
            print("\nEjecución cancelada antes de iniciar la competencia.")
            # Devuelve el código convencional de interrupción 130.
            return 130
    # Valida también los enteros recibidos directamente por --rondas.
    if args.rondas < 1:
        # Rechaza cero o números negativos.
        parser.error("rondas debe ser un entero mayor que cero")
    # Importa la exportación y la comprobación de dependencias del reporte.
    from reporte import exportar, verificar_dependencias
    # Comprueba Node y la biblioteca de Excel antes de comenzar las rondas.
    verificar_dependencias()
    # Importa fecha y hora para generar una carpeta de ejecución identificable.
    from datetime import datetime
    # Usa la salida indicada o genera una carpeta con fecha, hora y microsegundos.
    salida = args.salida or BASE / "resultados" / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    # Permite informar fallos de ejecución conservando los JSON ya guardados.
    try:
        # Crea el coordinador con la configuración y le entrega la función de exportación.
        Coordinador(args.host, args.puerto, salida.resolve(), args.rondas, args.timeout).ejecutar(exportar)
    # Captura errores operativos de conexión, clientes o generación del Excel.
    except Exception as error:
        # Escribe el motivo en la salida de errores y recuerda que los JSON anteriores se conservan.
        print(f"Competencia detenida: {error}. Los JSON ya guardados se conservan.", file=sys.stderr)
        # Devuelve un código distinto de cero para señalar que hubo un problema.
        return 1
    # Muestra la ruta absoluta del Excel cuando la competencia termina correctamente.
    print(f"Excel: {salida.resolve() / 'resultados.xlsx'}")
    # Devuelve cero para indicar finalización normal.
    return 0


# Ejecuta main solo cuando este archivo se inicia directamente.
if __name__ == "__main__":
    # Transfiere al sistema operativo el código de salida devuelto por main.
    sys.exit(main())


