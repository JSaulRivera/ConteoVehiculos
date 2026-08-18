
from flask import Flask, render_template, Response, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix
from collections import defaultdict
from ultralytics import YOLO
import cv2
import numpy as np
import datetime
import os
import csv
import time
import threading


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)

app.wsgi_app = ProxyFix(
    app.wsgi_app,
    x_for=1,
    x_proto=1,
    x_host=1,
    x_prefix=1
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

MODEL_PATH = "yolo11n.pt"

# URL RTSP DE LA CÁMARA
RTSP_URL = os.getenv(
    "RTSP_URL",
    "rtsp://admin:admin123@192.168.1.34:554/live/ch00_1"
)

CSV_FILENAME = "eventos.csv"

FRECUENCIA_DETECCION = 10

TIEMPO_TOLERANCIA_SALIDA = 3

DISTANCIA_MAXIMA_MISMO_OBJETO = 50

TIEMPO_CAPTURA_ENTRADA = 10

TIEMPO_MINIMO_SALIDA = 30


# ============================================================
# CARPETAS
# ============================================================

os.makedirs("capturas_entrada", exist_ok=True)
os.makedirs("capturas_salida", exist_ok=True)


# ============================================================
# CSV
# ============================================================

if not os.path.exists(CSV_FILENAME) or os.stat(CSV_FILENAME).st_size == 0:

    with open(
        CSV_FILENAME,
        mode="w",
        newline="",
        encoding="utf-8"
    ) as archivo:

        writer = csv.writer(archivo)

        writer.writerow([
            "Evento",
            "ID",
            "Zona",
            "Hora",
            "Duración",
            "Duración_segundos",
            "Imagen",
            "Ocupados"
        ])


csv_lock = threading.Lock()


def registrar_evento_csv(datos):

    try:

        with csv_lock:

            with open(
                CSV_FILENAME,
                mode="a",
                newline="",
                encoding="utf-8"
            ) as archivo:

                writer = csv.writer(archivo)

                writer.writerow(datos)

    except Exception as e:

        print(f"[ERROR CSV] {e}")


# ============================================================
# MODELO YOLO
# ============================================================

print("[INFO] Cargando modelo YOLO...")

model = YOLO(MODEL_PATH)

print("[INFO] Modelo cargado correctamente.")


# ============================================================
# ZONAS
# ============================================================

zonas = {

    "1": (
        [(3, 65), (3, 150), (75, 133), (75, 60)],
        (5, 10)
    ),

    "2": (
        [(80, 60), (80, 130), (135, 115), (135, 55)],
        (95, 10)
    ),

    "3": (
        [(140, 52), (140, 113), (200, 95), (200, 42)],
        (180, 10)
    ),

    "4": (
        [(205, 40), (205, 93), (290, 68), (290, 25)],
        (240, 10)
    ),

    "5": (
        [(295, 25), (295, 63), (350, 50), (350, 20)],
        (310, 10)
    ),

    "6": (
        [(465, 85), (400, 140), (530, 170), (550, 95)],
        (450, 95)
    ),

    "7": (
        [(395, 146), (300, 200), (480, 250), (523, 178)],
        (370, 155)
    ),

    "8": (
        [(295, 203), (150, 300), (410, 350), (475, 255)],
        (270, 210)
    )
}


TOTAL_ESPACIOS = len(zonas)


# ============================================================
# ESTADO DE LAS ZONAS
# ============================================================

estado_zonas = {

    zona: {

        "track_id": None,

        "tiempo_entrada": None,

        "centroide": None,

        "ultimo_update": 0,

        "imagen_guardada": False

    }

    for zona in zonas
}


# ============================================================
# HISTORIAL DE TRACKING
# ============================================================

track_history = defaultdict(list)


# ============================================================
# ESTADO GLOBAL PARA LA WEB
# ============================================================

estado_global = {

    "ocupados": 0,

    "disponibles": TOTAL_ESPACIOS,

    "total": TOTAL_ESPACIOS,

    "detecciones": 0,

    "fps": 0,

    "camara": "Conectando...",

    "ultima_actualizacion": "",

    "zonas": {},

    "objetos": []

}


# ============================================================
# INICIALIZAR ZONAS
# ============================================================

for zona in zonas:

    estado_global["zonas"][zona] = {

        "ocupada": False,

        "track_id": None,

        "tiempo": "00:00:00"

    }


# ============================================================
# FRAMES
# ============================================================

# Frame procesado por YOLO
latest_frame = None

# Frame original de la cámara
latest_original_frame = None


# Locks independientes
frame_lock = threading.Lock()

original_frame_lock = threading.Lock()

estado_lock = threading.Lock()


# ============================================================
# CONEXIÓN A CÁMARA
# ============================================================

cap = None


def conectar_camara():

    global cap

    while True:

        try:

            print("[INFO] Intentando conectar con la cámara...")

            nuevo_cap = cv2.VideoCapture(RTSP_URL)

            nuevo_cap.set(
                cv2.CAP_PROP_BUFFERSIZE,
                1
            )

            if nuevo_cap.isOpened():

                cap = nuevo_cap

                print("[OK] Cámara RTSP conectada.")

                with estado_lock:

                    estado_global["camara"] = "Conectada"

                return True

            nuevo_cap.release()

            print(
                "[ERROR] No se pudo conectar con la cámara."
            )

        except Exception as e:

            print(
                f"[ERROR CAMARA] {e}"
            )

        with estado_lock:

            estado_global["camara"] = "Desconectada"

        time.sleep(5)


# ============================================================
# PROCESAMIENTO DE VIDEO
# ============================================================

def procesar_video():

    global cap

    global latest_frame

    global latest_original_frame


    contador_fotogramas = 0

    tiempo_fps_inicio = time.time()

    frames_fps = 0


    conectar_camara()


    while True:

        try:

            if cap is None or not cap.isOpened():

                conectar_camara()

                continue


            # ====================================================
            # LEER FRAME DE LA CÁMARA
            # ====================================================

            success, frame = cap.read()


            if not success:

                print(
                    "[ERROR] No se pudo leer frame."
                )

                try:

                    cap.release()

                except:

                    pass


                cap = None


                with estado_lock:

                    estado_global[
                        "camara"
                    ] = "Reconectando..."


                time.sleep(2)

                conectar_camara()

                continue


            contador_fotogramas += 1


            # ====================================================
            # GUARDAR FRAME ORIGINAL
            # ====================================================

            ret_original, buffer_original = cv2.imencode(
                ".jpg",
                frame,
                [
                    int(
                        cv2.IMWRITE_JPEG_QUALITY
                    ),
                    80
                ]
            )


            if ret_original:

                with original_frame_lock:

                    latest_original_frame = (
                        buffer_original.tobytes()
                    )


            # ====================================================
            # REDUCIR FRECUENCIA DE PROCESAMIENTO
            # ====================================================

            if (
                contador_fotogramas
                %
                FRECUENCIA_DETECCION
                !=
                0
            ):

                continue


            # ====================================================
            # YOLO TRACK
            # ====================================================

            results = model.track(

                frame,

                persist=True,

                classes=[
                    0,
                    2,
                    7
                ],

                verbose=False

            )


            result = results[0]


            # ====================================================
            # DATOS DE DETECCIONES
            # ====================================================

            boxes = result.boxes


            if boxes is None:

                continue


            boxes_xywh = (
                boxes.xywh.cpu().numpy()
            )

            boxes_xyxy = (
                boxes.xyxy.cpu().numpy()
            )

            confidences = (
                boxes.conf.cpu().numpy()
            )

            class_ids = (
                boxes.cls
                .cpu()
                .numpy()
                .astype(int)
            )


            if boxes.id is not None:

                track_ids = (
                    boxes.id
                    .int()
                    .cpu()
                    .numpy()
                    .tolist()
                )

            else:

                track_ids = [
                    None
                    for _ in boxes_xyxy
                ]


            names = model.names


            objetos_detectados = []


            tiempo_actual = time.time()


            # ====================================================
            # DETECCIONES
            # ====================================================

            for i in range(
                len(boxes_xyxy)
            ):

                box = boxes_xywh[i]

                box_xyxy = boxes_xyxy[i]

                conf = float(
                    confidences[i]
                )

                cls = int(
                    class_ids[i]
                )

                track_id = track_ids[i]


                x, y, w, h = box

                cx = int(x)

                cy = int(y)


                x1, y1, x2, y2 = map(
                    int,
                    box_xyxy
                )


                nombre = names[cls]

                confianza = conf * 100

                centroide = (
                    cx,
                    cy
                )


                # =================================================
                # HISTORIAL
                # =================================================

                if track_id is not None:

                    track = track_history[
                        track_id
                    ]

                    track.append(
                        (cx, cy)
                    )


                    if len(track) > 30:

                        track.pop(0)


                    points = np.array(
                        track,
                        dtype=np.int32
                    ).reshape(
                        (-1, 1, 2)
                    )


                    cv2.polylines(

                        frame,

                        [points],

                        isClosed=False,

                        color=(
                            255,
                            255,
                            0
                        ),

                        thickness=2

                    )


                # =================================================
                # TEXTO
                # =================================================

                texto = (
                    f"{nombre} "
                    f"{confianza:.1f}%"
                )


                # =================================================
                # RECTÁNGULO
                # =================================================

                cv2.rectangle(

                    frame,

                    (
                        x1,
                        y1
                    ),

                    (
                        x2,
                        y2
                    ),

                    (
                        255,
                        255,
                        0
                    ),

                    2

                )


                # =================================================
                # ETIQUETA
                # =================================================

                texto_y = max(
                    y1 - 10,
                    20
                )


                cv2.rectangle(

                    frame,

                    (
                        x1,
                        texto_y - 22
                    ),

                    (
                        x1
                        +
                        len(texto) * 8
                        +
                        10,

                        texto_y
                    ),

                    (
                        0,
                        31,
                        51
                    ),

                    -1

                )


                cv2.putText(

                    frame,

                    texto,

                    (
                        x1 + 5,
                        texto_y - 6
                    ),

                    cv2.FONT_HERSHEY_SIMPLEX,

                    0.5,

                    (
                        0,
                        255,
                        255
                    ),

                    1,

                    cv2.LINE_AA

                )


                # =================================================
                # DATOS PARA JAVASCRIPT
                # =================================================

                objetos_detectados.append({

                    "id":
                        int(track_id)
                        if track_id is not None
                        else None,

                    "nombre":
                        nombre,

                    "confianza":
                        round(
                            confianza,
                            1
                        ),

                    "centroide": [
                        cx,
                        cy
                    ]

                })


                # =================================================
                # COMPROBAR ZONAS
                # =================================================

                if track_id is None:

                    continue


                for zona, datos_zona in zonas.items():

                    poligono, texto_pos = (
                        datos_zona
                    )


                    dentro = (
                        cv2.pointPolygonTest(

                            np.array(
                                poligono,
                                np.int32
                            ),

                            centroide,

                            False

                        )
                        >=
                        0
                    )


                    zona_actual = (
                        estado_zonas[zona]
                    )


                    if dentro:

                        # =========================================
                        # ENTRADA A ZONA VACÍA
                        # =========================================

                        if (
                            zona_actual[
                                "track_id"
                            ]
                            is None
                        ):

                            estado_zonas[zona] = {

                                "track_id":
                                    track_id,

                                "tiempo_entrada":
                                    tiempo_actual,

                                "centroide":
                                    centroide,

                                "ultimo_update":
                                    tiempo_actual,

                                "imagen_guardada":
                                    False

                            }


                        else:

                            distancia = np.linalg.norm(

                                np.array(
                                    centroide
                                )
                                -
                                np.array(
                                    zona_actual[
                                        "centroide"
                                    ]
                                )

                            )


                            # =====================================
                            # MISMO OBJETO
                            # =====================================

                            if (

                                distancia
                                <
                                DISTANCIA_MAXIMA_MISMO_OBJETO

                                and

                                track_id
                                ==
                                zona_actual[
                                    "track_id"
                                ]

                            ):

                                estado_zonas[zona][
                                    "ultimo_update"
                                ] = (
                                    tiempo_actual
                                )


                                estado_zonas[zona][
                                    "centroide"
                                ] = centroide


                                # =================================
                                # CAPTURA ENTRADA
                                # =================================

                                if (

                                    not zona_actual[
                                        "imagen_guardada"
                                    ]

                                    and

                                    tiempo_actual
                                    -
                                    zona_actual[
                                        "tiempo_entrada"
                                    ]
                                    >=
                                    TIEMPO_CAPTURA_ENTRADA

                                ):

                                    timestamp_str = (

                                        datetime.datetime.now()
                                        .strftime(
                                            "%Y-%m-%d_%H-%M-%S"
                                        )

                                    )


                                    hora_exacta_str = (

                                        datetime.datetime.now()
                                        .strftime(
                                            "%Y-%m-%d %H:%M:%S"
                                        )

                                    )


                                    nombre_imagen = (

                                        f"entrada_"
                                        f"{zona}_"
                                        f"id{track_id}_"
                                        f"{timestamp_str}.jpg"

                                    )


                                    frame_captura = (
                                        frame.copy()
                                    )


                                    ruta = os.path.join(

                                        "capturas_entrada",

                                        nombre_imagen

                                    )


                                    cv2.imwrite(

                                        ruta,

                                        frame_captura

                                    )


                                    zona_actual[
                                        "imagen_guardada"
                                    ] = True


                                    print(

                                        f"[ENTRADA] "
                                        f"ID {track_id} "
                                        f"en zona {zona}"

                                    )


                            # =====================================
                            # NUEVO OBJETO
                            # =====================================

                            elif (

                                track_id
                                !=
                                zona_actual[
                                    "track_id"
                                ]

                            ):

                                estado_zonas[zona] = {

                                    "track_id":
                                        track_id,

                                    "tiempo_entrada":
                                        tiempo_actual,

                                    "centroide":
                                        centroide,

                                    "ultimo_update":
                                        tiempo_actual,

                                    "imagen_guardada":
                                        False

                                }


            # ====================================================
            # ACTUALIZAR ESTADO DE ZONAS
            # ====================================================

            ocupados = 0


            for zona, datos_zona in zonas.items():

                poligono, texto_pos = (
                    datos_zona
                )


                zona_actual = (
                    estado_zonas[zona]
                )


                tiempo_sin_update = (

                    tiempo_actual

                    -
                    zona_actual[
                        "ultimo_update"
                    ]

                )


                zona_ocupada = (

                    zona_actual[
                        "track_id"
                    ]
                    is not None

                    and

                    tiempo_sin_update
                    <=
                    TIEMPO_TOLERANCIA_SALIDA

                )


                if zona_ocupada:

                    ocupados += 1


                # =================================================
                # COLOR ZONA
                # =================================================

                if zona_ocupada:

                    color = (
                        0,
                        0,
                        255
                    )

                else:

                    color = (
                        0,
                        255,
                        0
                    )


                # =================================================
                # DIBUJAR POLÍGONO
                # =================================================

                cv2.polylines(

                    frame,

                    [
                        np.array(
                            poligono,
                            np.int32
                        )
                    ],

                    True,

                    color,

                    2

                )


                # =================================================
                # NÚMERO ZONA
                # =================================================

                cv2.putText(

                    frame,

                    f"Zona {zona}",

                    texto_pos,

                    cv2.FONT_HERSHEY_COMPLEX,

                    0.5,

                    (
                        255,
                        255,
                        0
                    ),

                    1

                )


                # =================================================
                # CRONÓMETRO
                # =================================================

                if (

                    zona_actual[
                        "track_id"
                    ]
                    is not None

                ):

                    segundos = int(

                        tiempo_actual

                        -

                        zona_actual[
                            "tiempo_entrada"
                        ]

                    )


                    tiempo_formateado = (

                        time.strftime(

                            "%H:%M:%S",

                            time.gmtime(
                                segundos
                            )

                        )

                    )


                    cv2.putText(

                        frame,

                        tiempo_formateado,

                        (
                            texto_pos[0] - 20,
                            texto_pos[1] + 90
                        ),

                        cv2.FONT_HERSHEY_SIMPLEX,

                        0.5,

                        (
                            255,
                            255,
                            255
                        ),

                        1

                    )


            # ====================================================
            # PROCESAR SALIDAS
            # ====================================================

            for zona, datos in list(
                estado_zonas.items()
            ):

                if datos[
                    "track_id"
                ] is None:

                    continue


                tiempo_sin_update = (

                    tiempo_actual

                    -

                    datos[
                        "ultimo_update"
                    ]

                )


                if (

                    tiempo_sin_update
                    >
                    TIEMPO_TOLERANCIA_SALIDA

                ):

                    duracion_segundos = int(

                        tiempo_actual

                        -

                        datos[
                            "tiempo_entrada"
                        ]

                    )


                    if (

                        duracion_segundos
                        >=
                        TIEMPO_MINIMO_SALIDA

                    ):

                        duracion_formato = (

                            time.strftime(

                                "%H:%M:%S",

                                time.gmtime(
                                    duracion_segundos
                                )

                            )

                        )


                        timestamp_str = (

                            datetime.datetime.now()
                            .strftime(
                                "%Y-%m-%d_%H-%M-%S"
                            )

                        )


                        hora_exacta_str = (

                            datetime.datetime.now()
                            .strftime(
                                "%Y-%m-%d %H:%M:%S"
                            )

                        )


                        nombre_imagen = (

                            f"salida_"
                            f"{zona}_"
                            f"id{datos['track_id']}_"
                            f"{timestamp_str}.jpg"

                        )


                        ruta = os.path.join(

                            "capturas_salida",

                            nombre_imagen

                        )


                        frame_captura = (
                            frame.copy()
                        )


                        cv2.imwrite(

                            ruta,

                            frame_captura

                        )


                        registrar_evento_csv([

                            "SALIDA",

                            datos[
                                "track_id"
                            ],

                            zona,

                            hora_exacta_str,

                            duracion_formato,

                            duracion_segundos,

                            nombre_imagen,

                            ocupados

                        ])


                        print(

                            f"[SALIDA] "
                            f"ID {datos['track_id']} "
                            f"zona {zona} "
                            f"duración "
                            f"{duracion_formato}"

                        )


                    else:

                        print(

                            f"[IGNORADO] "
                            f"ID {datos['track_id']} "
                            f"salió de zona "
                            f"{zona} antes de "
                            f"{TIEMPO_MINIMO_SALIDA}s"

                        )


                    # =============================================
                    # LIBERAR ZONA
                    # =============================================

                    estado_zonas[zona] = {

                        "track_id":
                            None,

                        "tiempo_entrada":
                            None,

                        "centroide":
                            None,

                        "ultimo_update":
                            0,

                        "imagen_guardada":
                            False

                    }


            # ====================================================
            # ESTADÍSTICAS
            # ====================================================

            disponibles = (

                TOTAL_ESPACIOS
                -
                ocupados

            )


            # ====================================================
            # FPS
            # ====================================================

            frames_fps += 1

            tiempo_fps_actual = (
                time.time()
            )

            tiempo_fps = (

                tiempo_fps_actual

                -
                tiempo_fps_inicio

            )


            if tiempo_fps >= 1:

                fps = round(

                    frames_fps
                    /
                    tiempo_fps,

                    1

                )


                frames_fps = 0

                tiempo_fps_inicio = (
                    tiempo_fps_actual
                )

            else:

                fps = estado_global[
                    "fps"
                ]


            # ====================================================
            # ACTUALIZAR ESTADO GLOBAL
            # ====================================================

            with estado_lock:

                estado_global[
                    "ocupados"
                ] = ocupados


                estado_global[
                    "disponibles"
                ] = disponibles


                estado_global[
                    "detecciones"
                ] = len(
                    objetos_detectados
                )


                estado_global[
                    "fps"
                ] = fps


                estado_global[
                    "camara"
                ] = "Conectada"


                estado_global[
                    "ultima_actualizacion"
                ] = (

                    datetime.datetime.now()
                    .strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )

                )


                estado_global[
                    "objetos"
                ] = objetos_detectados


                for zona in zonas:

                    datos_zona = (
                        estado_zonas[zona]
                    )


                    ocupada = (

                        datos_zona[
                            "track_id"
                        ]
                        is not None

                        and

                        tiempo_actual

                        -
                        datos_zona[
                            "ultimo_update"
                        ]

                        <=
                        TIEMPO_TOLERANCIA_SALIDA

                    )


                    if (

                        ocupada

                        and

                        datos_zona[
                            "tiempo_entrada"
                        ]
                        is not None

                    ):

                        segundos = int(

                            tiempo_actual

                            -

                            datos_zona[
                                "tiempo_entrada"
                            ]

                        )

                    else:

                        segundos = 0


                    estado_global[
                        "zonas"
                    ][zona] = {

                        "ocupada":
                            ocupada,

                        "track_id":
                            datos_zona[
                                "track_id"
                            ],

                        "tiempo":
                            time.strftime(

                                "%H:%M:%S",

                                time.gmtime(
                                    segundos
                                )

                            )

                    }


            # ====================================================
            # CODIFICAR FRAME PROCESADO
            # ====================================================

            ret, buffer = cv2.imencode(

                ".jpg",

                frame,

                [
                    int(
                        cv2.IMWRITE_JPEG_QUALITY
                    ),

                    80

                ]

            )


            if ret:

                with frame_lock:

                    latest_frame = (
                        buffer.tobytes()
                    )


        except Exception as e:

            print(
                f"[ERROR PROCESAMIENTO] {e}"
            )

            time.sleep(1)


# ============================================================
# GENERADOR VIDEO PROCESADO
# ============================================================

def generar_video():

    while True:

        with frame_lock:

            frame = latest_frame


        if frame is not None:

            yield (

                b"--frame\r\n"

                b"Content-Type: image/jpeg\r\n\r\n"

                +

                frame

                +

                b"\r\n"

            )


        time.sleep(0.03)


# ============================================================
# GENERADOR VIDEO ORIGINAL
# ============================================================

def generar_video_original():

    while True:

        with original_frame_lock:

            frame = latest_original_frame


        if frame is not None:

            yield (

                b"--frame\r\n"

                b"Content-Type: image/jpeg\r\n\r\n"

                +

                frame

                +

                b"\r\n"

            )


        time.sleep(0.03)


# ============================================================
# RUTA PRINCIPAL
# ============================================================

@app.route("/")
def index():

    return render_template(
        "index.html"
    )


# ============================================================
# VIDEO PROCESADO POR YOLO
# ============================================================

@app.route("/video_feed")
def video_feed():

    return Response(

        generar_video(),

        mimetype=(

            "multipart/x-mixed-replace; "
            "boundary=frame"

        )

    )


# ============================================================
# VIDEO ORIGINAL DE LA CÁMARA
# ============================================================

@app.route("/video_original")
def video_original():

    return Response(

        generar_video_original(),

        mimetype=(

            "multipart/x-mixed-replace; "
            "boundary=frame"

        )

    )


# ============================================================
# API ESTADO
# ============================================================

@app.route("/api/estado")
def api_estado():

    with estado_lock:

        datos = {

            "ocupados":
                estado_global[
                    "ocupados"
                ],

            "disponibles":
                estado_global[
                    "disponibles"
                ],

            "total":
                estado_global[
                    "total"
                ],

            "detecciones":
                estado_global[
                    "detecciones"
                ],

            "fps":
                estado_global[
                    "fps"
                ],

            "camara":
                estado_global[
                    "camara"
                ],

            "ultima_actualizacion":
                estado_global[
                    "ultima_actualizacion"
                ],

            "zonas":
                estado_global[
                    "zonas"
                ],

            "objetos":
                estado_global[
                    "objetos"
                ]

        }


    return jsonify(datos)


# ============================================================
# API EVENTOS
# ============================================================

@app.route("/api/eventos")
def api_eventos():

    eventos = []


    try:

        with csv_lock:

            with open(

                CSV_FILENAME,

                mode="r",

                encoding="utf-8"

            ) as archivo:

                reader = csv.DictReader(
                    archivo
                )


                for fila in reader:

                    eventos.append(fila)


        # Últimos 20 eventos

        eventos = eventos[-20:]

        eventos.reverse()


    except Exception as e:

        print(
            f"[ERROR EVENTOS] {e}"
        )


    return jsonify(eventos)


# ============================================================
# CAPTURAS DE ENTRADA
# ============================================================

@app.route(
    "/capturas_entrada/<path:nombre>"
)
def captura_entrada(nombre):

    return app.send_static_file(

        os.path.join(

            "..",

            "capturas_entrada",

            nombre

        )

    )


# ============================================================
# INICIAR
# ============================================================

if __name__ == "__main__":

    hilo_video = threading.Thread(

        target=procesar_video,

        daemon=True

    )


    hilo_video.start()


    print("")

    print(
        "=========================================="
    )

    print(
        " SISTEMA DE MONITOREO DE ESTACIONAMIENTO"
    )

    print(
        "=========================================="
    )

    print(
        "Servidor: http://127.0.0.1:5000"
    )

    print(
        "Video YOLO: http://127.0.0.1:5000/video_feed"
    )

    print(
        "Video original: http://127.0.0.1:5000/video_original"
    )

    print(
        "Presiona CTRL+C para detener."
    )

    print("")


    app.run(

        host="0.0.0.0",

        port=5000,

        debug=False,

        threaded=True

    )

