"""PROGRAMA 1: Retroceso, retroceso con multiconjunto, restricciones y MRV.

A=alfabeto, M=longitud máxima, L=longitud descubierta, D=letras presentes.
P=L!/producto(n_c!), K<=A+P restricciones; consultas <=A+P (aquí <=50).
Nodos O(L*P). Un nodo prueba O(L*D) asignaciones para construir dominios;
cada prueba cuesta O(K*L). Cota conservadora de trabajo local:
O(A*M + P*K*D*L^3 + P*K*L*M). Crecimiento factorial en el peor caso
cuando las letras son distintas; K también puede crecer con P.
Espacio auxiliar O(K*M + L^2*D + A), sin historial de métricas O(E).
E=eventos instrumentados. Comunicación y reportes: ver EXPLICACION.md.
"""
# Importa la función de Levenshtein que usará para filtrar contraseñas completas.
from metricas import distancia


# Agrupa el estado y los métodos del algoritmo de retroceso en una clase.
class Retroceso:
    # Constructor: recibe la función de consulta, las métricas, las letras y la longitud máxima.
    def __init__(self, consultar, metricas, alfabeto="abcdefghijklmnopqrstuvwxyz", maximo=4):
        # Guarda consultar como función invocable y abrevia el objeto de métricas como self.m.
        self.consultar, self.m = consultar, metricas
        # Conserva los límites del problema; self indica que los datos pertenecen a esta instancia.
        self.alfabeto, self.maximo = alfabeto, maximo
        # Crea restricciones conocidas, cantidades de letras restantes y posiciones de la contraseña.
        self.restricciones, self.restantes, self.casillas = [], {}, []

    # Punto de entrada del algoritmo para una sola ronda.
    def ejecutar(self):
        # Inicializa la suma de apariciones que permitirá deducir la longitud del secreto.
        longitud = 0
        # PREPARACIÓN: cada sondeo uniforme cuenta las apariciones de una letra.
        # Recorre todas las letras y registra las vueltas del bucle de sondeos iniciales.
        for letra in self.m.recorrer("sondeos_uniformes_Retroceso", self.alfabeto):
            # Repite la letra M veces: por ejemplo, 'a' * 4 produce 'aaaa'.
            intento = letra * self.maximo
            # Registra que está obteniendo información y cuál es el sondeo actual.
            self.m.estado("sondeo", intento)
            # Consulta el servidor a través del canal; un acierto o cierre interrumpe mediante FinRonda.
            respuesta = self.consultar(intento)
            # En un sondeo uniforme, las coincidencias posicionales equivalen a apariciones de esa letra.
            cantidad = respuesta["matchedLetters"]
            # Cada posición del secreto contribuye una vez a la suma; al terminar, la suma es L.
            longitud += cantidad
            # Comprueba si la letra aparece al menos una vez; cero se interpreta como falso.
            if cantidad:
                # Guarda solamente las letras presentes y cuántas veces habrá que colocarlas.
                self.restantes[letra] = cantidad
            # Conserva el intento y sus pistas para comprobar asignaciones futuras.
            self.restricciones.append((intento, cantidad, respuesta["distance"]))
        # Comprueba que la longitud deducida respete los límites del servidor.
        if not 2 <= longitud <= self.maximo:
            # Detiene la ejecución ante datos incoherentes, en vez de buscar con información inválida.
            raise RuntimeError("Longitud incoherente: posible cambio externo de contraseña")
        # Crea L posiciones vacías; None representa una posición todavía sin asignar.
        self.casillas = [None] * longitud
        # Inicia la búsqueda recursiva con cero posiciones asignadas.
        self.buscar(0)
        # Llegar aquí sin interrupción por SUCCESS significa que se agotaron las opciones sin solución.
        raise RuntimeError("Se agotó el árbol sin SUCCESS; revisar protocolo y ronda")

    # Comprueba si la asignación parcial todavía puede satisfacer todas las pistas posicionales.
    def compatible(self):
        """PODA: fijas <= coincidencias_reales <= fijas+posibles.

        'posibles' es una sobreestimación segura: puede contar posiciones que
        compiten por una misma aparición. Debilita la poda, no la invalida.
        Las cantidades se respetan al decrementar restantes.
        """
        # Recorre las restricciones; objetivo es matchedLetters y el guion bajo ignora la distancia aquí.
        for intento, objetivo, _ in self.m.recorrer("restricciones_posicionales", self.restricciones):
            # Reinicia las coincidencias obligatorias y las adicionales potencialmente alcanzables.
            fijas = posibles = 0
            # Examina solo posiciones que existen tanto en el intento anterior como en la contraseña.
            for i in self.m.recorrer("posiciones_restriccion", range(min(len(intento), len(self.casillas)))):
                # Distingue una posición pendiente de una ya fijada.
                if self.casillas[i] is None:
                    # Suma una coincidencia potencial si queda esa letra; get devuelve cero si no está presente.
                    posibles += int(self.restantes.get(intento[i], 0) > 0)
                # Procesa el caso en que la posición ya tiene una letra asignada.
                else:
                    # Registra una comparación explícita de caracteres para el reporte.
                    self.m.contar("comparaciones_caracteres")
                    # Suma uno si coincide; int convierte True en 1 y False en 0.
                    fijas += int(self.casillas[i] == intento[i])
            # PODA: rechaza si sobran coincidencias fijas o si ni la cota superior alcanza el objetivo.
            if fijas > objetivo or fijas + posibles < objetivo:
                # Cuenta el rechazo por una restricción posicional imposible.
                self.m.contar("podas_restricciones")
                # Devuelve falso: no se debe continuar explorando esta asignación.
                return False
        # Devuelve verdadero si ninguna restricción demostró que la rama es imposible; no prueba que sea solución.
        return True

    # Construye el dominio: lista de letras admisibles para cada posición aún libre.
    def dominios(self):
        """Forward checking: probar letras disponibles para cada posición libre."""
        # Crea un diccionario cuya clave será la posición y cuyo valor serán sus opciones.
        dominios = {}
        # Recorre los índices de la contraseña para calcular las opciones de cada hueco.
        for i in self.m.recorrer("posiciones_dominios", range(len(self.casillas))):
            # Detecta posiciones que ya están ocupadas en la rama actual.
            if self.casillas[i] is not None:
                # Salta a la siguiente posición; no modifica decisiones de niveles anteriores.
                continue
            # Prepara una lista de opciones para esta posición concreta.
            opciones = []
            # Prueba las letras presentes en el multiconjunto, registrando cada visita.
            for letra in self.m.recorrer("letras_dominios", self.restantes):
                # Comprueba si ya se consumieron todas las apariciones de esta letra.
                if self.restantes[letra] == 0:
                    # Registra la poda por cantidad agotada.
                    self.m.contar("podas_cantidad")
                    # Descarta esta letra y examina la siguiente.
                    continue
                # Coloca temporalmente la letra para evaluar su compatibilidad.
                self.casillas[i] = letra
                # Consume una aparición durante esta prueba temporal.
                self.restantes[letra] -= 1
                # Garantiza que se ejecute la restauración posterior aunque haya una interrupción.
                try:
                    # Comprueba todas las restricciones con la letra provisionalmente colocada.
                    if self.compatible():
                        # Incluye la letra en el dominio si no se demuestra que sea imposible.
                        opciones.append(letra)
                # Se ejecuta siempre al salir de la prueba, tanto normalmente como por excepción.
                finally:
                    # Devuelve la aparición que se consumió temporalmente.
                    self.restantes[letra] += 1
                    # Vuelve a dejar vacía la posición; calcular dominios no toma la decisión definitiva.
                    self.casillas[i] = None
            # PODA: una posición sin opciones impide completar esta rama.
            # Comprueba si ninguna letra resultó admisible para este hueco.
            if not opciones:
                # Cuenta la poda que descarta toda la rama por un dominio vacío.
                self.m.contar("podas_dominio_vacio")
                # Usa None para comunicar a buscar que esta rama no puede completarse.
                return None
            # Asocia el índice de la posición con las letras que sí pueden probarse.
            dominios[i] = opciones
        # Devuelve todos los dominios si cada posición libre conserva alguna opción.
        return dominios

    # Explora una rama; profundidad indica cuántas posiciones se han asignado.
    def buscar(self, profundidad):
        # Cuenta esta llamada recursiva como un nodo del árbol de búsqueda.
        self.m.contar("nodos")
        # Guarda un punto de control; join forma la cadena y sustituye cada hueco por '_'.
        self.m.estado("retroceso", "".join(c or "_" for c in self.casillas), profundidad)
        # Revalida la rama usando incluso las pistas recibidas durante la exploración anterior.
        if not self.compatible():
            # Abandona esta llamada sin explorar hijos si la asignación es incompatible.
            return
        # Comprueba si todas las posiciones tienen letra: se alcanzó una hoja.
        if profundidad == len(self.casillas):
            # Une las letras de la lista para producir una contraseña completa.
            candidato = "".join(self.casillas)
            # FILTRO de hoja: las distancias también deben coincidir exactamente.
            # Recorre las distancias conocidas; aquí no utiliza el campo de coincidencias.
            for previo, _, objetivo in self.m.recorrer("distancias_hoja", self.restricciones):
                # Descarta el candidato si su distancia frente a un intento no coincide con la respuesta real.
                if distancia(candidato, previo, self.m) != objetivo:
                    # Cuenta este filtro de una hoja completa, diferente de podar una asignación parcial.
                    self.m.contar("hojas_descartadas_distancia")
                    # Termina esta hoja sin enviar una consulta que ya se sabe incompatible.
                    return
            # Envía la contraseña compatible; si hay SUCCESS, el canal interrumpe la búsqueda.
            respuesta = self.consultar(candidato)
            # Si volvió una respuesta FAIL, la incorpora como una restricción adicional.
            self.restricciones.append((candidato, respuesta["matchedLetters"], respuesta["distance"]))
            # Termina la hoja y devuelve el control a la llamada anterior para probar otra opción.
            return
        # Calcula las letras posibles de las posiciones todavía libres.
        dominios = self.dominios()
        # Reconoce la señal de que una posición quedó sin opciones.
        if dominios is None:
            # Abandona la rama porque ya no admite ninguna solución.
            return
        # MRV: posición con MENOS letras posibles; empate por menor índice.
        # Todavía no hay una posición elegida para la siguiente decisión.
        posicion = None
        # Recorre los índices disponibles para aplicar la heurística MRV.
        for i in self.m.recorrer("seleccion_MRV", dominios):
            # Elige el primer índice o uno con menos opciones; en empate conserva el anterior.
            if posicion is None or len(dominios[i]) < len(dominios[posicion]):
                # Actualiza la posición que se resolverá a continuación.
                posicion = i
        # Explora una por una las letras del dominio de la posición seleccionada.
        for letra in self.m.recorrer("ramas_retroceso", dominios[posicion]):
            # ELECCIÓN: coloca una letra en la asignación que explorará la llamada hija.
            self.casillas[posicion] = letra           # ELEGIR
            # Reduce el inventario para que los descendientes no reutilicen esa aparición.
            self.restantes[letra] -= 1
            # Asegura la restauración del estado incluso si se recibe FIN durante la recursión.
            try:
                # EXPLORACIÓN: resuelve recursivamente otra posición con una casilla adicional asignada.
                self.buscar(profundidad + 1)         # EXPLORAR
            # Al regresar o interrumpirse la llamada hija, restaura siempre la decisión de este nivel.
            finally:
                # RETROCESO: devuelve al inventario la aparición utilizada.
                self.restantes[letra] += 1           # DESHACER: retroceso real
                # RETROCESO: vacía la posición para poder intentar la siguiente letra del dominio.
                self.casillas[posicion] = None
            # Cada hijo revalida todas las restricciones, incluidas las nuevas.


# Solo inicia un cliente si este archivo se ejecuta directamente, no cuando se importa.
if __name__ == "__main__":
    # Importa la infraestructura común que administra mensajes, rondas y guardado.
    from cliente import ejecutar_cliente
    # Inicia el proceso con el nombre Retroceso y proporciona su clase de búsqueda.
    ejecutar_cliente("Retroceso", Retroceso)

