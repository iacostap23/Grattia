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

def home(request):
    return render(request, 'empleado/home.html')

def validar_empleado(request):
    if request.method == 'POST':
        correo = request.POST.get('correo')
        cedula = request.POST.get('cedula')
        cargo = request.POST.get('cargo')

        try:
            empleado = Empleado.objects.get(correo=correo, cedula=cedula, cargo=cargo)
            request.session['empleado_id'] = empleado.id

            if empleado.rostro_registrado:
                messages.info(request, "Bienvenido. Vamos a validar tu rostro.")
                return redirect('login_facial')
            else:
                messages.success(request, "Validación exitosa. Ahora registra tu rostro.")
                return redirect('registro')

        except Empleado.DoesNotExist:
            messages.error(request, "Los datos no coinciden con ningún empleado de Grattia.")
            return redirect('home')

def registro(request):
    if request.method == 'POST':
        empleado_id = request.session.get('empleado_id')
        if not empleado_id:
            messages.error(request, "No hay sesión activa.")
            return redirect('home')

        empleado = Empleado.objects.get(id=empleado_id)

        if empleado.rostro_registrado:
            messages.info(request, "Ya tienes un rostro registrado. Vamos a verificarlo.")
            return redirect('login_facial')

        cam = cv2.VideoCapture(0)
        ret, frame = cam.read()
        cam.release()

        if not ret:
            messages.error(request, "No se pudo acceder a la cámara.")
            return redirect('registro')

        face_locations = face_recognition.face_locations(frame)

        if face_locations:
            top, right, bottom, left = face_locations[0]
            rostro = frame[top:bottom, left:right]

            user_img_path = os.path.join(user_dir, f"{empleado.id}.jpg")
            cv2.imwrite(user_img_path, rostro)

            face_encoding = face_recognition.face_encodings(frame, [face_locations[0]])[0]
            encoding_path = os.path.join(encoding_dir, f"{empleado.id}.pkl")
            with open(encoding_path, 'wb') as f:
                pickle.dump(face_encoding, f)

            empleado.rostro_registrado = True
            empleado.save()

            hoy = datetime.now().date()
            ahora = datetime.now().time()

            EventosAsistencia.objects.create(
                empleado=empleado,
                fecha=hoy,
                hora_entrada=ahora
            )

            messages.success(request, f'Registro facial exitoso. Tu hora de entrada fue {ahora.strftime("%H:%M:%S")}')
            return redirect('home')
        else:
            messages.error(request, "No se detectó ningún rostro.")

    return render(request, 'empleado/registro.html')

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

                    hoy = datetime.now().date()
                    ahora = datetime.now().time()

                    registro, creado = EventosAsistencia.objects.get_or_create(empleado=empleado, fecha=hoy)

                    if creado or not registro.hora_entrada:
                        registro.hora_entrada = ahora
                        mensaje = f"{empleado.nombre}, el registro facial fue exitoso. Tu hora de entrada fue {registro.hora_entrada.strftime('%H:%M:%S')}."
                    elif not registro.hora_salida:
                        registro.hora_salida = ahora
                        mensaje = f"{empleado.nombre}, tu hora de salida fue {registro.hora_salida.strftime('%H:%M:%S')}."
                    else:
                        mensaje = f"{empleado.nombre}, ya registraste entrada y salida para hoy."

                    registro.save()
                    messages.success(request, mensaje)
                    request.session['empleado_id'] = empleado.id
                    return redirect('home')

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
def guardar_rostro(request):
    if request.method == 'POST':
        empleado_id = request.session.get('empleado_id')
        if not empleado_id:
            return JsonResponse({'success': False, 'message': 'No hay sesión activa'})

        data_url = request.POST.get('image')
        if not data_url:
            return JsonResponse({'success': False, 'message': 'No se recibió imagen'})

        header, encoded = data_url.split(',', 1)
        img_data = base64.b64decode(encoded)
        np_arr = np.frombuffer(img_data, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        face_locations = face_recognition.face_locations(frame)
        if not face_locations:
            return JsonResponse({'success': False, 'message': 'No se detectó ningún rostro'})

        empleado = Empleado.objects.get(id=empleado_id)

        top, right, bottom, left = face_locations[0]
        rostro = frame[top:bottom, left:right]

        user_img_path = os.path.join(user_dir, f"{empleado.id}.jpg")
        cv2.imwrite(user_img_path, rostro)

        face_encoding = face_recognition.face_encodings(frame, [face_locations[0]])[0]
        encoding_path = os.path.join(encoding_dir, f"{empleado.id}.pkl")
        with open(encoding_path, 'wb') as f:
            pickle.dump(face_encoding, f)

        empleado.rostro_registrado = True
        empleado.save()

        return JsonResponse({'success': True, 'message': f'Registro exitoso para {empleado.nombre}'})

    return JsonResponse({'success': False, 'message': 'Método no permitido'})

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
                    username = filename.replace('.pkl', '')
                    try:
                        empleado = Empleado.objects.get(id=int(username))
                        return JsonResponse({'success': True, 'message': f'Bienvenido, {empleado.nombre}'})
                    except (ValueError, Empleado.DoesNotExist):
                        correo = username.replace("usuario_", "") + "@grattia.edu.co"
                        try:
                            empleado = Empleado.objects.get(correo=correo)
                            return JsonResponse({'success': True, 'message': f'Bienvenido, {empleado.nombre}'})
                        except Empleado.DoesNotExist:
                            return JsonResponse({'success': False, 'message': 'Empleado no encontrado en la base de datos.'})

        return JsonResponse({'success': False, 'message': 'No coincide con ningún rostro registrado.'})

@require_POST
def cerrar_sesion(request):
    request.session.flush()
    messages.success(request, "Sesión cerrada exitosamente.")
    return redirect('home')

