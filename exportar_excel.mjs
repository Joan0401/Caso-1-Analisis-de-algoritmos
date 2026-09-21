// Solo presentación/exportación. Ninguna decisión de los algoritmos vive aquí.
// Importa operaciones de archivos asíncronas; await esperará a que finalicen.
import fs from 'node:fs/promises';
// Importa utilidades para construir rutas de archivos del sistema operativo.
import path from 'node:path';
// Importa el creador de un resolvedor de paquetes desde una ubicación concreta.
import { createRequire } from 'node:module';
// Permite convertir una ruta de Windows a una URL válida para import dinámico.
import { pathToFileURL } from 'node:url';
// Lee la ubicación de paquetes que reporte.py transmite en el entorno.
const root = process.env.ARTIFACT_NODE_MODULES;
// Configura la búsqueda de paquetes respecto de esa carpeta o de este propio módulo.
const require = createRequire(root ? path.join(root, '_resolver.cjs') : import.meta.url);
// Localiza e importa las clases que crean libros y exportan archivos XLSX.
const { Workbook, SpreadsheetFile } = await import(pathToFileURL(require.resolve('@oai/artifact-tool')).href);
// Obtiene entrada, salida y opción de verificación; omite los dos argumentos iniciales de Node.
const [input, output, verify] = process.argv.slice(2);
// Lee las tablas JSON de entrada y las convierte en un objeto JavaScript.
const data = JSON.parse(await fs.readFile(input, 'utf8'));
// Crea un libro vacío en memoria.
const wb = Workbook.create();
// Recorre cada pareja nombre/tabla recibida desde Python.
for (const [name, table] of Object.entries(data)) {
  // Agrega una hoja con el nombre de esa tabla.
  const sheet = wb.worksheets.add(name);
  // Oculta la cuadrícula visual predeterminada para facilitar la lectura.
  sheet.showGridLines = false;
  // Reserva las filas de datos más una para los encabezados.
  const rows = table.filas.length + 1;
  // Obtiene el número de columnas a partir de los encabezados.
  const cols = table.encabezados.length;
  // Evita superar las filas de Excel teniendo en cuenta las tres filas previas a la tabla.
  if (rows > 1048573) throw new Error(`${name}: demasiadas filas para Excel; reduzca N`);
  // Escribe el título general en Resumen y el nombre de la hoja en las demás.
  sheet.getRange('A2').values = [[name === 'Resumen' ? 'Competencia de contraseñas · Retroceso y Voraz' : name]];
  // Muestra la procedencia del experimento si Python proporcionó esa nota.
  if (table.nota) sheet.getRange('A3').values = [[table.nota]];
  // Da al título una fuente de 14 puntos y negrita.
  sheet.getRange('A2').format.font = { name: 'Arial', size: 14, bold: true };
  // Selecciona la tabla desde fila índice 3 y columna 0: corresponde a A4.
  const range = sheet.getRangeByIndexes(3, 0, rows, cols);
  // Escribe una matriz con encabezados y todas las filas; ... expande la lista de filas.
  range.values = [table.encabezados, ...table.filas];
  // Aplica una fuente legible y uniforme al contenido de la tabla.
  range.format.font = { name: 'Arial', size: 10 };
  // Establece la altura base de sus filas.
  range.format.rowHeight = 21;
  // Establece el ancho base de sus columnas.
  range.format.columnWidth = 20;
  // Selecciona únicamente la fila de encabezados.
  const header = sheet.getRangeByIndexes(3, 0, 1, cols);
  // Configura fondo azul oscuro y letras blancas en negrita para distinguirlos.
  header.format = { fill: '#233A59', font: { name: 'Arial', size: 10, color: '#FFFFFF', bold: true },
    // Permite envolver encabezados largos, aumenta su altura y centra el texto.
    wrapText: true, rowHeight: 34, horizontalAlignment: 'center' };
  // Centra verticalmente el contenido de las celdas.
  range.format.verticalAlignment = 'center';
  // Mantiene visibles las primeras cuatro filas al desplazar la hoja hacia abajo.
  sheet.freezePanes.freezeRows(4);
  // Mantiene visibles ronda y algoritmo al desplazarse horizontalmente.
  sheet.freezePanes.freezeColumns(2);
  // Solo aplica formato al cuerpo si existen filas de datos.
  if (table.filas.length) {
    // Recorre todas las columnas para identificar cuáles contienen números.
    for (let col = 0; col < cols; col++) {
      // Selecciona las celdas de datos de la columna, empezando en la fila 5 de Excel.
      const body = sheet.getRangeByIndexes(4, col, table.filas.length, 1);
      // some comprueba si al menos una fila contiene un valor numérico en esa columna.
      if (table.filas.some(row => typeof row[col] === 'number')) {
        // Muestra tres decimales en tiempos y enteros con separador de miles en otros números.
        body.setNumberFormat(table.encabezados[col].includes('(ms)') ? '0.000' : '#,##0');
      // Cierra la condición de columna numérica.
      }
    // Finaliza el formato de esta columna y continúa con la siguiente.
    }
  // Termina el tratamiento del cuerpo de datos.
  }
  // Aplica detalles que pertenecen solamente a la hoja Resumen.
  if (name === 'Resumen') {
    // Amplía las columnas de fase, asignación y último intento.
    sheet.getRange('M4:O4').format.columnWidth = 25;
    // Si hay datos, crea una regla condicional en la columna Resultado.
    if (rows > 1) sheet.getRange(`C5:C${rows+3}`).conditionalFormats.add('containsText', {
      // La regla destaca las celdas que contienen ÉXITO en verde y negrita.
      text: 'ÉXITO', format: { font: { bold: true, color: '#17623A' } }
    // Completa la configuración de la regla condicional.
    });
  // Termina las opciones exclusivas de Resumen.
  }
  // Amplía la columna con los nombres de los bucles para que se puedan leer.
  if (name === 'Bucles') sheet.getRange('D4').format.columnWidth = 34;
  // Amplía la columna equivalente en la hoja de recorridos por intento.
  if (name === 'Recorridos') sheet.getRange('E4').format.columnWidth = 34;
// Termina esta hoja y continúa con la siguiente tabla.
}
// Actualiza los cálculos del libro antes de inspeccionarlo o exportarlo.
wb.recalculate();
// Activa las comprobaciones adicionales únicamente si se pidió --verificar.
if (verify === '--verificar') {
  // Solicita una inspección de valores y fórmulas de una parte del resumen.
  console.log((await wb.inspect({kind:'table', range:'Resumen!A4:H10', include:'values,formulas',
    // Limita su tamaño y muestra el resultado de inspección en la consola.
    tableMaxRows:7, tableMaxCols:8, maxChars:3500})).ndjson);
  // Busca textos de errores comunes de Excel dentro del libro.
  console.log((await wb.inspect({kind:'match', searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!',
    // Usa expresión regular y limita las coincidencias mostradas para no llenar la consola.
    options:{useRegex:true,maxResults:20}, maxChars:1000})).ndjson);
  // Recorre las hojas para crear una vista de muestra de cada una.
  for (const [name, table] of Object.entries(data)) {
    // Solicita una imagen renderizada de la hoja actual.
    const preview = await wb.render({sheetName:name,
      // Selecciona un rango pequeño de muestra y una escala de 1.3; no captura toda la hoja.
      range:`A1:${name === 'Resumen' ? 'H' : name === 'Bucles' ? 'F' : 'G'}${Math.min(table.filas.length+4,12)}`, scale:1.3});
    // Guarda la imagen PNG en la carpeta del reporte, sin modificar sus mediciones.
    await fs.writeFile(path.join(path.dirname(output), `vista_${name}.png`), new Uint8Array(await preview.arrayBuffer()));
  // Termina la generación de la vista de esta hoja.
  }
// Termina las tareas opcionales de verificación.
}
// Define un nombre temporal para no dejar un Excel final parcialmente escrito.
const temporary = `${output}.tmp.xlsx`;
// Convierte el libro a XLSX y espera a que termine de guardarse en la ruta temporal.
await (await SpreadsheetFile.exportXlsx(wb)).save(temporary);
// Renombra el archivo temporal como reporte final; un Excel abierto puede bloquearlo en Windows.
await fs.rename(temporary, output);
// Informa la ruta del Excel actualizado.
console.log(`Excel actualizado: ${output}`);


