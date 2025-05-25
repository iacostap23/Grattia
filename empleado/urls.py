from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),  
    path('inicio/', views.inicio, name='inicio'),
    path('login_facial/', views.login_facial, name='login_facial'),
    path('video_feed/', views.video_feed, name='video_feed'),
    path('validar_rostro/', views.validar_rostro, name='validar_rostro'),
    path('gracias/', views.gracias, name='gracias'), 
    path('historial/', views.historial_asistencia, name='historial_asistencia'),
    path('panel_administrador/', views.panel_administrador, name='panel_administrador'),
]
