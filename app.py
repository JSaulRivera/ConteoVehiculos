from collections import defaultdict
import cv2
import numpy as np
import time
from ultralytics import YOLO
import datetime 
import os
import csv
from arcgis.gis import GIS
from arcgis.features import FeatureLayer, Feature
import threading

csv_filename = "eventos.csv"
if not os.path.exists(csv_filename) or os.stat(csv_filename).st_size == 0:
    with open(csv_filename, mode='w', newline='') as archivo:
        writer = csv.writer(archivo)
        writer.writerow(["Evento", "ID", "Zona", "Hora", "Duración", "Imagen"])

model = YOLO('yolov8n.pt')
cap = cv2.VideoCapture('rtsp://admin:admin123@192.168.1.34:554/live/ch00_1')

frecuencia_deteccion = 10
contador_fotogramas = 0

os.makedirs("capturas_entrada", exist_ok=True)
os.makedirs("capturas_salida", exist_ok=True)

zonas = {
    '1': ([(3, 3), (3, 100), (85, 87), (85, 3)], (5, 10)),
    '2': ([(90, 3), (90, 87), (170, 72), (170, 3)], (95, 10)),
    '3': ([(175, 3), (175, 71), (230, 64), (230, 3)], (180, 10)),
    '4': ([(235, 3), (235, 64), (300, 57), (300, 3)], (240, 10)),
    '5': ([(305, 3), (305, 57), (365, 50), (365, 3)], (310, 10)),
    '6': ([(515, 55), (470, 90), (555, 120), (555, 55)], (490, 60)),
    '7': ([(465, 95), (400, 140), (530, 170), (550, 125)], (450, 95)),
    '8': ([(395, 146), (300, 200), (480, 250), (523, 178)], (370, 155)),
    '9': ([(295, 203), (150, 300), (410, 350), (475, 255)], (270, 210)),
}
TOTAL_ESPACIOS = len(zonas)

estado_zonas = {
    zona: {
        'track_id': None,
        'tiempo_entrada': None,
        'centroide': None,
        'ultimo_update': 0,
        'imagen_guardada': False
    }
    for zona in zonas
}

TIEMPO_TOLERANCIA_SALIDA = 3
DISTANCIA_MAXIMA_MISMO_OBJETO = 50

track_history = defaultdict(lambda: [])
puntos = []

# def click_event(event, x, y, flags, param):
#     if event == cv2.EVENT_LBUTTONDOWN:
#         puntos.append((x, y))
#         print(f"Punto agregado: ({x}, {y})")
#         if len(puntos) >= 2:
#             cv2.line(param, puntos[-2], puntos[-1], (255, 0, 0), 2)

# def registrar_evento_csv(nombre_archivo, datos):
#     with open(nombre_archivo, mode='a', newline='') as archivo:
#         writer = csv.writer(archivo)
#         writer.writerow(datos)
#         formato = '%Y-%m-%d %H:%M:%S'
#         fecha_datetime = datetime.datetime.strptime(datos[3], formato)
       
#         if datos[5]=='':
#             tiempo_estacionado=0
#             tiempo_formato='00:00:00'
#         else:
#             tiempo_estacionado=int(datos[5])
#             tiempo_formato=datos[4]
#         gis = GIS()
#         lyr_url = 'https://smart-twins.sigsa.info/server/rest/services/Hosted/RegistroEstacionamiento_WFL1/FeatureServer/0'
#         layer = FeatureLayer(lyr_url)
#         new_point = {
#             'attributes': {
#                 'evento': datos[0],
#                 'id': datos[1],
#                 'zona': datos[2],
#                 'fechaevento': fecha_datetime,                
#                 'imagen': datos[6],
#                 'tiempoestacionado':tiempo_estacionado,
#                 'tiempoduracion': tiempo_formato,
#                 'disponibilidad': 13-datos[7]
#             },
#             'geometry': {
#             'x': -98.414301,
#             'y': 20.063116,
#             'spatialReference': {'wkid': 4326}
#         },
#             'visible': True
#         }
#         nuevo_feature = Feature(geometry=new_point['geometry'], attributes=new_point['attributes'])
#         try:
#             resultado = layer.edit_features(adds=[nuevo_feature])
#             if resultado and 'addResults' in resultado and resultado['addResults']:
            
#                 if 'success' in resultado['addResults'][0]:
#                     if datos[0]=='ENTRADA':
#                         valevento="capturas_entrada/"
#                     else:
#                         valevento="capturas_salida/"

#                     new_object_id = resultado['addResults'][0]['objectId']
#                     attachment_result = layer.attachments.add(
#                     new_object_id,valevento+datos[6]  
#                 )
#                     if attachment_result:
#                         print('Imagen adjuntada correctamente.')
#                     else:
#                         print('Error al adjuntar la imagen.')
#                 else:
#                     print('Error al agregar el punto:', resultado['addResults'][0].get('error', ''))
#             else:
#                 print('Error inesperado al agregar el punto')
#         except Exception as e:
#             print('Excepción:', str(e))


#         print("Datos agregados.")

while cap.isOpened():
    success, frame = cap.read()
    if not success:
        break

    contador_fotogramas += 1
    if contador_fotogramas % frecuencia_deteccion != 0:
        continue

    results = model.track(frame, persist=True, classes=[0, 2, 7])
    boxes = results[0].boxes.xywh.cpu()
    boxes_xyxy = results[0].boxes.xyxy.cpu()
    track_ids = results[0].boxes.id.int().cpu().tolist() if results[0].boxes.id is not None else []
    confidences = results[0].boxes.conf.cpu().tolist()
    class_ids = results[0].boxes.cls.int().cpu().tolist()
    names = model.names

    ocupados = 0
    tiempo_actual = time.time()

    for box, box_xyxy, track_id, conf, cls in zip(boxes, boxes_xyxy,track_ids,confidences,class_ids):

        x, y, w, h = box
        cx, cy = int(x), int(y)
        x1, y1, x2, y2 = map(int, box_xyxy)
        nombre = names[cls]
        confianza = conf * 100
        centroide = (cx, cy)

        track = track_history[track_id]
        track.append((cx, cy))
        if len(track) > 30:
            track.pop(0)
        points = np.hstack(track).astype(np.int32).reshape((-1, 1, 2))
        texto = f"{nombre} {confianza:.1f}%"
        
        cv2.polylines(frame, [points], isClosed=False, color=(255, 255, 0), thickness=5) #punto medio
        cv2.putText(frame,texto,(x1, y2 + 15),cv2.FONT_HERSHEY_SIMPLEX,0.6,(255, 255, 0),1) #clase
        cv2.rectangle(frame, (x1, y1),(x2, y2),(255, 255, 0),1)   #Deteccion

        for zona, (poligono, texto_pos) in zonas.items():
            dentro = cv2.pointPolygonTest(np.array(poligono, np.int32), centroide, False) >= 0
            zona_actual = estado_zonas[zona]

            if dentro:
                ocupados += 1

                if zona_actual['track_id'] is None:
                    estado_zonas[zona] = {
                        'track_id': track_id,
                        'tiempo_entrada': tiempo_actual,
                        'centroide': centroide,
                        'ultimo_update': tiempo_actual,
                        'imagen_guardada': False
                    }

                else:
                    distancia = np.linalg.norm(np.array(centroide) - np.array(zona_actual['centroide']))
                    if distancia < DISTANCIA_MAXIMA_MISMO_OBJETO:
                        estado_zonas[zona]['ultimo_update'] = tiempo_actual
                        estado_zonas[zona]['centroide'] = centroide

                        if not zona_actual['imagen_guardada'] and tiempo_actual - zona_actual['tiempo_entrada'] >= 10:
                            timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                            hora_exacta_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            nombre_imagen = f"entrada_{zona}_id{track_id}_{timestamp_str}.jpg"
                            cv2.polylines(frame, [np.array(poligono, np.int32)], True, (255, 0, 0), 1)
                            cv2.imwrite(f"capturas_entrada/{nombre_imagen}", frame)
                            #threading.Thread(target=registrar_evento_csv, args=("eventos.csv", ["ENTRADA", track_id, zona, hora_exacta_str, "","", nombre_imagen,ocupados])).start()
                            # registrar_evento_csv("eventos.csv", ["ENTRADA", track_id, zona, hora_exacta_str, "","", nombre_imagen,ocupados])
                            estado_zonas[zona]['imagen_guardada'] = True
                            print(f"[ENTRADA] ID {track_id} en zona {zona} (captura retrasada 10s)")

                    elif track_id != zona_actual['track_id']:
                        estado_zonas[zona] = {
                            'track_id': track_id,
                            'tiempo_entrada': tiempo_actual,
                            'centroide': centroide,
                            'ultimo_update': tiempo_actual,
                            'imagen_guardada': False
                        }

                segundos = int(tiempo_actual - estado_zonas[zona]['tiempo_entrada'])
                tiempo_formateado = time.strftime('%H:%M:%S', time.gmtime(segundos))
                cv2.putText(frame, tiempo_formateado, (texto_pos[0]-10,texto_pos[1]+70), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)#cronometro

            
            for zona, (poligono, texto_pos) in zonas.items():
                zona_actual = estado_zonas[zona]
                tiempo_sin_update = tiempo_actual - zona_actual['ultimo_update']

                # Se considera ocupada si hay un ID activo y ha tenido actualizaciones recientes
                zona_ocupada = zona_actual['track_id'] is not None and tiempo_sin_update <= TIEMPO_TOLERANCIA_SALIDA

                color = (0, 0, 255) if zona_ocupada else (0, 255, 0)  # Rojo si ocupada, verde si libre

                cv2.polylines(frame, [np.array(poligono, np.int32)], True, color, 2)
                cv2.putText(frame, zona, texto_pos, cv2.FONT_HERSHEY_COMPLEX, 0.5, (255, 255, 0), 1)


    # Salidas
    for zona, datos in estado_zonas.items():
        if datos['track_id'] is not None and tiempo_actual - datos['ultimo_update'] > TIEMPO_TOLERANCIA_SALIDA:
            duracion_segundos = int(tiempo_actual - datos['tiempo_entrada'])
            if duracion_segundos >= 30:
                duracion_formato = time.strftime('%H:%M:%S', time.gmtime(duracion_segundos))
                timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                hora_exacta_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                nombre_imagen = f"salida_{zona}_id{datos['track_id']} {timestamp_str}.jpg"
                cv2.polylines(frame, [np.array(poligono, np.int32)], True, (255, 0, 0), 1)
                cv2.imwrite(f"capturas_salida/{nombre_imagen}", frame)
                #threading.Thread(target=registrar_evento_csv, args=("eventos.csv", ["SALIDA", datos['track_id'], zona, hora_exacta_str, duracion_formato,duracion_segundos, nombre_imagen, ocupados])).start()
                
                print(f"[SALIDA] ID {datos['track_id']} salió de zona {zona} (duración: {duracion_formato})")
            else:
                print(f"[IGNORADO] ID {datos['track_id']} salió de zona {zona} antes de 30s")

            estado_zonas[zona] = {'track_id': None, 'tiempo_entrada': None, 'centroide': None, 'ultimo_update': 0, 'imagen_guardada': False}

    espacios_disponibles = TOTAL_ESPACIOS - ocupados
    cv2.putText(frame, f"Disponibles: {espacios_disponibles}/{TOTAL_ESPACIOS}", (10, 330), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 0), 1)
    cv2.imshow("Estacionamiento", frame)
    # cv2.setMouseCallback("Estacionamiento", click_event)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
