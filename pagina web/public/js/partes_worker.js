// ==========================================================
// PROBADOR VIRTUAL INTELIGENTE - PÁGINA WEB
// Separa a la persona en partes (pelo, piel, cara, ropa) con MediaPipe Image Segmenter.
// Corre en un proceso aparte: el modelo es pesado y así no traba la cámara. Todo queda en
// el navegador: la imagen de la cámara no sale del dispositivo.
// ==========================================================

const CDN = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14";
const MODELO = "https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_multiclass_256x256/float32/latest/selfie_multiclass_256x256.tflite";

self.exports = {};
self.module = { exports: self.exports };
// (copia local: el CDN sirve el .cjs con un tipo que un Worker no acepta)
importScripts("vendor/vision_bundle_0.10.14.js");
const { FilesetResolver, ImageSegmenter } = self.module.exports;

let segmentador = null;

(async () => {
  const archivos = await FilesetResolver.forVisionTasks(`${CDN}/wasm`);
  const opciones = (delegado) => ({
    baseOptions: { modelAssetPath: MODELO, delegate: delegado },
    runningMode: "IMAGE", outputCategoryMask: true, outputConfidenceMasks: false,
  });
  try {
    segmentador = await ImageSegmenter.createFromOptions(archivos, opciones("GPU"));
  } catch (e) {
    segmentador = await ImageSegmenter.createFromOptions(archivos, opciones("CPU"));
  }
  self.postMessage({ listo: true });
})().catch((e) => self.postMessage({ error: String(e) }));

self.onmessage = ({ data }) => {
  const { imagen, id } = data;
  if (!segmentador) {
    imagen.close();
    self.postMessage({ id, vacio: true });
    return;
  }
  try {
    const resultado = segmentador.segment(imagen);
    const mascara = resultado.categoryMask;
    const categorias = mascara.getAsUint8Array().slice();
    const ancho = mascara.width, alto = mascara.height;
    mascara.close();
    self.postMessage({ id, categorias, ancho, alto }, [categorias.buffer]);
  } catch (e) {
    self.postMessage({ id, error: String(e) });
  } finally {
    imagen.close();
  }
};
