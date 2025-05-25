from django.shortcuts import render, redirect
import os
import cv2
import face_recognition
from django.conf import settings
from django.contrib import messages
from django.http import StreamingHttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
import numpy as np
import base64
import pickle
from .models import Empleado, EventosAsistencia 
from datetime import datetime
from django.views.decorators.http import require_POST

# Directorios
user_dir = os.path.join(settings.MEDIA_ROOT, 'usuarios')
encoding_dir = os.path.join(user_dir, 'encodings')

os.makedirs(user_dir, exist_ok=True)
os.makedirs(encoding_dir, exist_ok=True)

def login_facial(request):
    if request.method == 'POST':
        messages.info(request, "Mira a la cámara. Verificando tu rostro...")

        cam = cv2.VideoCapture(0)
        ret, frame = cam.read()
        cam.release()

        if not ret:
            messages.error(request, "No se pudo acceder a la cámara.")
            return redirect('login_facial')

        face_locations = face_recognition.face_locations(frame)
        if not face_locations:
            messages.error(request, "No se detectó ningún rostro.")
            return redirect('login_facial')

        unknown_encoding = face_recognition.face_encodings(frame, [face_locations[0]])[0]

        for filename in os.listdir(encoding_dir):
            if filename.endswith('.pkl'):
                path = os.path.join(encoding_dir, filename)
                with open(path, 'rb') as f:
                    known_encoding = pickle.load(f)

                result = face_recognition.compare_faces([known_encoding], unknown_encoding, tolerance=0.45)
                if result[0]:
                    empleado_id = int(filename.replace('.pkl', ''))
                    try:
                        empleado = Empleado.objects.get(id=empleado_id)
                    except Empleado.DoesNotExist:
                        continue

                    ahora = datetime.now()
                    hoy = ahora.date()

                    # ✅ Verificación especial para ADMINISTRADOR
                    if empleado.cargo.lower() == "administrador":
                        request.session['empleado_id'] = empleado.id
                        request.session['tipo_evento'] = 'admin'
                        messages.success(request, f"Bienvenido Administrador: {empleado.nombre}")
                        return redirect('panel_administrador')

                    ultimo_evento = EventosAsistencia.objects.filter(empleado=empleado).order_by('-id').first()

                    if not ultimo_evento or ultimo_evento.tipo == 'salida':
                        tipo = 'entrada'
                    else:
                        tipo = 'salida'

                    mensaje = f"{empleado.nombre}, tu hora de {tipo} fue registrada a las {ahora.strftime('%H:%M:%S')}."

                    EventosAsistencia.objects.create(
                        empleado=empleado,
                        fecha=hoy,
                        hora=ahora.time(),
                        tipo=tipo
                    )

                    messages.success(request, mensaje)
                    request.session['empleado_id'] = empleado.id
                    request.session['tipo_evento'] = tipo
                    return redirect('gracias')

        messages.error(request, "Ningún rostro coincide con los registrados.")
        return redirect('login_facial')

    return render(request, 'empleado/login_facial.html')

def gen_camera():
    cam = cv2.VideoCapture(0)
    while True:
        ret, frame = cam.read()
        if not ret:
            break
        _, buffer = cv2.imencode('.jpg', frame)
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
    cam.release()

def video_feed(request):
    return StreamingHttpResponse(gen_camera(), content_type='multipart/x-mixed-replace; boundary=frame')

@csrf_exempt
def validar_rostro(request):
    if request.method == 'POST':
        data_url = request.POST.get('image')
        if not data_url:
            return JsonResponse({'success': False, 'message': 'No se recibió imagen.'})

        header, encoded = data_url.split(',', 1)
        img_data = base64.b64decode(encoded)
        np_arr = np.frombuffer(img_data, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        face_locations = face_recognition.face_locations(frame)
        if not face_locations:
            return JsonResponse({'success': False, 'message': 'No se detectó ningún rostro.'})

        unknown_encoding = face_recognition.face_encodings(frame, [face_locations[0]])[0]

        for filename in os.listdir(encoding_dir):
            if filename.endswith('.pkl'):
                path = os.path.join(encoding_dir, filename)
                with open(path, 'rb') as f:
                    known_encoding = pickle.load(f)

                result = face_recognition.compare_faces([known_encoding], unknown_encoding, tolerance=0.45)
                if result[0]:
                    empleado_id = int(filename.replace('.pkl', ''))
                    try:
                        empleado = Empleado.objects.get(id=empleado_id)
                    except Empleado.DoesNotExist:
                        continue

                    ahora = datetime.now()
                    hoy = ahora.date()

                    # ✅ Verificación especial para ADMINISTRADOR
                    if empleado.cargo.lower() == "administrador":
                        request.session['empleado_id'] = empleado.id
                        request.session['tipo_evento'] = 'admin'
                        return JsonResponse({'success': True, 'message': f"Bienvenido Administrador: {empleado.nombre}", 'redirect': 'panel_administrador'})

                    ultimo_evento = EventosAsistencia.objects.filter(empleado=empleado).order_by('-id').first()
                    tipo = 'entrada' if not ultimo_evento or ultimo_evento.tipo == 'salida' else 'salida'

                    mensaje = f"{empleado.nombre}, registro exitoso. Tu hora de {tipo} fue {ahora.strftime('%H:%M:%S')}."

                    EventosAsistencia.objects.create(
                        empleado=empleado,
                        fecha=hoy,
                        hora=ahora.time(),
                        tipo=tipo
                    )

                    request.session['empleado_id'] = empleado.id
                    request.session['tipo_evento'] = tipo

                    return JsonResponse({'success': True, 'message': mensaje})

        return JsonResponse({'success': False, 'message': 'No coincide con ningún rostro registrado.'})

def inicio(request):
    return render(request, 'empleado/inicio.html')

def home(request):
    return redirect('inicio')


def panel_administrador(request):
    empleados = Empleado.objects.exclude(cargo__iexact='Administrador').order_by('cargo', 'nombre')
    registros = EventosAsistencia.objects.all().order_by('empleado__cargo', 'empleado__nombre', '-fecha', '-hora')

    data_por_empleado = {}
    for empleado in empleados:
        data_por_empleado[empleado] = registros.filter(empleado=empleado)

    return render(request, 'empleado/panel_administrador.html', {
        'data_por_empleado': data_por_empleado
    })


def gracias(request):
    empleado_id = request.session.get('empleado_id')
    tipo_evento = request.session.get('tipo_evento')

    if empleado_id:
        empleado = Empleado.objects.get(id=empleado_id)
        eventos = EventosAsistencia.objects.filter(empleado=empleado).order_by('-id')[:2]

        entrada = None
        salida = None
        for evento in eventos:
            if evento.tipo == 'salida' and not salida:
                salida = evento
            elif evento.tipo == 'entrada' and not entrada:
                entrada = evento

        resumen = ""
        if tipo_evento == 'entrada':
            if entrada:
                resumen = f"¡Bienvenido/a, {empleado.nombre}! Tu entrada fue registrada con éxito."
            else:
                resumen = f"{empleado.nombre}, no se encontró un registro de entrada reciente."

        elif tipo_evento == 'salida':
            if entrada and salida:
             
                h_entrada = entrada.hora.hour
                h_salida = salida.hora.hour

                
                if salida.fecha > entrada.fecha:
                    horas_trabajadas = (24 - h_entrada) + h_salida
                else:
                    horas_trabajadas = max(h_salida - h_entrada, 0)

               
                cargo = empleado.cargo.lower()
                if cargo == "mesero":
                    tarifa = 13000
                elif cargo == "logístico":
                    tarifa = 10000
                else:
                    tarifa = 0

                pago_estimado = round(horas_trabajadas * tarifa)

                resumen = (
                    f"{empleado.nombre}, estos fueron tus últimos registros:<br>"
                    f"Cargo: {empleado.cargo}<br>"
                    f"➡ Entrada: {entrada.fecha} a las {entrada.hora.strftime('%I:%M:%S %p')}<br>"
                    f"⬅ Salida: {salida.fecha} a las {salida.hora.strftime('%I:%M:%S %p')}<br><br>"
                    f"💰 Valor estimado por el día: <strong>${pago_estimado:,.0f}</strong>"
                )
            else:
                resumen = f"{empleado.nombre}, no se encontraron registros completos de entrada y salida."
        else:
            resumen = "Tipo de evento no identificado."
    else:
        resumen = "No se encontró información del empleado."

    return render(request, 'empleado/gracias.html', {'resumen': resumen})


def historial_asistencia(request):
    empleado_id = request.session.get('empleado_id')
    if not empleado_id:
        return redirect('inicio')

    empleado = Empleado.objects.get(id=empleado_id)
    registros = EventosAsistencia.objects.filter(empleado=empleado).order_by('-fecha', '-hora')

    return render(request, 'empleado/historial.html', {
        'empleado': empleado,
        'registros': registros
    })

