from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, logging
from geopy.geocoders import Nominatim
# ------------------ SETUP ------------------
app = Flask(__name__)
app.secret_key = "super-secret-key"   # 🔒 For demo/resume project only

# Flask-Limiter (basic demo, in-memory)
limiter = Limiter(get_remote_address, app=app, default_limits=["10 per minute"])

# Logging
logging.basicConfig(filename="doctorbot.log", level=logging.INFO)

# Geopy Nominatim client (OpenStreetMap)
geolocator = Nominatim(user_agent="personal_doctor")

# ------------------ DATABASE ------------------
def init_db():
    conn = sqlite3.connect("medical_data.db")
    c = conn.cursor()
    # Users table
    c.execute("""CREATE TABLE IF NOT EXISTS users (username TEXT, password TEXT)""")
    # Symptoms table
    c.execute("""CREATE TABLE IF NOT EXISTS symptoms_conditions
                 (symptom TEXT, condition TEXT, medicine TEXT)""")

    demo_data = [
        ("headache,cold", "Common Cold", "Paracetamol, Vitamin C"),
        ("fever", "Viral Fever", "Ibuprofen, ORS solution"),
        ("stomach pain", "Gastritis", "Antacid syrup, Omeprazole"),
        ("cough", "Bronchitis", "Cough syrup, Honey ginger tea"),
        ("sneezing,runny nose", "Allergic Rhinitis", "Cetirizine, Loratadine"),
        ("headache,nausea", "Migraine", "Sumatriptan, Naproxen"),
        ("thirst,frequent urination", "Diabetes (possible)", "Metformin (doctor prescribed only)"),
        ("fatigue,weakness", "Anemia (possible)", "Iron supplements, Folic acid"),
        ("shortness of breath,chest pain", "Angina (possible)", "Aspirin (doctor prescribed only)"),
        ("sore throat", "Pharyngitis", "Warm saline gargle, Lozenges"),
    ]

    c.executemany("INSERT OR IGNORE INTO symptoms_conditions VALUES (?,?,?)", demo_data)
    conn.commit()
    conn.close()

# Initialize DB at startup
init_db()

# ------------------ ROUTES ------------------
@app.route("/")
def home():
    if "user" in session:
        return redirect(url_for("chat"))
    return render_template("login.html")

@app.route("/register", methods=["POST"])
def register():
    username = request.form["username"]
    password = request.form["password"]
    conn = sqlite3.connect("medical_data.db")
    c = conn.cursor()
    c.execute("INSERT INTO users VALUES (?, ?)", (username, generate_password_hash(password)))
    conn.commit()
    conn.close()
    return redirect(url_for("home"))

@app.route("/login", methods=["POST"])
def login():
    username = request.form["username"]
    password = request.form["password"]
    conn = sqlite3.connect("medical_data.db")
    c = conn.cursor()
    c.execute("SELECT password FROM users WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()
    if row and check_password_hash(row[0], password):
        session["user"] = username
        return redirect(url_for("chat"))
    return "Login failed!"

@app.route("/chat")
def chat():
    if "user" not in session:
        return redirect(url_for("home"))
    return render_template("chat.html")

# ------------------ CHATBOT API ------------------
@app.route("/chat_api", methods=["POST"])
@limiter.limit("5 per minute")
def chat_api():
    try:
        data = request.json or {}
        symptoms = data.get("message", "").lower().strip()
        user_location = data.get("location", "New York")  # default fallback

        # --- Step 1: Check symptoms in DB ---
        conn = sqlite3.connect("medical_data.db")
        c = conn.cursor()
        c.execute("SELECT condition, medicine FROM symptoms_conditions WHERE symptom LIKE ?", 
                  ('%' + symptoms + '%',))
        row = c.fetchone()
        conn.close()

        # --- Step 2: Find nearby hospitals via OpenStreetMap ---
        hospitals = []
        try:
            query = f"hospitals near {user_location}"
            places = geolocator.geocode(query, exactly_one=False, limit=3)
            if places:
                for place in places:
                    hospitals.append({
                        "name": place.address.split(",")[0],
                        "address": place.address,
                        "rating": "N/A"
                    })
        except Exception as e:
            logging.warning(f"OSM lookup failed: {str(e)}")
            hospitals = [
                {"name": "City General Hospital", "address": f"Default Hospital near {user_location}", "rating": "N/A"},
                {"name": "Community Health Clinic", "address": f"Demo Clinic near {user_location}", "rating": "N/A"}
            ]

        # --- Step 3: Build response ---
        if row:
            condition, medicine = row
            return jsonify({
                "diagnosis": condition,
                "medicine": medicine,
                "disclaimer": "⚠️ Demo only. Consult a doctor.",
                "nearby_hospitals": hospitals
            })
        else:
            return jsonify({
                "diagnosis": "Unknown",
                "medicine": "Not available",
                "disclaimer": "⚠️ Couldn’t match symptoms. Consult a real doctor.",
                "nearby_hospitals": hospitals
            })

    except Exception as e:
        logging.error(f"Error in chat_api: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

# ------------------ RUN APP ------------------
if __name__ == "__main__":
    app.run(debug=True)