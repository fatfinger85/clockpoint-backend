
from flask import Flask, request, jsonify, redirect, render_template, session
from flask_cors import CORS
from supabase import create_client
from datetime import datetime
from pytz import timezone
import os
import logging

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

# Inicializar Flask
app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.getenv("SECRET_KEY", "supersecreto123")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
CORS(app)

# Configurar clientes Supabase
SUPABASE_URL         = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY    = os.getenv("SUPABASE_KEY")           # anon key
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")   # service role key
supabase_anon = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
supabase_srv  = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect("/admin")
        return "Contraseña incorrecta", 403
    return render_template("login.html")

@app.route("/admin")
def admin():
    if not session.get("admin"):
        return redirect("/login")
    return render_template("admin.html")

@app.route("/submit", methods=["POST"])
def submit():
    data = request.json or {}
    nombre = data.get("nombre")
    pin = data.get("pin")
    accion = data.get("accion")
    proyecto_id = data.get("proyecto_id")
    if not all([nombre, pin, accion]):
        return jsonify({"status": "error", "message": "Datos incompletos"}), 400

    zona = timezone("America/New_York")
    timestamp = datetime.now(zona).strftime("%Y-%m-%d %H:%M:%S")

    try:
        resp = supabase_anon.table("empleados")\
            .select("*")\
            .eq("nombre", nombre)\
            .eq("pin", pin)\
            .execute()
        if not resp.data:
            return jsonify({"status": "error", "message": "Empleado no autorizado"}), 401
    except Exception:
        logging.error("Error verificando empleado en /submit", exc_info=True)
        return jsonify({"status": "error", "message": "Error interno"}), 500

    try:
        supabase_srv.table("registros").insert({
            "nombre": nombre,
            "accion": accion,
            "timestamp": timestamp,
            "proyecto_id": proyecto_id
        }).execute()
    except Exception:
        logging.error("Error insertando registro en /submit", exc_info=True)
        return jsonify({"status": "error", "message": "Error interno"}), 500

    return jsonify({"status": "success"})

@app.route("/agregar-empleado", methods=["POST"])
def agregar_empleado():
    if not session.get("admin"):
        if request.is_json:
            return jsonify({"status":"error","message":"No autorizado"}), 403
        return redirect("/login")

    if request.is_json:
        data = request.get_json()
        nombre = data.get("nombre")
        pin    = data.get("pin")
    else:
        nombre = request.form.get("nombre")
        pin    = request.form.get("pin")

    if not nombre or not pin:
        if request.is_json:
            return jsonify({"status":"error","message":"Nombre o PIN vacío"}), 400
        return "Nombre o PIN vacío", 400

    try:
        supabase_srv.table("empleados").insert({
            "nombre": nombre,
            "pin": pin
        }).execute()
    except Exception:
        logging.error("Error agregando empleado", exc_info=True)
        if request.is_json:
            return jsonify({"status":"error","message":"Error interno"}), 500
        return "Error inesperado al agregar empleado", 500

    if request.is_json:
        return jsonify({"status":"success"}), 200
    return redirect("/admin")

@app.route("/empleados")
def empleados():
    if not session.get("admin"):
        return redirect("/login")
    try:
        data = supabase_anon.table("empleados").select("*").execute().data
    except Exception:
        logging.error("Error listando empleados", exc_info=True)
        return jsonify({"status": "error", "message": "Error interno"}), 500
    return jsonify(data)

@app.route("/eliminar-empleado", methods=["POST"])
def eliminar_empleado():
    if not session.get("admin"):
        return jsonify({"status": "error", "message": "No autorizado"}), 403
    nombre = request.json.get("nombre")
    try:
        supabase_srv.table("empleados").delete().eq("nombre", nombre).execute()
    except Exception:
        logging.error("Error eliminando empleado", exc_info=True)
        return jsonify({"status": "error", "message": "Error interno"}), 500
    return jsonify({"status": "success"})

@app.route("/registros")
def registros():
    if not session.get("admin"):
        return redirect("/login")
    try:
        data = supabase_anon.table("registros")\
            .select("*")\
            .order("timestamp", desc=True)\
            .execute().data
    except Exception:
        logging.error("Error obteniendo registros", exc_info=True)
        return jsonify({"status": "error", "message": "Error interno"}), 500
    return jsonify(data)

@app.route("/proyectos")
def listar_proyectos():
    try:
        proyectos = supabase_anon.table("proyectos")\
            .select("*")\
            .order("nombre")\
            .execute().data
    except Exception:
        logging.error("Error listando proyectos", exc_info=True)
        return jsonify({"status": "error", "message": "Error interno"}), 500
    return jsonify(proyectos)

@app.route("/agregar-proyecto", methods=["POST"])
def agregar_proyecto():
    if not session.get("admin"):
        return jsonify({"status": "error", "message": "No autorizado"}), 403
    data = request.get_json() or {}
    nombre = data.get("nombre")
    if not nombre:
        return jsonify({"status": "error", "message": "Nombre requerido"}), 400
    try:
        supabase_srv.table("proyectos").insert({"nombre": nombre}).execute()
    except Exception:
        logging.error("Error agregando proyecto", exc_info=True)
        return jsonify({"status": "error", "message": "Error interno"}), 500
    return jsonify({"status": "success", "message": "Proyecto agregado"}), 200

@app.route("/exportar")
def exportar():
    if not session.get("admin"):
        return redirect("/login")
    try:
        registros = supabase_anon.table("registros")\
            .select("*")\
            .order("timestamp", desc=True)\
            .execute().data
        proyectos = supabase_anon.table("proyectos")\
            .select("id,nombre")\
            .execute().data
        mapa = {p["id"]: p["nombre"] for p in proyectos}
    except Exception:
        logging.error("Error generando CSV", exc_info=True)
        return "Error interno", 500

    csv = "nombre,accion,proyecto,timestamp\n"
    for r in registros:
        proyecto_nombre = mapa.get(r.get("proyecto_id"), "")
        csv += f'{r["nombre"]},{r["accion"]},"{proyecto_nombre}",{r["timestamp"]}\n'

    return csv, 200, {
        "Content-Type": "text/csv",
        "Content-Disposition": "attachment;filename=registros.csv"
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
