import streamlit as st
import os
from tempfile import NamedTemporaryFile

from ProgramaLlaves import (
    procesar_imagen_unica, 
    buscar_llave_en_bd, 
    guardar_llave_completa,
    guardar_usuario_en_bd,
    verificar_login_usuario,
    verificar_hay_ubicaciones,
    obtener_lista_ubicaciones,
    guardar_ubicacion_en_bd
)

# =============================================================================
# CONFIGURACIÓN GENERAL
# =============================================================================
st.set_page_config(page_title="Bóveda Biométrica", page_icon="🔑", layout="centered")

DIRECTORIO_IMG = "boveda_imagenes"
os.makedirs(DIRECTORIO_IMG, exist_ok=True)

def guardar_temp(archivo_subido):
    """Guarda un archivo subido en memoria temporal y retorna su ruta física."""
    with NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
        tmp.write(archivo_subido.getvalue())
        return tmp.name

# =============================================================================
# GESTIÓN DE SESIÓN Y AUTENTICACIÓN
# =============================================================================
if 'logueado' not in st.session_state:
    st.session_state['logueado'] = False
    st.session_state['datos_usuario'] = None

if not st.session_state['logueado']:
    st.image("https://cdn-icons-png.flaticon.com/512/2838/2838332.png", width=80)
    st.title("Acceso al Sistema")
    st.markdown("Identifícate para acceder a tu bóveda de llaves personal.")
    
    tab_login, tab_registro = st.tabs(["🔑 Iniciar Sesión", "📝 Nuevo Usuario"])
    
    with tab_login:
        with st.form("form_login"):
            log_nom = st.text_input("Nombre")
            log_ape = st.text_input("Apellido")
            log_pass = st.text_input("Contraseña", type="password")
            btn_login = st.form_submit_button("Entrar", type="primary", use_container_width=True)
            
            if btn_login:
                if verificar_login_usuario(log_nom, log_ape, log_pass):
                    st.session_state['logueado'] = True
                    st.session_state['datos_usuario'] = {'nombre': log_nom, 'apellido': log_ape, 'pass': log_pass}
                    st.rerun()
                else:
                    st.error("⛔ Credenciales incorrectas o usuario no registrado.")
                    
    with tab_registro:
        with st.form("form_registro"):
            reg_nom = st.text_input("Nombre")
            reg_ape = st.text_input("Apellido")
            reg_pass = st.text_input("Contraseña", type="password")
            btn_registro = st.form_submit_button("Registrarse y Entrar", type="primary", use_container_width=True)
            
            if btn_registro:
                if reg_nom and reg_ape and reg_pass:
                    if guardar_usuario_en_bd(reg_nom, reg_ape, reg_pass):
                        st.session_state['logueado'] = True
                        st.session_state['datos_usuario'] = {'nombre': reg_nom, 'apellido': reg_ape, 'pass': reg_pass}
                        st.success("Usuario creado con éxito. Entrando...")
                        st.rerun()
                    else:
                        st.error("Error al crear el usuario en la base de datos.")
                else:
                    st.warning("Todos los campos son obligatorios.")

# =============================================================================
# APLICACIÓN PRINCIPAL
# =============================================================================
else:
    st.sidebar.image("https://cdn-icons-png.flaticon.com/512/2838/2838332.png", width=100)
    st.sidebar.title(f"Hola, {st.session_state['datos_usuario']['nombre']}")
    modo = st.sidebar.radio("Navegación:", ["🔍 Identificar Llave", "🛠️ Registrar Llave", "📍 Guardar Ubicación"])
    st.sidebar.markdown("---")
    
    if st.sidebar.button("🚪 Cerrar Sesión"):
        st.session_state['logueado'] = False
        st.session_state['datos_usuario'] = None
        st.rerun()

    # -------------------------------------------------------------------------
    # PANTALLA 1: IDENTIFICACIÓN BIOMÉTRICA
    # -------------------------------------------------------------------------
    if modo == "🔍 Identificar Llave":
        st.title("🔍 Identificación Biométrica")
        st.markdown("Sube una foto de la llave. El sistema solo buscará coincidencias en **tus llaves registradas**.")
        st.divider()

        archivo = st.file_uploader("Selecciona la imagen de la llave", type=["jpg", "jpeg", "png"])
        
        if archivo is not None:
            col_izq, col_der = st.columns([1, 1.5], gap="large")
            
            with col_izq:
                st.markdown("### Escáner Óptico")
                st.image(archivo, caption="Muestra capturada", use_container_width=True)
                boton_analizar = st.button("Iniciar Análisis", type="primary", use_container_width=True)

            with col_der:
                st.markdown("### Resultados")
                if boton_analizar:
                    with st.spinner("Comparando con tu base de datos..."):
                        ruta_temp = guardar_temp(archivo)
                        vector = procesar_imagen_unica(ruta_temp)
                        
                        if vector is not None:
                            resultados = buscar_llave_en_bd(vector, st.session_state['datos_usuario'])
                            
                            if resultados:
                                st.success("✅ Búsqueda completada con éxito.")
                                st.subheader("Top Coincidencias")
                                
                                for i, fila in enumerate(resultados):
                                    nombre = fila[0]
                                    calle = fila[1]
                                    piso = fila[2]
                                    ciudad = fila[3]
                                    similitud = float(fila[4])
                                    
                                    col_texto, col_boton = st.columns([4, 1])
                                    
                                    with col_texto:
                                        info_puerta = f"({calle}, Piso {piso} - {ciudad})"
                                        if i == 0 and similitud >= 99.00:
                                            st.success(f"**#1 {nombre}** {info_puerta}\n\nSimilitud: {similitud:.2f}% 🟢")
                                        elif similitud >= 91.00:
                                            st.warning(f"**#{i+1} {nombre}** {info_puerta}\n\nSimilitud: {similitud:.2f}% 🟡")
                                        else:
                                            st.error(f"**#{i+1} {nombre}** {info_puerta}\n\nSimilitud: {similitud:.2f}% ⛔")
                                    
                                    with col_boton:
                                        ruta_img_local = os.path.join(DIRECTORIO_IMG, f"{nombre}.jpg")
                                        if os.path.exists(ruta_img_local):
                                            with st.popover("👁️ Ver"):
                                                st.image(ruta_img_local, caption=nombre, use_container_width=True)
                            else:
                                st.error("No se encontró ninguna llave tuya que se parezca a esta.")
                        else:
                            st.error("Error: El sistema no pudo procesar la silueta.")
                        os.remove(ruta_temp)
                else:
                    st.info("👈 Presiona el botón para iniciar la comparativa.")

    # -------------------------------------------------------------------------
    # PANTALLA 2: REGISTRO DE LLAVES
    # -------------------------------------------------------------------------
    elif modo == "🛠️ Registrar Llave":
        st.title("🛠️ Alta en Bóveda")
        
        if not verificar_hay_ubicaciones():
            st.warning("⚠️ **Sistema Bloqueado:** No puedes registrar llaves porque no hay ninguna ubicación física creada en la base de datos.")
            st.info("👉 Ve a la pestaña **📍 Guardar Ubicación** en el menú lateral para crear la primera.")
        else:
            st.markdown("Sube una o varias imágenes para registrarlas. Debes asignarlas a una ubicación existente.")
            
            ubicaciones_raw = obtener_lista_ubicaciones()
            diccionario_ubicaciones = {}
            lista_opciones = []
            
            for ubi in ubicaciones_raw:
                ciudad, cp, piso, calle = ubi
                etiqueta = f"{calle}, Piso {piso} - {ciudad} (CP: {cp})"
                lista_opciones.append(etiqueta)
                diccionario_ubicaciones[etiqueta] = {'ciudad': ciudad, 'cp': cp, 'piso': piso, 'calle': calle}

            archivos = st.file_uploader("Selecciona las imágenes", type=["jpg", "jpeg", "png"], accept_multiple_files=True)
            
            if archivos:
                st.markdown("### Configuración de Registros")
                datos_inputs = []
                
                for i, archivo in enumerate(archivos):
                    col1, col2 = st.columns([1, 2])
                    with col1:
                        st.image(archivo, use_container_width=True)
                    with col2:
                        n_defecto = os.path.splitext(archivo.name)[0]
                        nombre_llave = st.text_input(f"Identificador de la llave {i+1}:", value=n_defecto, key=f"nombre_{i}")
                        ubi_seleccionada = st.selectbox("¿A qué ubicación pertenece?", lista_opciones, key=f"ubi_{i}")
                        
                        datos_inputs.append({
                            'nombre': nombre_llave,
                            'datos_ubicacion': diccionario_ubicaciones[ubi_seleccionada]
                        })
                        
                st.divider()
                
                if st.button("Registrar en Base de Datos", type="primary"):
                    barra_progreso = st.progress(0)
                    exitos = 0
                    
                    for i, archivo in enumerate(archivos):
                        config_actual = datos_inputs[i]
                        ruta_temp = guardar_temp(archivo)
                        vector = procesar_imagen_unica(ruta_temp)
                        
                        if vector is not None:
                            guardado_ok = guardar_llave_completa(
                                st.session_state['datos_usuario'], 
                                config_actual['datos_ubicacion'], 
                                {'nombre': config_actual['nombre']}, 
                                vector
                            )
                            
                            if guardado_ok:
                                ruta_guardado_local = os.path.join(DIRECTORIO_IMG, f"{config_actual['nombre']}.jpg")
                                with open(ruta_guardado_local, "wb") as f:
                                    f.write(archivo.getvalue())
                                exitos += 1
                        
                        os.remove(ruta_temp)
                        barra_progreso.progress((i + 1) / len(archivos))
                        
                    if exitos == len(archivos):
                        st.balloons()
                        st.success(f"🎉 ¡Completado! {exitos} llaves vinculadas a tu cuenta correctamente.")
                    else:
                        st.warning(f"⚠️ Se registraron {exitos} de {len(archivos)} llaves. Algunas pudieron fallar debido a un escaneo defectuoso o a un intento de duplicado.")

    # -------------------------------------------------------------------------
    # PANTALLA 3: GUARDAR UBICACIÓN
    # -------------------------------------------------------------------------
    elif modo == "📍 Guardar Ubicación":
        st.title("📍 Nueva Ubicación")
        st.markdown("Registra un edificio, casa, almacén o cobertizo. Una vez guardado, podrás asignarle llaves.")
        
        col_u1, col_u2 = st.columns(2)
        with col_u1:
            calle = st.text_input("Calle / Dirección", max_chars=50)
            ciudad = st.text_input("Ciudad (máx 15 char)", max_chars=15)
            
            opciones_tipo = ["Casa", "Chalet", "Apartamento", "Armario", "Almacén", "Cobertizo", "Otros"]
            tipo_seleccion = st.selectbox("Tipo de ubicación", opciones_tipo)
            
            if tipo_seleccion == "Otros":
                tipo_final = st.text_input("Especifica el tipo de ubicación (máx 30 char)", max_chars=30)
            else:
                tipo_final = tipo_seleccion
                
        with col_u2:
            piso = st.number_input("Piso / Nivel (0 si no tiene)", value=0, step=1)
            cp = st.number_input("Código Postal", value=28000, step=1)
            descripcion = st.text_area("Descripción (Opcional)")
            
        st.divider()
        btn_guardar_ubi = st.button("Añadir Ubicación", type="primary", use_container_width=True)
        
        if btn_guardar_ubi:
            if calle and ciudad and tipo_final:
                if guardar_ubicacion_en_bd(calle, tipo_final, ciudad, descripcion, int(cp), int(piso)):
                    st.success(f"La ubicación '{calle}, Piso {piso} - {ciudad}' se ha guardado correctamente como: {tipo_final}.")
                else:
                    st.error("Hubo un error en la base de datos (es posible que esa ubicación exacta ya exista).")
            else:
                st.warning("La Calle, la Ciudad y el Tipo son campos obligatorios.")