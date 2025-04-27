
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

    # Basic Input Validation
    if not nombre or not pin or not accion:
        logging.warning(f"Submit attempt with missing data: name={bool(nombre)}, pin={bool(pin)}, action={bool(accion)}")
        return jsonify({"status": "error", "message": "Nombre, PIN, y acción son requeridos."}), 400

    # Optional: Add more specific PIN validation (e.g., check if numeric)
    if not pin.isdigit():
        logging.warning(f"Submit attempt with non-numeric PIN from user: {nombre}")
        return jsonify({"status": "error", "message": "PIN debe ser numérico."}), 400

    zona = timezone("America/Chicago") # Or configure via env var if needed elsewhere
    timestamp = datetime.now(zona).strftime("%Y-%m-%d %H:%M:%S")

    try:
        # Verify employee credentials
        empleados = supabase.table("empleados").select("id").eq("nombre", nombre).eq("pin", pin).execute().data
        if not empleados:
            logging.warning(f"Submit attempt with incorrect PIN for user: {nombre}")
            return jsonify({"status": "error", "message": "Nombre o PIN incorrecto."}), 401 # Use 401 Unauthorized

        # Insert the clocking record
        insert_response = supabase.table("registros").insert({
            "nombre": nombre,
            "accion": accion,
            "timestamp": timestamp
        }).execute()

        # Optional: Check insert_response for errors if Supabase client provides details
        logging.info(f"Record submitted successfully for user: {nombre}, action: {accion}")
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
        data = supabase.table("registros").select("*").order("timestamp", desc=True).execute().data
        if not data:
            return "No hay registros para exportar.", 200

        csv_lines = ["nombre,accion,timestamp"] # Start with header row
        for row in data:
            # Prepare data, handling potential None values and escaping quotes
            nombre = row.get('nombre', '') or '' # Ensure string, handle None
            accion = row.get('accion', '') or '' # Ensure string, handle None
            timestamp = row.get('timestamp', '') or '' # Ensure string, handle None

            # Escape double quotes for CSV compatibility
            nombre_escaped = nombre.replace('"', '""')
            accion_escaped = accion.replace('"', '""')
            timestamp_escaped = timestamp.replace('"', '""')

            # Create the CSV line using f-string with the prepared variables
            csv_lines.append(f'"{nombre_escaped}","{accion_escaped}","{timestamp_escaped}"')

        # Join all lines with a newline character
        csv_output = "\n".join(csv_lines) + "\n" # Add final newline

        logging.info("Generated CSV export.")
        return csv_output, 200, {
            "Content-Type": "text/csv; charset=utf-8", # Specify charset
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
