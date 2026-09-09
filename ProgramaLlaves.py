import cv2
import numpy as np
import psycopg2
import math
import os
import hashlib

# --- CONFIGURACIÓN DE BASE DE DATOS ---
DB_HOST = "TU_HOST"
DB_PORT = "TU_PUERTO"
DB_NAME = "TU_BASE_DE_DATOS"
DB_USER = "TU_USUARIO"
DB_PASS = "TU_CONTRASEÑA"

# =============================================================================
# BLOQUE 2: MOTOR TOPOGRÁFICO OpenCV
# =============================================================================
DIRECTORIO_BASE = os.path.dirname(os.path.abspath(__file__))
carpeta_adn = os.path.join(DIRECTORIO_BASE, "ADN_llaves_beta")
carpeta_bin = os.path.join(DIRECTORIO_BASE, "llaves_bin_beta")

if not os.path.exists(carpeta_adn): os.makedirs(carpeta_adn)
if not os.path.exists(carpeta_bin): os.makedirs(carpeta_bin)

def procesar_imagen_unica(ruta):
    img = cv2.imread(ruta, cv2.IMREAD_GRAYSCALE)
    if img is None: return None

    _, umbral = cv2.threshold(img, 127, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    contornos, _ = cv2.findContours(umbral, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contornos: return None
    
    contorno_max = max(contornos, key=cv2.contourArea)

    [vx, vy, x, y] = cv2.fitLine(contorno_max, cv2.DIST_L2, 0, 0.01, 0.01)
    
    vx_val = float(vx[0])
    vy_val = float(vy[0])
    angle_rad = math.atan2(vy_val, vx_val)
    angle_deg = math.degrees(angle_rad)

    if angle_deg < -45 or angle_deg > 45:
        angle_deg -= 90

    (h, w) = img.shape[:2]
    centro = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(centro, angle_deg, 1.0)
    img_rotada = cv2.warpAffine(umbral, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=0)

    contornos_rotados, _ = cv2.findContours(img_rotada, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contorno_recto = max(contornos_rotados, key=cv2.contourArea)
    x_rect, y_rect, w_rect, h_rect = cv2.boundingRect(contorno_recto)
    
    img_recortada = img_rotada[y_rect:y_rect+h_rect, x_rect:x_rect+w_rect]

    h_rec, w_rec = img_recortada.shape
    perfil_dientes = []
    
    for y in range(h_rec):
        fila = img_recortada[y, :]
        puntos_blancos = np.where(fila > 0)[0]
        if len(puntos_blancos) > 0:
            ancho = puntos_blancos[-1] - puntos_blancos[0]
            perfil_dientes.append(ancho)
        else:
            perfil_dientes.append(0)
    
    perfil_array = np.array(perfil_dientes, dtype=float)
    anchura_media = np.mean(perfil_array)
    
    inicio_sierra = 0
    for i in range(10, len(perfil_array)): 
        if perfil_array[i] < anchura_media and perfil_array[i-5] >= anchura_media:
            inicio_sierra = i
            break
    
    if inicio_sierra == 0 or inicio_sierra > len(perfil_array) * 0.5:
        inicio_sierra = int(len(perfil_array) * 0.3)

    perfil_sierra = perfil_array[inicio_sierra:]
    
    if len(perfil_sierra) == 0: return None
    max_sierra = np.max(perfil_sierra)
    min_sierra = np.min(perfil_sierra)
    
    if max_sierra == min_sierra: return None
    perfil_normalizado = (perfil_sierra - min_sierra) / (max_sierra - min_sierra)

    puntos_originales = np.linspace(0, 1, len(perfil_normalizado))
    puntos_objetivo = np.linspace(0, 1, 2000)
    adn_vector = np.interp(puntos_objetivo, puntos_originales, perfil_normalizado)

    nombre_base = os.path.basename(ruta)
    nombre_sin_ext = os.path.splitext(nombre_base)[0]
    
    ruta_bin = os.path.join(carpeta_bin, f"BIN_{nombre_base}")
    cv2.imwrite(ruta_bin, img_recortada[inicio_sierra:, :])
    
    ruta_csv = os.path.join(carpeta_adn, f"ADN_{nombre_sin_ext}.csv")
    np.savetxt(ruta_csv, adn_vector, fmt="%.6f", delimiter=",")
    
    img_color = cv2.imread(ruta)
    if img_color is not None:
        M_color = cv2.getRotationMatrix2D(centro, angle_deg, 1.0)
        img_color_rotada = cv2.warpAffine(img_color, M_color, (w, h), borderValue=(255, 255, 255))
        
        cv2.rectangle(img_color_rotada, (x_rect, y_rect), (x_rect + w_rect, y_rect + h_rect), (255, 0, 0), 2)
        linea_corte_y = y_rect + inicio_sierra
        cv2.line(img_color_rotada, (x_rect, linea_corte_y), (x_rect + w_rect, linea_corte_y), (255, 0, 255), 2)
        eje_x = x_rect + (w_rect // 2)
        cv2.line(img_color_rotada, (eje_x, 0), (eje_x, h), (0, 255, 0), 1)

        ruta_debug = os.path.join(carpeta_bin, f"DEBUG_{nombre_base}")
        cv2.imwrite(ruta_debug, img_color_rotada)

    return np.array(adn_vector)

# =============================================================================
# BLOQUE 3: MOTOR DE BASE DE DATOS
# =============================================================================
from pgvector.psycopg2 import register_vector

def generar_hash_sierra(vector_numpy):
    """Genera un hash SHA-256 a partir del vector característico."""
    vector_texto = ",".join(f"{float(x):.6f}" for x in vector_numpy)
    hash_objeto = hashlib.sha256(vector_texto.encode('utf-8'))
    return hash_objeto.hexdigest()

def obtener_conexion():
    conexion = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS)
    register_vector(conexion)
    return conexion

def verificar_hay_ubicaciones():
    """Comprueba si existe al menos una ubicación registrada en el sistema."""
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        cursor.execute('SELECT COUNT(*) FROM "Almacen llaves"."Ubicación";')
        cantidad = cursor.fetchone()[0]
        cursor.close()
        conexion.close()
        return cantidad > 0
    except Exception as e:
        print(f"[ERROR] Verificación de ubicaciones: {e}")
        return False

def obtener_lista_ubicaciones():
    """Obtiene las ubicaciones disponibles en la base de datos."""
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        cursor.execute('SELECT ciudad, "código_postal", "Piso", "Calle" FROM "Almacen llaves"."Ubicación";')
        resultados = cursor.fetchall()
        cursor.close()
        conexion.close()
        return resultados
    except Exception as e:
        print(f"[ERROR] Carga de ubicaciones: {e}")
        return []

def guardar_ubicacion_en_bd(calle, tipo, ciudad, descripcion, cp, piso):
    """Registra una nueva ubicación física."""
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        consulta = """
            INSERT INTO "Almacen llaves"."Ubicación" 
            ("Calle", tipo, ciudad, "descripción", "código_postal", "Piso")
            VALUES (%s, %s, %s, %s, %s, %s);
        """
        cursor.execute(consulta, (calle, tipo, ciudad, descripcion, cp, piso))
        conexion.commit()
        cursor.close()
        conexion.close()
        return True
    except Exception as e:
        print(f"[ERROR] Creación de ubicación: {e}")
        return False
        
def guardar_usuario_en_bd(nombre, apellido, password):
    """Registra un nuevo usuario en el sistema."""
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        consulta = """
            INSERT INTO "Almacen llaves"."Usuario" (nombre, apellido, "contraseña")
            VALUES (%s, %s, %s)
            ON CONFLICT (nombre, apellido, "contraseña") DO NOTHING;
        """
        cursor.execute(consulta, (nombre, apellido, password))
        conexion.commit()
        cursor.close()
        conexion.close()
        return True
    except Exception as e:
        print(f"[ERROR] Creación de usuario: {e}")
        return False

def verificar_login_usuario(nombre, apellido, password):
    """Autentica a un usuario."""
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        
        consulta = """
            SELECT COUNT(*) FROM "Almacen llaves"."Usuario"
            WHERE nombre = %s AND apellido = %s AND "contraseña" = %s;
        """
        cursor.execute(consulta, (nombre, apellido, password))
        existe = cursor.fetchone()[0]
        
        cursor.close()
        conexion.close()
        
        return existe > 0
    except Exception as e:
        print(f"[ERROR] Autenticación: {e}")
        return False

def guardar_llave_completa(datos_usuario, datos_ubicacion, datos_llave, vector_numpy):
    """Registra la llave y sus relaciones en la base de datos."""
    exito_user = guardar_usuario_en_bd(datos_usuario['nombre'], datos_usuario['apellido'], datos_usuario['pass'])
    if not exito_user: return False

    hash_sierra = generar_hash_sierra(vector_numpy)

    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        
        consulta = """
            INSERT INTO "Almacen llaves"."Llave" (
                nombre_llave, url_imagen, 
                "nombre_Usuario", "apellido_Usuario", "contraseña_Usuario",
                sierra, sierra_hash,
                "ciudad_Ubicación", "código_postal_Ubicación", "Piso_Ubicación", "Calle_Ubicación"
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """
        
        valores = (
            datos_llave['nombre'], "", 
            datos_usuario['nombre'], datos_usuario['apellido'], datos_usuario['pass'],
            vector_numpy, hash_sierra,
            datos_ubicacion['ciudad'], datos_ubicacion['cp'], datos_ubicacion['piso'], datos_ubicacion['calle']
        )
        
        cursor.execute(consulta, valores)
        conexion.commit()
        cursor.close()
        conexion.close()
        return True
        
    except psycopg2.errors.UniqueViolation:
        print("[AVISO] La llave ya existe en la base de datos.")
        return False
    except Exception as e:
        print(f"[ERROR] Registro de llave: {e}")
        return False

def buscar_llave_en_bd(vector_numpy, datos_usuario):
    """Busca similitudes vectoriales asociadas al usuario autenticado."""
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        
        consulta = """
            SELECT 
                nombre_llave,
                "Calle_Ubicación", "Piso_Ubicación", "ciudad_Ubicación",
                (1 - (sierra <=> %s::vector)) * 100 AS porcentaje_similitud
            FROM "Almacen llaves"."Llave"
            WHERE "nombre_Usuario" = %s 
              AND "apellido_Usuario" = %s 
              AND "contraseña_Usuario" = %s
            ORDER BY sierra <=> %s::vector 
            LIMIT 5;
        """
        
        valores = (
            vector_numpy, 
            datos_usuario['nombre'], datos_usuario['apellido'], datos_usuario['pass'],
            vector_numpy
        )
        
        cursor.execute(consulta, valores)
        resultados = cursor.fetchall() 
        
        cursor.close()
        conexion.close()
        return resultados 
    except Exception as e:
        print(f"[ERROR] Búsqueda vectorial: {e}")
        return None