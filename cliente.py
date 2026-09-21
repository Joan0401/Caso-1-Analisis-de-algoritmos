"""Infraestructura compartida; cada programa conserva sus decisiones y memoria."""
# Importa el lector de opciones de la línea de comandos.
import argparse
# Importa la conversión entre diccionarios de Python y texto JSON.
import json
# Importa Path para construir rutas sin concatenar separadores manualmente.
from pathlib import Path
# Importa una cola segura para comunicar el hilo receptor con el algoritmo.
from queue import Queue
# Da acceso a la entrada estándar, conectada al coordinador.
import sys
# Event representa la señal de parada; Thread permite escuchar mensajes en segundo plano.
from threading import Event, Thread
# Importa la interrupción normal de ronda y el objeto que mide el algoritmo.
from metricas import FinRonda, Metricas


# Encapsula el canal JSON de un programa independiente con el coordinador.
class Canal:
    # Inicializa la cola y el hilo receptor al crear el canal.
    def __init__(self):
        # Crea una cola vacía y una señal de finalización inicialmente desactivada.
        self.entrada, self.fin = Queue(), Event()
        # Escucha en un hilo de fondo; daemon permite que ese hilo no impida salir del proceso.
        Thread(target=self.leer, daemon=True).start()

    # Lee continuamente los mensajes enviados por el coordinador.
    def leer(self):
        # Asegura la señal de parada incluso si se cierra o falla la lectura.
        try:
            # Lee una línea completa cada vez; cada línea debe contener un mensaje JSON.
            for linea in sys.stdin:
                # Convierte el texto recibido en un diccionario.
                mensaje = json.loads(linea)
                # Reconoce el cierre de una ronda o la salida de toda la competencia.
                if mensaje["tipo"] in ("FIN", "SALIR"):
                    # Activa la parada para que el algoritmo la detecte en su próximo punto instrumentado.
                    self.fin.set()
                # Entrega también el mensaje completo a quien esté esperando una respuesta.
                self.entrada.put(mensaje)
        # Ejecuta la limpieza siempre que termina la lectura, con o sin error.
        finally:
            # Impide que la búsqueda siga al perder su canal de control.
            self.fin.set()
            # Desbloquea una espera en la cola con una orden de salida.
            self.entrada.put({"tipo": "SALIR"})

    # Envía un diccionario al coordinador mediante la salida estándar del proceso.
    def enviar(self, mensaje):
        # Escribe JSON y salto de línea; flush evita retrasos por el búfer de salida.
        print(json.dumps(mensaje, ensure_ascii=True), flush=True)

    # Punto de interrupción cooperativa usado antes de consultar o registrar una operación.
    def comprobar(self):
        # Comprueba si el hilo receptor ya activó la señal de finalización.
        if self.fin.is_set():
            # Lanza la excepción que termina la búsqueda y permite guardar las métricas.
            raise FinRonda()

    # Envía una contraseña y espera una respuesta; no decide qué contraseña probar.
    def consultar(self, intento):
        # Evita iniciar otra solicitud si ya recibió la señal de cierre.
        self.comprobar()
        # Asigna un número secuencial a esta solicitud del cliente.
        self.numero += 1
        # Envía el tipo de mensaje y la ronda a la que pertenece.
        self.enviar({"tipo": "INTENTO", "ronda": self.ronda,
                     # Agrega su identificador y la contraseña propuesta; el coordinador decidirá si llega a TCP.
                     "id": self.numero, "password": intento})
        # Espera un mensaje sin consumir CPU en un bucle de sondeo continuo.
        mensaje = self.entrada.get()
        # Reconoce que la respuesta del coordinador cierra la ronda.
        if mensaje["tipo"] == "FIN":
            # Guarda el cierre completo para usar su instante, ganador e intentos enviados.
            self.cierre = mensaje
            # Interrumpe la recursión o los bucles del algoritmo y vuelve al código de guardado.
            raise FinRonda()
        # Reconoce una orden de abandonar el proceso completo.
        if mensaje["tipo"] == "SALIR":
            # Sale con código 1 porque no puede continuar esa consulta.
            raise SystemExit(1)
        # Exige una respuesta con el mismo identificador para no mezclar solicitudes.
        if mensaje["tipo"] != "RESPUESTA" or mensaje["id"] != self.numero:
            # Informa un fallo de protocolo cuando el mensaje no corresponde al intento.
            raise RuntimeError("Respuesta fuera de orden")
        # Devuelve al algoritmo solamente la respuesta del servidor, normalmente FAIL.
        return mensaje["respuesta"]


# Ejecuta cualquier clase de algoritmo compatible dentro de su propio proceso.
def ejecutar_cliente(nombre, clase):
    # Crea el lector de argumentos y muestra el nombre de este cliente en la ayuda.
    parser = argparse.ArgumentParser(description=f"Cliente independiente {nombre}")
    # Define un indicador booleano para el modo administrado por el coordinador.
    parser.add_argument("--controlado", action="store_true",
                        # Explica en la ayuda quién proporciona los canales de entrada y salida.
                        help="Lo inicia competir.py con su canal de coordinación")
    # Define la carpeta donde este proceso guardará sus propios JSON.
    parser.add_argument("--salida", type=Path, default=Path("resultados"))
    # Lee y valida los argumentos usados al iniciar el script.
    args = parser.parse_args()
    # Comprueba que se inició mediante el mecanismo de coordinación esperado.
    if not args.controlado:
        # Muestra cómo arrancar ambos programas y sale si falta el canal administrado.
        parser.error("Ejecute python competir.py --rondas 10; inicia ambos programas independientes")
    # Crea el canal y activa su hilo receptor.
    canal = Canal()
    # Notifica que este proceso está listo para recibir la primera ronda.
    canal.enviar({"tipo": "LISTO", "algoritmo": nombre})
    # Espera sucesivas rondas hasta que el coordinador ordene salir.
    while True:
        # Recibe la siguiente orden de inicio o salida.
        inicio = canal.entrada.get()
        # Reconoce el cierre de toda la competencia mientras espera una ronda.
        if inicio["tipo"] == "SALIR":
            # Finaliza normalmente la función y el proceso cliente.
            return
        # Verifica que cualquier otra orden recibida aquí sea INICIO.
        if inicio["tipo"] != "INICIO":
            # Interrumpe ante un mensaje inesperado para no mezclar estados de rondas.
            raise RuntimeError("Se esperaba INICIO")
        # Desactiva la señal de la ronda anterior para permitir la nueva búsqueda.
        canal.fin.clear()
        # Guarda la ronda actual, reinicia el número de solicitudes y descarta el cierre anterior.
        canal.ronda, canal.numero, canal.cierre = inicio["ronda"], 0, None
        # Crea métricas independientes con una función que comprueba la señal FIN.
        metricas = Metricas(canal.comprobar)
        # Distingue la terminación normal por FIN de los errores del algoritmo.
        try:
            # Crea una instancia nueva del algoritmo, le pasa canal y métricas, y comienza a buscar.
            clase(canal.consultar, metricas).ejecutar()
        # Captura la excepción usada para finalizar la búsqueda al primer acierto de la competencia.
        except FinRonda:
            # No la trata como error; continúa con el guardado de la ronda.
            pass
        # Captura otras excepciones como errores reales de esta ejecución.
        except Exception as error:
            # Comunica al coordinador una representación del error para detener la competencia.
            canal.enviar({"tipo": "ERROR", "mensaje": repr(error)})
            # Sale del cliente porque no puede continuar con un estado posiblemente incoherente.
            return
        # Recupera el cierre si consultar ya lo recibió antes de lanzar FinRonda.
        cierre = canal.cierre
        # Si solo se detectó la señal, todavía necesita leer el mensaje FIN completo.
        while cierre is None:
            # Espera mensajes pendientes hasta encontrar ese cierre.
            mensaje = canal.entrada.get()
            # Permite salir si el coordinador termina mientras esperaba FIN.
            if mensaje["tipo"] == "SALIR":
                # Finaliza el cliente sin fabricar métricas de una ronda no cerrada.
                return
            # Identifica el mensaje que contiene la frontera temporal de la ronda.
            if mensaje["tipo"] == "FIN":
                # Conserva sus datos para salir del bucle de espera.
                cierre = mensaje
        # Reconstruye únicamente las métricas hasta el instante de corte, excluyendo trabajo tardío.
        datos = metricas.congelar(cierre["corte"])
        # Agrega al informe la identidad del algoritmo y la ronda.
        datos.update({"ronda": canal.ronda, "algoritmo": nombre,
                      # Marca ÉXITO al ganador; el competidor interrumpido se marca INCONCLUSO.
                      "resultado": "ÉXITO" if cierre["ganador"] == nombre else "INCONCLUSO",
                      # Guarda quién ganó y el instante de inicio compartido por ambos.
                      "ganador": cierre["ganador"], "inicio": inicio["inicio"],
                      # Guarda el corte común y las solicitudes creadas, incluidas las que pudieron cancelarse.
                      "corte": cierre["corte"], "solicitudes": canal.numero,
                      # Conserva las consultas que el coordinador confirma que realmente llegaron al servidor.
                      "intentos": cierre["intentos"],
                      # Resta nanosegundos y divide entre un millón para obtener milisegundos.
                      "duracion_ms": (cierre["corte"] - inicio["inicio"]) / 1e6})
        # Cada PROGRAMA guarda sus propias métricas antes de confirmar el cierre.
        # Crea la carpeta si hace falta; acepta que el coordinador ya la haya creado.
        args.salida.mkdir(parents=True, exist_ok=True)
        # Forma un nombre por algoritmo y ronda; 04d rellena la ronda con ceros hasta cuatro dígitos.
        destino = args.salida / f"{nombre}_ronda_{canal.ronda:04d}.json"
        # Elige una ruta temporal para no dejar el JSON final a medio escribir.
        temporal = destino.with_suffix(".tmp")
        # Serializa las métricas con sangría y caracteres españoles en UTF-8.
        temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
        # Reemplaza el archivo final con el temporal ya escrito; no cambia su contenido.
        temporal.replace(destino)
        # Notifica que este cliente ya guardó su ronda.
        canal.enviar({"tipo": "GUARDADO", "ronda": canal.ronda,
                      # Incluye la ruta absoluta del archivo para identificar el resultado persistido.
                      "archivo": str(destino.resolve())})
