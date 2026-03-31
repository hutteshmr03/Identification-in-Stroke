from flask import Flask, render_template, redirect, request, url_for, session, flash
from werkzeug.utils import secure_filename
import mysql.connector
import os
from PIL import Image
import torch
import torch.nn as nn
from torchvision import models, transforms
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'dev_secret_key_change_in_production_123'  # Change for production!

# Allowed extensions for uploads
UPLOAD_FOLDER = 'static/saved_images'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# DB connection with error handling
def get_db_connection():
    try:
        return mysql.connector.connect(
            host="localhost",
            user="root",
            password="",
            port="3306",
            database='stroke'
        )
    except mysql.connector.Error as err:
        logger.error(f"DB connection failed: {err}")
        return None

mycursor = None
mydb = get_db_connection()
if mydb:
    mycursor = mydb.cursor()
else:
    logger.error("Failed to connect to DB. App may not function properly.")

def execution_query(query, values):
    if not mycursor:
        return False
    try:
        mycursor.execute(query, values)
        mydb.commit()
        return True
    except mysql.connector.Error as err:
        logger.error(f"Query execution failed: {err}")
        return False

def retrieve_query(query, values=None):
    if not mycursor:
        return []
    try:
        if values:
            mycursor.execute(query, values)
        else:
            mycursor.execute(query)
        return mycursor.fetchall()
    except mysql.connector.Error as err:
        logger.error(f"Query retrieve failed: {err}")
        return []

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/register', methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        c_password = request.form['c_password']
        if password != c_password:
            return render_template('register.html', message="Confirm password does not match!")
        # Check if email exists (case-insensitive for lookup)
        query = "SELECT id FROM users WHERE LOWER(email) = %s"
        if retrieve_query(query, (email.lower(),)):
            return render_template('register.html', message="This email already exists!")
        query = "INSERT INTO users (name, email, password) VALUES (%s, %s, %s)"
        if execution_query(query, (name, email, password)):
            flash("Successfully Registered!", "success")
            return redirect(url_for('login'))
        else:
            return render_template('register.html', message="Registration failed. Try again.")
    return render_template('register.html')

@app.route('/login', methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form['email'].lower()
        password = request.form['password']
        query = "SELECT id, name FROM users WHERE LOWER(email) = %s AND password = %s"
        user_data = retrieve_query(query, (email, password))
        if user_data:
            session['user_id'] = user_data[0][0]
            session['user_email'] = email
            flash("Login successful!", "success")
            return redirect('/home')
        flash("Invalid email or password!", "error")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully!", "success")
    return redirect(url_for('index'))

@app.route('/home')
def home():
    if 'user_id' not in session:
        flash("Please login first!", "error")
        return redirect(url_for('login'))
    return render_template('home.html')

@app.route('/prediction', methods=['GET', 'POST'])
def prediction():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash("No file selected!", "error")
            return render_template('prediction.html')
        file = request.files['file']
        if file.filename == '':
            flash("No file selected!", "error")
            return render_template('prediction.html')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            try:
                # Device setup
                device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
                logger.info(f"Using device: {device}")
                
                # Transforms
                transform = transforms.Compose([
                    transforms.Resize((224, 224)),
                    transforms.ToTensor(),
                    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
                ])
                
                # Model definition
                class MobileNetModel(nn.Module):
                    def __init__(self, num_classes=2):
                        super().__init__()
                        self.mobilenet = models.mobilenet_v2(pretrained=False)  # No pretrained for fine-tuned
                        num_features = self.mobilenet.classifier[1].in_features
                        self.mobilenet.classifier[1] = nn.Linear(num_features, num_classes)
                    
                    def forward(self, x):
                        return self.mobilenet(x)
                
                # Load model
                if not os.path.exists("mobilenet.pt"):
                    raise FileNotFoundError("mobilenet.pt not found! Copy from BACK END.")
                model = MobileNetModel()
                model.load_state_dict(torch.load("mobilenet.pt", map_location=device))
                model.to(device)
                model.eval()
                
                # Predict
                image = Image.open(filepath).convert('RGB')
                image = transform(image).unsqueeze(0).to(device)
                with torch.no_grad():
                    output = model(image)
                    _, predicted = torch.max(output, 1)
                
                label = "Normal" if predicted.item() == 0 else "Stroke"
                logger.info(f"Prediction for {filename}: {label}")
                
                return render_template('prediction.html', prediction=label, path=filepath)
            except Exception as e:
                logger.error(f"Prediction error: {e}")
                flash(f"Prediction failed: {str(e)}", "error")
        else:
            flash("Invalid file type! Use image files.", "error")
    return render_template('prediction.html')

@app.route('/graph')
def graph():
    # Placeholder - implement if data available
    flash("Graph feature coming soon!", "info")
    return render_template('graph.html')

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)

