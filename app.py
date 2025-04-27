
from flask import Flask, request, jsonify, redirect, render_template, session
from flask_cors import CORS
from supabase import create_client, Client
from datetime import datetime
from pytz import timezone
import os

app = Flask(__name__)
app.secret_key = "supersecreto123"
CORS(app)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

ADMIN_PASSWORD = "admin123"

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form["password"] == ADMIN_PASSWORD:
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
    data = request.json
    nombre = data.get("nombre")
    pin = data.get("pin")
    accion = data.get("accion")
    zona = timezone("America/Chicago")
    timestamp = datetime.now(zona).strftime("%Y-%m-%d %H:%M:%S")

    empleados = supabase.table("empleados").select("*").eq("nombre", nombre).eq("pin", pin).execute().data
    if not empleados:
        return jsonify({"status": "error"}), 401

    supabase.table("registros").insert({
        "nombre": nombre,
        "accion": accion,
        "timestamp": timestamp
    }).execute()
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
        return redirect("/admin")
    except Exception as e:
        return f"Error inesperado al agregar empleado: {str(e)}", 500

@app.route("/empleados")
def empleados():
    if not session.get("admin"):
        return redirect("/login")
    data = supabase.table("empleados").select("*").execute().data
    return jsonify(data)

@app.route("/eliminar-empleado", methods=["POST"])
def eliminar_empleado():
    if not session.get("admin"):
        return jsonify({"status": "error"}), 403
    nombre = request.json.get("nombre")
    supabase.table("empleados").delete().eq("nombre", nombre).execute()
    return jsonify({"status": "success"})

@app.route("/registros")
def registros():
    if not session.get("admin"):
        return redirect("/login")
    data = supabase.table("registros").select("*").order("timestamp", desc=True).execute().data
    return jsonify(data)

@app.route("/estado")
def estado():
    nombre = request.args.get("nombre")
    pin = request.args.get("pin")
    if not nombre or not pin:
        return jsonify({"estado": "desconocido"})

    registros = supabase.table("registros")         .select("*")         .eq("nombre", nombre)         .order("timestamp", desc=True)         .limit(1)         .execute().data

    if not registros:
        return jsonify({"estado": "ninguno"})
    return jsonify({"estado": registros[0]["accion"]})

@app.route("/exportar")
def exportar():
    if not session.get("admin"):
        return redirect("/login")
    data = supabase.table("registros").select("*").order("timestamp", desc=True).execute().data
    csv = "nombre,accion,timestamp\n"
    for row in data:
        csv += f"{row['nombre']},{row['accion']},{row['timestamp']}\n"
    return csv, 200, {
        "Content-Type": "text/csv",
        "Content-Disposition": "attachment;filename=registros.csv"
    }

@app.route("/eliminar-registro", methods=["POST"])
def eliminar_registro():
    if not session.get("admin"):
        return jsonify({"status": "error"}), 403
    registro_id = request.json.get("id")
    try:
        supabase.table("registros").delete().eq("id", registro_id).execute()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
