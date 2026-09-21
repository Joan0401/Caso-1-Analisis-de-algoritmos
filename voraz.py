"""PROGRAMA 2: Voraz, fijación irreversible de posiciones.

A=alfabeto, M=longitud máxima, L=longitud descubierta.
Consultas <= A+1+L*(A-1): <=127 aquí. O(A*M) consultas.
CPU local O(A*M^2) por construcción/copia/serialización de cadenas.
Memoria auxiliar O(A+M), excluyendo historial O(E). Crecimiento polinómico.
Servidor: O(M^2) por FAIL, O(A*M^3) asociado en total (medida separada).
Las etapas NO retroceden: cada posición aceptada queda fija para siempre.
"""


# Define la clase del algoritmo voraz; cada instancia trabaja en una sola ronda.
class Voraz:
    # Recibe la función de consulta, el registrador y los límites del alfabeto y longitud.
    def __init__(self, consultar, metricas, alfabeto="abcdefghijklmnopqrstuvwxyz", maximo=4):
        # Guarda el canal de consulta y el objeto de métricas en esta instancia.
        self.consultar, self.m = consultar, metricas
        # Conserva las letras permitidas y la longitud máxima que cubren los sondeos.
        self.alfabeto, self.maximo = alfabeto, maximo

    # Ejecuta la preparación y después las etapas voraces.
    def ejecutar(self):
        # Inicializa la longitud y el espacio donde reutilizará la respuesta del sondeo de 'a'.
        longitud, respuesta_a = 0, None
        # PREPARACIÓN, no decisión voraz: suma de frecuencias = longitud.
        # Recorre el alfabeto completo y cuenta las iteraciones de adquisición de información.
        for letra in self.m.recorrer("sondeos_uniformes_Voraz", self.alfabeto):
            # Registra el sondeo uniforme que está por enviar.
            self.m.estado("sondeo", letra * self.maximo)
            # Consulta M repeticiones de la letra; SUCCESS provoca la interrupción de la ronda.
            respuesta = self.consultar(letra * self.maximo)
            # Suma sus coincidencias: cada posición del secreto se cuenta una vez al terminar los sondeos.
            longitud += respuesta["matchedLetters"]
            # Identifica el sondeo de la primera letra del alfabeto, normalmente 'a'.
            if letra == self.alfabeto[0]:
                # Conserva esa respuesta para evitar repetir la consulta de base cuando L=M.
                respuesta_a = respuesta
        # Rechaza una longitud fuera de los límites permitidos.
        if not 2 <= longitud <= self.maximo:
            # Informa una incoherencia de protocolo o de ronda y detiene el algoritmo.
            raise RuntimeError("Longitud incoherente: posible cambio externo de contraseña")
        # Crea una base editable de L letras 'a'; una lista permite cambiar una posición.
        base = [self.alfabeto[0]] * longitud
        # Registra la cadena base uniendo sus letras con join.
        self.m.estado("base_voraz", "".join(base))
        # Comprueba si la base es idéntica al sondeo uniforme inicial de longitud M.
        if longitud == self.maximo:
            # Reutiliza las coincidencias de ese sondeo como referencia inicial.
            referencia = respuesta_a["matchedLetters"]
        # Si la base tiene otra longitud, el resultado previo no corresponde a la misma consulta.
        else:
            # Consulta la base de longitud L y obtiene sus coincidencias como referencia.
            referencia = self.consultar("".join(base))["matchedLetters"]
        # ETAPAS VORACES: resolver las posiciones de izquierda a derecha.
        # Cada vuelta es una ETAPA: resolver una posición de izquierda a derecha.
        for i in self.m.recorrer("posiciones_voraces", range(longitud)):
            # Registra la posición que está resolviendo y cuántas anteriores quedaron fijadas.
            self.m.estado("posicion_voraz", "".join(base), i)
            # Recuerda la letra de esta posición en la base aceptada.
            original = base[i]
            # Examina las letras del alfabeto como sustituciones posibles para esta posición.
            for letra in self.m.recorrer("letras_voraces", self.alfabeto):
                # Cuenta la comparación entre la letra propuesta y la original.
                self.m.contar("comparaciones_caracteres")
                # Comprueba si la propuesta mantendría exactamente la letra original.
                if letra == original:
                    # Evita repetir esa consulta; pasa a la siguiente letra.
                    continue
                # Copia la base para probar una sustitución sin alterar las decisiones aceptadas.
                candidato = base.copy()
                # Cambia únicamente la posición i en la copia.
                candidato[i] = letra
                # Consulta esa cadena; todas las demás posiciones son iguales a la base.
                respuesta = self.consultar("".join(candidato))
                # Cuenta una comparación numérica entre el nuevo matchedLetters y la referencia.
                self.m.contar("comparaciones_puntaje_posicional")
                # ÓPTIMO LOCAL: una mejora alcanza contribución 1 en esta posición.
                # Solo cambia i; la mejora prueba que esta letra es correcta.
                # Una mejora implica que la letra de i es correcta: su contribución pasa de 0 a 1.
                if respuesta["matchedLetters"] > referencia:
                    # Acepta la sustitución como nueva base; los empates y empeoramientos no llegan aquí.
                    base = candidato
                    # Actualiza las coincidencias de referencia para la siguiente etapa.
                    referencia = respuesta["matchedLetters"]
                    # Termina las pruebas de esta posición: ya alcanzó su óptimo local y no volverá atrás.
                    break  # DECISIÓN IRREVERSIBLE; no se vuelve a la posición i.
            # Sin mejora: la letra original era correcta (se probaron todas).
            # Registra i+1 posiciones resueltas; sin mejora, la letra original ya era correcta.
            self.m.estado("posicion_fijada", "".join(base), i + 1)
        # Si termina sin recibir SUCCESS, informa un error en vez de inventar un acierto.
        raise RuntimeError("Terminó Voraz sin SUCCESS; revisar protocolo y ronda")


# Ejecuta el arranque solo al iniciar este archivo como programa principal.
if __name__ == "__main__":
    # Importa la infraestructura de rondas, comunicación y métricas individuales.
    from cliente import ejecutar_cliente
    # Arranca un cliente independiente llamado Voraz, utilizando esta clase.
    ejecutar_cliente("Voraz", Voraz)

