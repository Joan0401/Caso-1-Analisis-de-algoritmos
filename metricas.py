"""Contadores del algoritmo; no incluyen instrucciones internas de Python o Java."""
# Importa un diccionario contador: las claves nuevas comienzan automáticamente en cero.
from collections import Counter
# Importa el reloj monotónico de alta resolución expresado en nanosegundos.
from time import perf_counter_ns


# Define una excepción propia para abandonar normalmente la búsqueda al cerrar la ronda.
class FinRonda(Exception):
    """Interrupción cooperativa al terminar la ronda."""


# Agrupa el registro de eventos y la reconstrucción de las métricas al cierre.
class Metricas:
    # Recibe una función para detectar FIN; por defecto usa una función que no hace nada.
    def __init__(self, comprobar=lambda: None):
        # Guarda esa función sin ejecutarla todavía.
        self.comprobar = comprobar
        # Prepara el historial cronológico de eventos de esta ronda.
        self.eventos = []
        # Inicializa la numeración de activaciones de bucles.
        self.siguiente_bucle = 0

    # Recibe un tipo y campos adicionales; **datos reúne esos argumentos en un diccionario.
    def registrar(self, tipo, **datos):
        # Comprueba si debe detenerse antes de registrar otra operación del algoritmo.
        self.comprobar()
        # Guarda instante, tipo y campos; **datos incorpora esos campos al nuevo diccionario.
        self.eventos.append({"t": perf_counter_ns(), "tipo": tipo, **datos})

    # Ofrece un atajo para contar una operación; si no se indica cantidad, suma uno.
    def contar(self, nombre, cantidad=1):
        # Registra un incremento que se acumulará al congelar el historial.
        self.registrar("contador", nombre=nombre, cantidad=cantidad)

    # Recibe el punto de avance; los valores por defecto representan una búsqueda sin asignación.
    def estado(self, fase, asignacion="", avance=0):
        # Guarda fase, cadena parcial y número de posiciones de avance en un evento.
        self.registrar("estado", fase=fase, asignacion=asignacion, avance=avance)

    # Generador que sustituye al recorrido directo y mide activaciones e iteraciones.
    def recorrer(self, nombre, elementos):
        """Registra una activación, su universo y cada iteración efectivamente iniciada.

        La copia permite conocer los elementos disponibles aunque haya break.
        Los bucles de infraestructura y reporte no son bucles de búsqueda.
        """
        # Toma una copia inmutable de los elementos para conocer cuántos había al entrar al bucle.
        elementos = tuple(elementos)
        # Reserva un identificador nuevo para esta activación concreta.
        self.siguiente_bucle += 1
        # Mantiene el identificador local mientras este generador está suspendido entre iteraciones.
        identificador = self.siguiente_bucle
        # Registra la entrada al bucle y el tamaño de su conjunto de elementos disponibles.
        self.registrar("bucle", id=identificador, nombre=nombre, disponibles=len(elementos))
        # Recorre la copia de los elementos, uno por uno.
        for elemento in elementos:
            # Cuenta la vuelta que está por entregarse al algoritmo.
            self.registrar("iteracion", id=identificador)
            # Entrega un elemento y suspende el generador hasta la siguiente vuelta del bucle consumidor.
            yield elemento

    # Reconstruye las métricas que pertenecen al instante común de cierre.
    def congelar(self, cierre):
        """Incluye solo eventos instrumentados hasta el instante común de cierre.

        El mensaje FIN puede llegar tarde; sus eventos posteriores se excluyen.
        No se afirma medir instrucciones que no están instrumentadas.
        """
        # Inicializa contadores por nombre y un diccionario por identificador de activación.
        contadores, bucles = Counter(), {}
        # Define el estado inicial por si no llegó a registrarse ningún avance antes del corte.
        estado = {"fase": "inicio", "asignacion": "", "avance": 0}
        # Inicializa el máximo avance observado y los eventos válidos que se conservarán.
        maximo, eventos = 0, []
        # Examina los eventos en el mismo orden cronológico en que se registraron.
        for evento in self.eventos:
            # Detecta el primer evento posterior al corte definido por el coordinador.
            if evento["t"] > cierre:
                # Deja de recorrer: los eventos restantes también son posteriores al corte.
                break
            # Conserva este evento porque ocurrió antes o exactamente en el corte.
            eventos.append(evento)
            # Obtiene su categoría para decidir cómo acumularlo.
            tipo = evento["tipo"]
            # Distingue la entrada a una nueva activación de un bucle.
            if tipo == "bucle":
                # Copia sus datos y agrega un contador de visitas inicialmente en cero.
                bucles[evento["id"]] = {**evento, "visitados": 0}
            # Distingue una vuelta del bucle ya registrado.
            elif tipo == "iteracion":
                # Suma una visita a la activación correspondiente.
                bucles[evento["id"]]["visitados"] += 1
            # Distingue un incremento de una operación específica, como comparar o podar.
            elif tipo == "contador":
                # Acumula el incremento bajo el nombre de esa operación.
                contadores[evento["nombre"]] += evento["cantidad"]
            # Distingue un punto de control de fase y avance.
            elif tipo == "estado":
                # Conserva solamente los campos de estado; reemplaza el punto de control anterior.
                estado = {k: evento[k] for k in ("fase", "asignacion", "avance")}
                # Actualiza el mayor avance registrado, aunque después el retroceso haya vuelto atrás.
                maximo = max(maximo, estado["avance"])
        # Devuelve contadores normales y una lista de las activaciones reconstruidas.
        return {"contadores": dict(contadores), "bucles": list(bucles.values()),
                # Suma las visitas de todas las activaciones para obtener las iteraciones globales.
                "iteraciones": sum(b["visitados"] for b in bucles.values()),
                # Incluye cuántas activaciones hubo y el máximo avance observado.
                "total_bucles": len(bucles), "avance_maximo": maximo,
                # Incluye el último estado y los eventos que permiten auditar el resultado.
                "estado": estado, "eventos": eventos}


# Calcula la distancia de edición entre dos cadenas y registra sus comparaciones.
def distancia(a, b, metricas):
    """Levenshtein: O(len(a)*len(b)) tiempo, O(len(b)) espacio auxiliar."""
    # Primera fila: transformar una cadena vacía en los prefijos de b cuesta 0,1,2,... inserciones.
    anterior = list(range(len(b) + 1))
    # Recorre los prefijos no vacíos de a; cada i representa una fila de la tabla.
    for i in metricas.recorrer("levenshtein_filas", range(1, len(a) + 1)):
        # Primera columna: convertir el prefijo de a de longitud i en vacío cuesta i borrados.
        actual = [i]
        # Recorre los prefijos no vacíos de b para completar las columnas de esta fila.
        for j in metricas.recorrer("levenshtein_columnas", range(1, len(b) + 1)):
            # Cuenta la comparación entre el carácter de a y el de b.
            metricas.contar("comparaciones_caracteres")
            # El costo es cero si son iguales y uno si hay que sustituir el carácter.
            costo = int(a[i - 1] != b[j - 1])
            # Elige el menor costo entre borrar, insertar o sustituir/conservar y lo agrega a la fila.
            actual.append(min(anterior[j] + 1, actual[j - 1] + 1, anterior[j - 1] + costo))
        # La fila calculada será la anterior para la siguiente iteración; no conserva toda la matriz.
        anterior = actual
    # Devuelve la última celda, que compara las dos cadenas completas.
    return anterior[-1]
