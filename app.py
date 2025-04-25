
from flask import Flask, request, jsonify, redirect, render_template, session
from flask_cors import CORS
from supabase import create_client, Client
from datetime import datetime
from pytz import timezone
import os
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(message)s')

app = Flask(__name__)
# Leer secret_key y admin password de entorno
app.secret_key = os.getenv("SECRET_KEY", "supersecreto123")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

CORS(app)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

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

    # Timestamp en zona de Nueva York
    zona = timezone("America/New_York")
    timestamp = datetime.now(zona).strftime("%Y-%m-%d %H:%M:%S")

    # Validar empleado
    try:
        resp = supabase.table("empleados").select("*")\
            .eq("nombre", nombre)\
            .eq("pin", pin)\
            .execute()
        if not resp.data:
            return jsonify({"status": "error", "message": "Empleado no autorizado"}), 401
    except Exception:
        logging.error("Error verificando empleado en /submit", exc_info=True)
        return jsonify({"status": "error", "message": "Error interno"}), 500

    # Insertar registro
    try:
        supabase.table("registros").insert({
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
        return redirect("/login")
    nombre = request.form.get("nombre")
    pin = request.form.get("pin")
    if not nombre or not pin:
        return "Nombre o PIN vacío", 400
    try:
        supabase.table("empleados").insert({"nombre": nombre, "pin": pin}).execute()
    except Exception:
        logging.error("Error agregando empleado", exc_info=True)
        return "Error inesperado al agregar empleado", 500
    return redirect("/admin")

@app.route("/empleados")
def empleados():
    if not session.get("admin"):
        return redirect("/login")
    try:
        data = supabase.table("empleados").select("*").execute().data
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
        supabase.table("empleados").delete().eq("nombre", nombre).execute()
    except Exception:
        logging.error("Error eliminando empleado", exc_info=True)
        return jsonify({"status": "error", "message": "Error interno"}), 500
    return jsonify({"status": "success"})

@app.route("/registros")
def registros():
    if not session.get("admin"):
        return redirect("/login")
    try:
        data = supabase.table("registros").select("*").order("timestamp", desc=True).execute().data
    except Exception:
        logging.error("Error obteniendo registros", exc_info=True)
        return jsonify({"status": "error", "message": "Error interno"}), 500
    return jsonify(data)

@app.route("/estado")
def estado():
    nombre = request.args.get("nombre")
    pin = request.args.get("pin")
    if not nombre or not pin:
        return jsonify({"estado": "desconocido"}), 400

    # Validar empleado
    try:
        emp_resp = supabase.table("empleados").select("*")\
            .eq("nombre", nombre)\
            .eq("pin", pin)\
            .execute()
        if not emp_resp.data:
            return jsonify({"estado": "desconocido"}), 401

        registros = supabase.table("registros")\
            .select("accion, proyecto_id")\
            .eq("nombre", nombre)\
            .order("timestamp", desc=True)\
            .limit(1)\
            .execute().data
    except Exception:
        logging.error("Error en /estado", exc_info=True)
        return jsonify({"estado": "error"}), 500

    if not registros:
        return jsonify({"estado": "ninguno"})
    return jsonify({
        "estado": registros[0]["accion"],
        "proyecto_id": registros[0].get("proyecto_id")
    })

@app.route("/exportar")
def exportar():
    if not session.get("admin"):
        return redirect("/login")

    try:
        # 1) Traer todos los registros
        registros = supabase.table("registros")\
            .select("*")\
            .order("timestamp", desc=True)\
            .execute().data

        # 2) Traer todos los proyectos y construir un mapa id→nombre
        proyectos = supabase.table("proyectos")\
            .select("id,nombre")\
            .execute().data
        mapa_proyectos = { p["id"]: p["nombre"] for p in proyectos }

    except Exception as e:
        logging.error("Error generando CSV", exc_info=True)
        return "Error interno", 500

    # 3) Cabecera: cambiamos proyecto_id por proyecto
    csv = "nombre,accion,proyecto,fecha\n"
    for r in registros:
        proyecto_nombre = mapa_proyectos.get(r.get("proyecto_id"), "")
        csv += f'{r["nombre"]},{r["accion"]},"{proyecto_nombre}",{r["timestamp"]}\n'

    return csv, 200, {
        "Content-Type": "text/csv",
        "Content-Disposition": "attachment;filename=registros.csv"
    }

@app.route("/proyectos")
def listar_proyectos():
    try:
        proyectos = supabase.table("proyectos").select("*").order("nombre").execute().data
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
        supabase.table("proyectos").insert({"nombre": nombre}).execute()
    except Exception:
        logging.error("Error agregando proyecto", exc_info=True)
        return jsonify({"status": "error", "message": "Error interno"}), 500
    return jsonify({"status": "success", "message": "Proyecto agregado"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
