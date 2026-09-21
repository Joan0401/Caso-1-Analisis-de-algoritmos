import fs from 'node:fs/promises';
import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load('resultados/20260920_170559_046031/resultados.xlsx'));
console.log((await wb.inspect({kind:'table',range:'Resumen!A4:P8',include:'values,formulas',tableMaxRows:5,tableMaxCols:16,maxChars:2200})).ndjson);
const img=await wb.render({sheetName:'Resumen',range:'A1:H8',scale:1});
await fs.writeFile('.excel_antes.png',new Uint8Array(await img.arrayBuffer()));
