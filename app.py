
# filename: app.py
from flask import Flask, request, jsonify, redirect, render_template, session
from flask_cors import CORS
from supabase import create_client, Client
from datetime import datetime
from pytz import timezone
import os
import logging # Added for potential logging later

app = Flask(__name__)
# Load secret key from environment variable for security
# Use a strong, randomly generated key
app.secret_key = os.getenv("FLASK_APP_SECRET_KEY", "supersecreto123") # Provide a default only for local dev if needed, but ideally require it
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
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "@dmin123") # Use a strong password

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
    proyecto = data.get("proyecto") # <-- Get the selected project (might be None or empty)

    # Basic Input Validation
    if not nombre or not pin or not accion:
        logging.warning(f"Submit attempt with missing data: name={bool(nombre)}, pin={bool(pin)}, action={bool(accion)}")
        return jsonify({"status": "error", "message": "Nombre, PIN, y acción son requeridos."}), 400

    if not pin.isdigit():
        logging.warning(f"Submit attempt with non-numeric PIN from user: {nombre}")
        return jsonify({"status": "error", "message": "PIN debe ser numérico."}), 400

    # Handle empty project selection - store as None (NULL) in the database
    if not proyecto: # Checks for None or empty string ""
        proyecto_db = None
    else:
        proyecto_db = proyecto

    zona = timezone("America/Chicago")
    timestamp = datetime.now(zona).strftime("%Y-%m-%d %H:%M:%S")
    fecha = now.strftime("%Y-%m-%d")
    hora = now.strftime("%H:%M:%S")

    try:
        empleados = supabase.table("empleados").select("id").eq("nombre", nombre).eq("pin", pin).execute().data
        if not empleados:
            logging.warning(f"Submit attempt with incorrect PIN for user: {nombre}")
            return jsonify({"status": "error", "message": "Nombre o PIN incorrecto."}), 401

        # Insert the record including the project
        insert_response = supabase.table("registros").insert({
            "nombre": nombre,
            "accion": accion,
            "timestamp": timestamp,
            "fecha": fecha,
            "hora": hora,
            "proyecto": proyecto_db # <-- Add project to the insert data
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
             return f"Empleado '{nombre}' ya existe.", 409 # 409 Conflict

        supabase.table("empleados").insert({"nombre": nombre, "pin": pin}).execute()
        logging.info(f"Employee added: {nombre}")
        return redirect("/admin?success=Empleado agregado") # Redirect with success message
    except Exception as e:
        logging.error(f"Error adding employee {nombre}: {str(e)}")
        # Redirect back with error message
        return f"Error inesperado al agregar empleado: {str(e)}", 500

@app.route("/empleados")
def empleados():
    if not session.get("admin"):
        return redirect("/login")
    if not supabase:
        return jsonify([]) # Return empty list if DB not configured

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
        return jsonify([]) # Return empty list if DB not configured

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
        return redirect("/login") # Or return 403 Forbidden
    if not supabase:
        return "Backend database not configured.", 500

    nombre_proyecto = request.form.get("nombre_proyecto")

    if not nombre_proyecto:
        logging.warning("Add project attempt with missing name.")
        # Redirect back to admin page with an error message
        # Ensure the redirect goes back to the projects tab eventually
        return redirect("/admin?error=Nombre del proyecto es requerido#proyectos") # Redirect includes error and #hash

    try:
        # Check if project already exists
        existing = supabase.table("proyectos").select("id").eq("nombre", nombre_proyecto).execute().data
        if existing:
             logging.warning(f"Attempt to add duplicate project: {nombre_proyecto}")
             return redirect(f"/admin?error=Proyecto '{nombre_proyecto}' ya existe.#proyectos") # Redirect with error

        supabase.table("proyectos").insert({"nombre": nombre_proyecto}).execute()
        logging.info(f"Project added: {nombre_proyecto}")
        return redirect("/admin?success=Proyecto agregado#proyectos") # Redirect with success and #hash
    except Exception as e:
        logging.error(f"Error adding project {nombre_proyecto}: {str(e)}")
        return redirect(f"/admin?error=Error inesperado al agregar proyecto#proyectos") # Redirect with error

@app.route("/eliminar-proyecto", methods=["POST"])
def eliminar_proyecto():
    """Deletes a project by name."""
    if not session.get("admin"):
        return jsonify({"status": "error", "message": "Unauthorized"}), 403
    if not supabase:
         return jsonify({"status": "error", "message": "Backend database not configured."}), 500

    nombre_proyecto = request.json.get("nombre") # Expecting JSON body
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
        project_names = [item['nombre'] for item in data]
        return jsonify(project_names)
    except Exception as e:
        logging.error(f"Error fetching project list: {str(e)}")
        return jsonify({"error": "Could not fetch project list"}), 500

@app.route("/registros")
def registros():
    if not session.get("admin"):
        return redirect("/login")
    if not supabase:
        return jsonify([]) # Return empty list if DB not configured

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
    pin = request.args.get("pin") # PIN is still required by this endpoint

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
        registros = supabase.table("registros") \
                          .select("accion") \
                          .eq("nombre", nombre) \
                          .order("timestamp", desc=True) \
                          .limit(1) \
                          .execute().data

        if not registros:
            return jsonify({"estado": "ninguno"}) # No records found for this user
        else:
            return jsonify({"estado": registros[0]["accion"]}) # Return last action

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
        # Select all columns, including the new 'proyecto' column
        data = supabase.table("registros").select("*").order("timestamp", desc=True).execute().data
        if not data:
            return "No hay registros para exportar.", 200

        # Add 'proyecto' to header
        csv_lines = ["nombre,accion,timestamp,proyecto"]
        for row in data:
            # Prepare data, handling potential None values and escaping quotes
            nombre = row.get('nombre', '') or ''
            accion = row.get('accion', '') or ''
            timestamp = row.get('timestamp', '') or ''
            proyecto = row.get('proyecto', '') or '' # Handle None/empty project

            # Escape double quotes
            nombre_escaped = nombre.replace('"', '""')
            accion_escaped = accion.replace('"', '""')
            timestamp_escaped = timestamp.replace('"', '""')
            proyecto_escaped = proyecto.replace('"', '""') # Escape project name

            # Add project to the CSV line
            csv_lines.append(f'"{nombre_escaped}","{accion_escaped}","{timestamp_escaped}","{proyecto_escaped}"')

        csv_output = "\n".join(csv_lines) + "\n"

        logging.info("Generated CSV export including projects.")
        return csv_output, 200, {
            "Content-Type": "text/csv; charset=utf-8",
            "Content-Disposition": f"attachment;filename=registros_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        }
    except Exception as e:
        logging.error(f"Error exporting records: {str(e)}")
        return "Error al generar el archivo CSV.", 500

# Health check endpoint (optional but good practice)
@app.route("/health")
def health_check():
    # Can add checks here (e.g., database connectivity)
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    # Use Gunicorn or similar in production instead of Flask's development server
    port = int(os.environ.get("PORT", 5000))
    # Set debug=False for production
    app.run(host="0.0.0.0", port=port, debug=False) # Set debug based on an environment variable ideally
