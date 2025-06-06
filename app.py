
# filename: app.py
from flask import Flask, request, jsonify, redirect, render_template, session, send_file
from flask_cors import CORS
from supabase import create_client, Client
from datetime import datetime, timedelta
from pytz import timezone
from collections import defaultdict  # <-- Añadido para totales
import pandas as pd
from io import BytesIO
import os
import logging  # Added for potential logging later

app = Flask(__name__)
# Load secret key from environment variable for security
# Use a strong, randomly generated key
app.secret_key = os.getenv("FLASK_APP_SECRET_KEY", "supersecreto123")  # Provide a default only for local dev if needed, but ideally require it
CORS(app)

# Configure basic logging
logging.basicConfig(level=logging.INFO)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Ensure Supabase credentials are set
if not SUPABASE_URL or not SUPABASE_KEY:
    logging.error("Supabase URL or Key environment variables not set.")
    # Depending on your setup, you might want to exit or handle this differently
    # For now, we'll proceed but Supabase calls will fail.
    supabase = None
else:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Load admin password from environment variable for security
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "@dmin123")  # Use a strong password

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        entered_password = request.form.get("password")
        if entered_password and entered_password == ADMIN_PASSWORD:
            session["admin"] = True
            logging.info("Admin login successful.")
            return redirect("/admin")
        else:
            logging.warning("Failed admin login attempt.")
            # Provide a generic error message
            return render_template("login.html", error="Contraseña incorrecta")
    return render_template("login.html")

@app.route("/admin")
def admin():
    if not session.get("admin"):
        logging.warning("Unauthorized attempt to access /admin.")
        return redirect("/login")
    return render_template("admin.html")

@app.route("/submit", methods=["POST"])
def submit():
    if not supabase:
        return jsonify({"status": "error", "message": "Backend database not configured."}), 500

    data = request.json
    nombre = data.get("nombre")
    pin = data.get("pin")
    accion = data.get("accion")
    proyecto = data.get("proyecto")  # <-- Get the selected project (might be None or empty)

    # Basic Input Validation
    if not nombre or not pin or not accion:
        logging.warning(f"Submit attempt with missing data: name={bool(nombre)}, pin={bool(pin)}, action={bool(accion)}")
        return jsonify({"status": "error", "message": "Nombre, PIN, y acción son requeridos."}), 400

    if not pin.isdigit():
        logging.warning(f"Submit attempt with non-numeric PIN from user: {nombre}")
        return jsonify({"status": "error", "message": "PIN debe ser numérico."}), 400

    # Handle empty project selection - store as None (NULL) in the database
    if not proyecto:  # Checks for None or empty string ""
        proyecto_db = None
    else:
        proyecto_db = proyecto

    zona = timezone("America/Chicago")
    now = datetime.now(zona)
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    fecha = now.strftime("%Y-%m-%d")
    hora = now.strftime("%H:%M:%S")

    try:
        empleados = supabase.table("empleados").select("id").eq("nombre", nombre).eq("pin", pin).execute().data
        if not empleados:
            logging.warning(f"Submit attempt with incorrect PIN for user: {nombre}")
            return jsonify({"status": "error", "message": "Nombre o PIN incorrecto."}), 401

        # Insert the record including the project, fecha y hora por separado
        insert_response = supabase.table("registros").insert({
            "nombre": nombre,
            "accion": accion,
            "timestamp": timestamp,
            "fecha": fecha,
            "hora": hora,
            "proyecto": proyecto_db  # <-- Add project to the insert data
        }).execute()

        logging.info(f"Record submitted successfully for user: {nombre}, action: {accion}, project: {proyecto_db}")
        return jsonify({"status": "success", "message": f"{accion} registrado para {nombre}"})

    except Exception as e:
        logging.error(f"Error during submit for user {nombre}: {str(e)}")
        return jsonify({"status": "error", "message": "Error interno del servidor al procesar la solicitud."}), 500


@app.route("/agregar-empleado", methods=["POST"])
def agregar_empleado():
    if not session.get("admin"):
        return redirect("/login")
    if not supabase:
        return "Backend database not configured.", 500

    nombre = request.form.get("nombre")
    pin = request.form.get("pin")

    if not nombre or not pin:
        logging.warning("Add employee attempt with missing name or PIN.")
        # Ideally, redirect back to admin page with an error message
        return "Nombre y PIN son requeridos.", 400

    # Optional: Add PIN validation
    if not pin.isdigit():
        logging.warning(f"Add employee attempt with non-numeric PIN for user: {nombre}")
        # Redirect back with error
        return "PIN debe ser numérico.", 400

    try:
        # Optional: Check if employee already exists
        existing = supabase.table("empleados").select("id").eq("nombre", nombre).execute().data
        if existing:
            logging.warning(f"Attempt to add duplicate employee: {nombre}")
            # Redirect back with error
            return f"Empleado '{nombre}' ya existe.", 409  # 409 Conflict

        supabase.table("empleados").insert({"nombre": nombre, "pin": pin}).execute()
        logging.info(f"Employee added: {nombre}")
        return redirect("/admin?success=Empleado agregado")  # Redirect with success message
    except Exception as e:
        logging.error(f"Error adding employee {nombre}: {str(e)}")
        # Redirect back with error message
        return f"Error inesperado al agregar empleado: {str(e)}", 500


@app.route("/empleados")
def empleados():
    if not session.get("admin"):
        return redirect("/login")
    if not supabase:
        return jsonify([])  # Return empty list if DB not configured

    try:
        data = supabase.table("empleados").select("*").order("nombre", desc=False).execute().data
        return jsonify(data)
    except Exception as e:
        logging.error(f"Error fetching employees: {str(e)}")
        return jsonify({"error": "Could not fetch employees"}), 500


@app.route("/eliminar-empleado", methods=["POST"])
def eliminar_empleado():
    if not session.get("admin"):
        return jsonify({"status": "error", "message": "Unauthorized"}), 403
    if not supabase:
        return jsonify({"status": "error", "message": "Backend database not configured."}), 500

    nombre = request.json.get("nombre")
    if not nombre:
        return jsonify({"status": "error", "message": "Nombre es requerido."}), 400

    try:
        # Also delete associated time records (optional, depends on requirements)
        # supabase.table("registros").delete().eq("nombre", nombre).execute()

        # Delete employee
        supabase.table("empleados").delete().eq("nombre", nombre).execute()
        logging.info(f"Employee deleted: {nombre}")
        return jsonify({"status": "success", "message": "Empleado eliminado"})
    except Exception as e:
        logging.error(f"Error deleting employee {nombre}: {str(e)}")
        return jsonify({"status": "error", "message": "Error interno al eliminar empleado."}), 500


# --- Project Routes ---

@app.route("/proyectos")
def proyectos():
    """Fetches all projects."""
    if not session.get("admin"):
        logging.warning("Unauthorized attempt to access /proyectos.")
        return redirect("/login")
    if not supabase:
        return jsonify([])  # Return empty list if DB not configured

    try:
        # Fetch projects ordered by name
        data = supabase.table("proyectos").select("*").order("nombre", desc=False).execute().data
        return jsonify(data)
    except Exception as e:
        logging.error(f"Error fetching projects: {str(e)}")
        return jsonify({"error": "Could not fetch projects"}), 500


@app.route("/agregar-proyecto", methods=["POST"])
def agregar_proyecto():
    """Adds a new project."""
    if not session.get("admin"):
        logging.warning("Unauthorized attempt to access /agregar-proyecto.")
        return redirect("/login")  # Or return 403 Forbidden
    if not supabase:
        return "Backend database not configured.", 500

    nombre_proyecto = request.form.get("nombre_proyecto")

    if not nombre_proyecto:
        logging.warning("Add project attempt with missing name.")
        # Redirect back to admin page with an error message
        # Ensure the redirect goes back to the projects tab eventually
        return redirect("/admin?error=Nombre del proyecto es requerido#proyectos")  # Redirect includes error and #hash

    try:
        # Check if project already exists
        existing = supabase.table("proyectos").select("id").eq("nombre", nombre_proyecto).execute().data
        if existing:
            logging.warning(f"Attempt to add duplicate project: {nombre_proyecto}")
            return redirect(f"/admin?error=Proyecto '{nombre_proyecto}' ya existe.#proyectos")  # Redirect with error

        supabase.table("proyectos").insert({"nombre": nombre_proyecto}).execute()
        logging.info(f"Project added: {nombre_proyecto}")
        return redirect("/admin?success=Proyecto agregado#proyectos")  # Redirect with success and #hash
    except Exception as e:
        logging.error(f"Error adding project {nombre_proyecto}: {str(e)}")
        return redirect(f"/admin?error=Error inesperado al agregar proyecto#proyectos")  # Redirect with error


@app.route("/eliminar-proyecto", methods=["POST"])
def eliminar_proyecto():
    """Deletes a project by name."""
    if not session.get("admin"):
        return jsonify({"status": "error", "message": "Unauthorized"}), 403
    if not supabase:
        return jsonify({"status": "error", "message": "Backend database not configured."}), 500

    nombre_proyecto = request.json.get("nombre")  # Expecting JSON body
    if not nombre_proyecto:
        return jsonify({"status": "error", "message": "Nombre del proyecto es requerido."}), 400

    try:
        # Delete project by name
        delete_result = supabase.table("proyectos").delete().eq("nombre", nombre_proyecto).execute()

        # Optional: Check if any rows were actually deleted
        # Note: Supabase delete response structure might vary, check docs if needed
        # if delete_result.count == 0: # Example check
        #     logging.warning(f"Attempt to delete non-existent project: {nombre_proyecto}")
        #     return jsonify({"status": "error", "message": "Proyecto no encontrado."}), 404

        logging.info(f"Project deleted: {nombre_proyecto}")
        return jsonify({"status": "success", "message": "Proyecto eliminado"})
    except Exception as e:
        logging.error(f"Error deleting project {nombre_proyecto}: {str(e)}")
        return jsonify({"status": "error", "message": "Error interno al eliminar proyecto."}), 500


@app.route("/get-proyectos-list")
def get_proyectos_list():
    """Fetches just project names for the dropdown."""
    # No admin check needed here, as this is for the public clock-in page
    if not supabase:
        return jsonify({"error": "Backend database not configured."}), 500

    try:
        # Fetch only the 'nombre' column, ordered by name
        data = supabase.table("proyectos").select("nombre").order("nombre", desc=False).execute().data
        # Extract just the names into a list
        project_names = [item["nombre"] for item in data]
        return jsonify(project_names)
    except Exception as e:
        logging.error(f"Error fetching project list: {str(e)}")
        return jsonify({"error": "Could not fetch project list"}), 500


@app.route("/registros")
def registros():
    if not session.get("admin"):
        return redirect("/login")
    if not supabase:
        return jsonify([])  # Return empty list if DB not configured

    try:
        data = supabase.table("registros").select("*").order("timestamp", desc=True).execute().data
        return jsonify(data)
    except Exception as e:
        logging.error(f"Error fetching records: {str(e)}")
        return jsonify({"error": "Could not fetch records"}), 500


@app.route("/estado")
def estado():
    if not supabase:
        return jsonify({"estado": "desconocido", "message": "Backend database not configured."})

    nombre = request.args.get("nombre")
    pin = request.args.get("pin")  # PIN is still required by this endpoint

    # Basic validation
    if not nombre or not pin:
        return jsonify({"estado": "desconocido", "message": "Nombre y PIN son requeridos para consultar estado."})

    try:
        # First, verify the PIN is correct for the given name
        empleados = supabase.table("empleados").select("id").eq("nombre", nombre).eq("pin", pin).execute().data
        if not empleados:
            logging.warning(f"Status check attempt with incorrect PIN for user: {nombre}")
            # Return a specific status or error to indicate invalid PIN vs. no records
            return jsonify({"estado": "pin_invalido"})

        # PIN is valid, now get the latest record
        registros = (
            supabase.table("registros")
            .select("accion")
            .eq("nombre", nombre)
            .order("timestamp", desc=True)
            .limit(1)
            .execute()
            .data
        )

        if not registros:
            return jsonify({"estado": "ninguno"})  # No records found for this user
        else:
            return jsonify({"estado": registros[0]["accion"]})  # Return last action

    except Exception as e:
        logging.error(f"Error fetching status for user {nombre}: {str(e)}")
        return jsonify({"estado": "error_interno"}), 500

@app.route("/exportar")
def exportar():
    if not session.get("admin"):
        return redirect("/login")
    if not supabase:
        return "Backend database not configured.", 500

    try:
        # --- 1) Leer todos los registros desde Supabase ---
        registros = (
            supabase.table("registros")
            .select("nombre, accion, timestamp, proyecto")
            .order("timestamp", desc=False)
            .execute()
            .data
        )
        if not isinstance(registros, list):
            logging.error(f"Respuesta inesperada de Supabase: {registros!r}")
            return "Error al generar archivo: formato inesperado de datos.", 500

        # --- 2) Construir DataFrame principal y separar fecha/hora ---
        df = pd.DataFrame(registros)
        if "timestamp" not in df.columns:
            return "Error: la columna 'timestamp' no existe en la tabla registros.", 500

        # Convertir 'timestamp' a datetime
        df["timestamp"] = pd.to_datetime(
            df["timestamp"], format="%Y-%m-%d %H:%M:%S", errors="coerce"
        )
        # Crear columnas 'fecha' y 'hora' a partir de 'timestamp'
        df["fecha"] = df["timestamp"].dt.strftime("%Y-%m-%d").fillna("")
        df["hora"] = df["timestamp"].dt.strftime("%H:%M:%S").fillna("")

        # --- 3) Calcular Totales Globales (por usuario) ---
        total_por_usuario = defaultdict(float)
        pendiente_entrada_global = {}

        # Recorremos cada fila en orden cronológico
        for _, row in df.iterrows():
            nombre = row["nombre"]
            accion = (row["accion"] or "").strip().lower()
            ts = row["timestamp"]

            if pd.isna(ts):
                continue

            if accion == "clock in":
                if pendiente_entrada_global.get(nombre) is None:
                    pendiente_entrada_global[nombre] = ts

            elif accion == "clock out":
                inicio = pendiente_entrada_global.get(nombre)
                if inicio is not None and ts > inicio:
                    total_por_usuario[nombre] += (ts - inicio).total_seconds()
                    pendiente_entrada_global[nombre] = None

        totales_list = []
        for nombre, segs in total_por_usuario.items():
            horas = round(segs / 3600, 2)
            totales_list.append({"nombre": nombre, "horas_trabajadas": horas})
        df_totales = pd.DataFrame(totales_list)

        # --- 4) Calcular Totales Semanales (por usuario + semana ISO) ---
        total_por_usuario_semana = defaultdict(float)
        pendiente_entrada_sem = {}

        for _, row in df.iterrows():
            nombre = row["nombre"]
            accion = (row["accion"] or "").strip().lower()
            ts = row["timestamp"]

            if pd.isna(ts):
                continue

            if accion == "clock in":
                if pendiente_entrada_sem.get(nombre) is None:
                    pendiente_entrada_sem[nombre] = ts

            elif accion == "clock out":
                inicio = pendiente_entrada_sem.get(nombre)
                if inicio is not None and ts > inicio:
                    delta_seg = (ts - inicio).total_seconds()
                    iso_year, iso_week, _ = inicio.isocalendar()
                    key = (nombre, iso_year, iso_week)
                    total_por_usuario_semana[key] += delta_seg
                    pendiente_entrada_sem[nombre] = None

        totales_semana_list = []
        for (nombre, year, week), segs in total_por_usuario_semana.items():
            horas = round(segs / 3600, 2)
            # Calcular rango de fechas: “Jun 2–8, 2025”
            lunes = datetime.fromisocalendar(year, week, 1)
            domingo = lunes + timedelta(days=6)
            mes_abrev = lunes.strftime("%b")   # ej. "Jun"
            dia_inicio = lunes.day             # ej. 2
            dia_fin = domingo.day              # ej. 8
            anio = lunes.year                  # ej. 2025
            semana_str = f"Semana {week} ({mes_abrev} {dia_inicio}–{dia_fin}, {anio})"
            totales_semana_list.append({
                "nombre": nombre,
                "semana": semana_str,
                "horas_trabajadas": horas
            })
        df_totales_semanal = pd.DataFrame(totales_semana_list)

        # --- 5) Calcular Totales Diarios (por usuario + fecha), con prorrateo si cruza medianoche ---
        total_por_usuario_fecha = defaultdict(float)
        pendiente_entrada_diaria = {}

        # Convertimos a lista de dicts para iterar con facilidad manteniendo orden cronológico
        records = df[["nombre", "accion", "timestamp"]].to_dict("records")

        for idx, rec in enumerate(records):
            nombre = rec.get("nombre")
            accion = (rec.get("accion") or "").strip().lower()
            ts = rec.get("timestamp")

            if ts is None or pd.isna(ts):
                continue

            if accion == "clock in":
                if pendiente_entrada_diaria.get(nombre) is None:
                    pendiente_entrada_diaria[nombre] = ts

            elif accion == "clock out":
                inicio = pendiente_entrada_diaria.get(nombre)
                if inicio is None or ts <= inicio:
                    # Nada que hacer si no había entrada, o si fue mal ordenado
                    pendiente_entrada_diaria[nombre] = None
                    continue

                # Si misma fecha
                if inicio.date() == ts.date():
                    segundos = (ts - inicio).total_seconds()
                    fecha_str = inicio.strftime("%Y-%m-%d")
                    total_por_usuario_fecha[(nombre, fecha_str)] += segundos

                else:
                    # --- Prorrateo: creamos trozos entre inicio y ts ---
                    # 1) Primer trozo: desde 'inicio' hasta la medianoche de ese día
                    next_midnight = datetime(inicio.year, inicio.month, inicio.day) + timedelta(days=1)
                    segundos_primero = (next_midnight - inicio).total_seconds()
                    fecha_inicio_str = inicio.strftime("%Y-%m-%d")
                    total_por_usuario_fecha[(nombre, fecha_inicio_str)] += segundos_primero

                    # 2) Días intermedios completos, si los hay
                    cursor = next_midnight
                    while cursor.date() < ts.date():
                        fecha_inter_str = cursor.strftime("%Y-%m-%d")
                        total_por_usuario_fecha[(nombre, fecha_inter_str)] += 24 * 3600
                        cursor = cursor + timedelta(days=1)

                    # 3) Último trozo: desde medianoche del día final hasta ts
                    mid_final = datetime(ts.year, ts.month, ts.day)
                    segundos_ultimo = (ts - mid_final).total_seconds()
                    fecha_final_str = ts.strftime("%Y-%m-%d")
                    total_por_usuario_fecha[(nombre, fecha_final_str)] += segundos_ultimo

                pendiente_entrada_diaria[nombre] = None

        totales_diarios_list = []
        for (nombre, fecha_str), segs in total_por_usuario_fecha.items():
            horas = round(segs / 3600, 2)
            totales_diarios_list.append({
                "nombre": nombre,
                "fecha": fecha_str,
                "horas_trabajadas": horas
            })
        df_totales_diarios = pd.DataFrame(totales_diarios_list)

        # --- 6) Generar el Excel con cuatro hojas en memoria ---
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            # Hoja 1: “Registros”
            df_reg = df[["nombre", "accion", "fecha", "hora", "proyecto"]].copy()
            df_reg.to_excel(writer, sheet_name="Registros", index=False)

            # Hoja 2: “Totales Globales”
            df_totales.to_excel(writer, sheet_name="Totales Globales", index=False)

            # Hoja 3: “Totales Semanales”
            df_totales_semanal.to_excel(writer, sheet_name="Totales Semanales", index=False)

            # Hoja 4: “Totales Diarios”
            df_totales_diarios.to_excel(writer, sheet_name="Totales Diarios", index=False)

        output.seek(0)

        # Nombre de archivo con timestamp actual
        filename = f"registros_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        logging.error(f"Error exporting Excel: {e}", exc_info=True)
        return "Error al generar el archivo Excel.", 500

# -- NUEVOS ENDPOINTS PARA HORAS TOTALES --

@app.route("/horas-totales/<nombre_usuario>", methods=["GET"])
def horas_totales_usuario(nombre_usuario):
    if not session.get("admin"):
        return jsonify({"status": "error", "message": "No autorizado"}), 403
    if not supabase:
        return jsonify({"status": "error", "message": "DB no configurada"}), 500

    try:
        # 1) Traer todos los registros de este usuario, usando timestamp completo
        registros = (
            supabase.table("registros")
            .select("accion, timestamp")
            .eq("nombre", nombre_usuario)
            .order("timestamp", desc=False)
            .execute()
            .data
        )

        if not isinstance(registros, list):
            logging.error(f"Respuesta inesperada de Supabase: {registros!r}")
            return jsonify({"status": "error", "message": "Formato inesperado de datos"}), 500

        total_segundos = 0
        pendiente_entrada = None

        # 2) Recorrer cada registro en orden cronológico
        for idx, row in enumerate(registros):
            accion = (row.get("accion") or "").strip().lower()
            ts = row.get("timestamp")
            if not ts:
                logging.warning(f"Fila #{idx} ignorada por timestamp vacío: {row!r}")
                continue

            # Intentamos parsear el timestamp (espera formato "YYYY-MM-DD HH:MM:SS")
            try:
                dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            except Exception as parse_err:
                logging.warning(f"Fila #{idx} con timestamp inválido '{ts}': {parse_err}. Fila: {row!r}")
                continue

            if accion == "clock in":
                if pendiente_entrada is None:
                    pendiente_entrada = dt
            elif accion == "clock out":
                if pendiente_entrada is not None:
                    delta = dt - pendiente_entrada
                    total_segundos += delta.total_seconds()
                    pendiente_entrada = None

        total_horas = round(total_segundos / 3600, 2)
        return jsonify({
            "status": "success",
            "nombre": nombre_usuario,
            "horas_trabajadas": total_horas
        })

    except Exception as e:
        logging.error(f"Error en /horas-totales/{nombre_usuario}: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Error interno al calcular totales"}), 500


@app.route("/horas-totales", methods=["GET"])
def horas_totales_todos():
    if not session.get("admin"):
        return jsonify({"status": "error", "message": "No autorizado"}), 403
    if not supabase:
        return jsonify({"status": "error", "message": "DB no configurada"}), 500

    try:
        # 1) Traer todos los registros de todos los usuarios, ordenados por timestamp
        registros = (
            supabase.table("registros")
            .select("nombre, accion, timestamp")
            .order("timestamp", desc=False)
            .execute()
            .data
        )

        if not isinstance(registros, list):
            logging.error(f"Respuesta inesperada de Supabase: {registros!r}")
            return jsonify({"status": "error", "message": "Formato inesperado de datos"}), 500

        total_por_usuario = defaultdict(float)
        pendiente_entrada = dict()  # { nombre_usuario: datetime de la última entrada pendiente }

        # 2) Recorrer cada registro en orden cronológico global
        for idx, row in enumerate(registros):
            nombre = row.get("nombre")
            accion = (row.get("accion") or "").strip().lower()
            ts = row.get("timestamp")
            if not ts:
                logging.warning(f"Fila #{idx} ignorada por timestamp vacío: {row!r}")
                continue

            try:
                dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            except Exception as parse_err:
                logging.warning(f"Fila #{idx} con timestamp inválido '{ts}': {parse_err}. Fila: {row!r}")
                continue

            if accion == "clock in":
                if pendiente_entrada.get(nombre) is None:
                    pendiente_entrada[nombre] = dt
            elif accion == "clock out":
                inicio = pendiente_entrada.get(nombre)
                if inicio is not None:
                    delta = dt - inicio
                    total_por_usuario[nombre] += delta.total_seconds()
                    pendiente_entrada[nombre] = None

        # 3) Convertir acumulados de segundos a horas y armar el JSON de respuesta
        resultados = []
        for nombre, segs in total_por_usuario.items():
            horas = round(segs / 3600, 2)
            resultados.append({"nombre": nombre, "horas_trabajadas": horas})

        return jsonify({"status": "success", "totales": resultados})

    except Exception as e:
        logging.error(f"Error en /horas-totales: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Error interno al calcular totales"}), 500

@app.route("/horas-totales-semanal", methods=["GET"])
def horas_totales_semanal():
    if not session.get("admin"):
        return jsonify({"status": "error", "message": "No autorizado"}), 403
    if not supabase:
        return jsonify({"status": "error", "message": "DB no configurada"}), 500

    try:
        # 1) Traer todos los registros ordenados por timestamp ascendente
        registros = (
            supabase.table("registros")
            .select("nombre, accion, timestamp")
            .order("timestamp", desc=False)
            .execute()
            .data
        )
        if not isinstance(registros, list):
            logging.error(f"Respuesta inesperada de Supabase: {registros!r}")
            return jsonify({"status": "error", "message": "Formato inesperado de datos"}), 500

        # 2) Acumular segundos trabajados por (usuario, año-semana)
        total_por_usuario_semana = defaultdict(float)
        pendiente_entrada = {}  # { nombre_usuario: datetime de clock-in pendiente }

        for idx, row in enumerate(registros):
            nombre = row.get("nombre")
            accion = (row.get("accion") or "").strip().lower()
            ts = row.get("timestamp")

            if not ts:
                logging.warning(f"Registro #{idx} sin timestamp: {row!r}")
                continue

            # Parsear timestamp (formato "YYYY-MM-DD HH:MM:SS")
            try:
                dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            except Exception as parse_err:
                logging.warning(f"Registro #{idx} timestamp inválido '{ts}': {parse_err}. Fila: {row!r}")
                continue

            if accion == "clock in":
                # Si no hay ya uno pendiente, guardamos este datetime de entrada
                if pendiente_entrada.get(nombre) is None:
                    pendiente_entrada[nombre] = dt
            elif accion == "clock out":
                inicio = pendiente_entrada.get(nombre)
                if inicio is not None:
                    # Diferencia en segundos
                    delta_seg = (dt - inicio).total_seconds()
                    # Obtener año y número de semana ISO
                    iso_year, iso_week, _ = inicio.isocalendar()
                    # Acumular al par (usuario, año, semana)
                    key = (nombre, iso_year, iso_week)
                    total_por_usuario_semana[key] += delta_seg
                    # Reset entrante pendiente
                    pendiente_entrada[nombre] = None

        # 3) Convertir segundos a horas y armar lista de resultados
        resultados = []
        for (nombre, year, week), segs in total_por_usuario_semana.items():
            horas = round(segs / 3600, 2)
            # --- Cálculo del rango “Jun 2–8, 2025” ---
            lunes = datetime.fromisocalendar(year, week, 1)
            domingo = lunes + timedelta(days=6)
            mes_abrev = lunes.strftime("%b")      # ej. "Jun"
            dia_inicio = lunes.day                # ej. 2
            dia_fin = domingo.day                 # ej. 8
            anio = lunes.year                     # ej. 2025

            semana_str = f"Semana {week} ({mes_abrev} {dia_inicio}–{dia_fin}, {anio})"

            resultados.append({
                "nombre": nombre,
                "semana": semana_str,
                "horas_trabajadas": horas
            })

        # Ordenamos por semana asc y luego por nombre (opcional)
        resultados.sort(key=lambda x: (x["semana"], x["nombre"]))

        return jsonify({"status": "success", "totales_semanal": resultados})

    except Exception as e:
        logging.error(f"Error en /horas-totales-semanal: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Error interno al calcular totales semanal"}), 500

# -- NUEVOS ENDPOINTS PARA HORAS TOTALES DIARIAS --

@app.route("/horas-totales-diarias", methods=["GET"])
def horas_totales_diarias():
    if not session.get("admin"):
        return jsonify({"status": "error", "message": "No autorizado"}), 403
    if not supabase:
        return jsonify({"status": "error", "message": "DB no configurada"}), 500

    try:
        # 1) Traer todos los registros ordenados cronológicamente
        registros = (
            supabase.table("registros")
            .select("nombre, accion, timestamp")
            .order("timestamp", desc=False)
            .execute()
            .data
        )
        if not isinstance(registros, list):
            logging.error(f"Respuesta inesperada de Supabase: {registros!r}")
            return jsonify({"status": "error", "message": "Formato inesperado de datos"}), 500

        # 2) Acumular segundos trabajados por (usuario, fecha)
        total_por_usuario_fecha = defaultdict(float)
        pendiente_entrada = {}  # { nombre_usuario: datetime de clock-in pendiente }

        for idx, row in enumerate(registros):
            nombre = row.get("nombre")
            accion = (row.get("accion") or "").strip().lower()
            ts = row.get("timestamp")

            if not ts:
                logging.warning(f"Registro #{idx} sin timestamp: {row!r}")
                continue

            # Parsear timestamp: "YYYY-MM-DD HH:MM:SS"
            try:
                dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            except Exception as parse_err:
                logging.warning(f"Registro #{idx} timestamp inválido '{ts}': {parse_err}")
                continue

            if accion == "clock in":
                # Guardamos la entrada si no hay otra pendiente
                if pendiente_entrada.get(nombre) is None:
                    pendiente_entrada[nombre] = dt

            elif accion == "clock out":
                inicio = pendiente_entrada.get(nombre)
                if inicio is not None:
                    # Si el clock-out viene antes que el clock-in, descartamos por seguridad
                    if dt <= inicio:
                        logging.warning(f"Clock-out anterior al clock-in para {nombre}: {inicio} → {dt}")
                        pendiente_entrada[nombre] = None
                        continue

                    # Si inicio y dt están en el mismo día, simple acumulado
                    if inicio.date() == dt.date():
                        segundos = (dt - inicio).total_seconds()
                        fecha_str = inicio.strftime("%Y-%m-%d")
                        key = (nombre, fecha_str)
                        total_por_usuario_fecha[key] += segundos
                    else:
                        # Prorrateo: tenemos que dividir entre varios días
                        temp_start = inicio
                        temp_end = dt

                        #  a) Primer trozo: desde 'inicio' hasta la medianoche de ese día
                        #     (mediodía = primera fecha + 1 día a las 00:00:00)
                        #     Ejemplo: inicio = 2025-06-02 17:30:00 → next_midnight = 2025-06-03 00:00:00
                        next_midnight = datetime(
                            temp_start.year, temp_start.month, temp_start.day
                        ) + timedelta(days=1)
                        segundos_primer_dia = (next_midnight - temp_start).total_seconds()
                        fecha_inicio_str = temp_start.strftime("%Y-%m-%d")
                        key_primero = (nombre, fecha_inicio_str)
                        total_por_usuario_fecha[key_primero] += segundos_primer_dia

                        #  b) Intermedios: si hubiera días completos entre next_midnight y fecha de salida
                        temp_cursor = next_midnight
                        while temp_cursor.date() < temp_end.date():
                            # Día intermedio completo (00:00:00 a 24:00:00)
                            fecha_intermedia_str = temp_cursor.strftime("%Y-%m-%d")
                            segundos_dia_completo = 24 * 3600
                            key_inter = (nombre, fecha_intermedia_str)
                            total_por_usuario_fecha[key_inter] += segundos_dia_completo

                            # Avanzamos un día
                            temp_cursor = temp_cursor + timedelta(days=1)

                        #  c) Último trozo: desde medianoche del día final hasta dt
                        fecha_final_str = temp_end.strftime("%Y-%m-%d")
                        # La medianoche de ese día es:
                        midnight_final = datetime(temp_end.year, temp_end.month, temp_end.day)
                        segundos_ultimo_dia = (temp_end - midnight_final).total_seconds()
                        key_ultimo = (nombre, fecha_final_str)
                        total_por_usuario_fecha[key_ultimo] += segundos_ultimo_dia

                    # Liberamos la entrada pendiente
                    pendiente_entrada[nombre] = None

        # 3) Convertir segundos a horas y armar lista de resultados
        resultados = []
        for (nombre, fecha_str), segs in total_por_usuario_fecha.items():
            horas = round(segs / 3600, 2)
            resultados.append({
                "nombre": nombre,
                "fecha": fecha_str,
                "horas_trabajadas": horas
            })

        # Ordenar por fecha ascendente y luego por nombre
        resultados.sort(key=lambda x: (x["fecha"], x["nombre"]))

        return jsonify({"status": "success", "totales_diarios": resultados})

    except Exception as e:
        logging.error(f"Error en /horas-totales-diarias: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Error interno al calcular totales diarios"}), 500


# Health check endpoint (optional but good practice)
@app.route("/health")
def health_check():
    # Can add checks here (e.g., database connectivity)
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    # Use Gunicorn or similar in production instead of Flask's development server
    port = int(os.environ.get("PORT", 5000))
    # Set debug=False for production
    app.run(host="0.0.0.0", port=port, debug=False)  # Set debug based on an environment variable ideally
