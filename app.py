from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_babel import Babel, _
import database
import datetime
import os
import sys

# PyInstaller creează un folder temporar și stochează calea în _MEIPASS
if getattr(sys, 'frozen', False):
    base_dir = sys._MEIPASS # Aici sunt html-urile și traducerile dezarhivate
    db_dir = os.path.dirname(sys.executable) # Aici e folderul unde se află .exe-ul efectiv
else:
    base_dir = os.path.abspath(os.path.dirname(__file__))
    db_dir = base_dir

# Când inițializezi Flask, îi spui exact unde să caute folderele
app = Flask(__name__, 
            template_folder=os.path.join(base_dir, 'templates'),
            static_folder=os.path.join(base_dir, 'static'))

app.config['BABEL_TRANSLATION_DIRECTORIES'] = os.path.join(base_dir, 'translations')
db_path = os.path.join(db_dir, 'access_control.db')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key-here'  # Required for sessions
app.config['BABEL_DEFAULT_LOCALE'] = 'en'

def get_locale():
    return session.get('lang', 'en')

babel = Babel(app, locale_selector=get_locale)

# Initialize DB
database.db.init_app(app)
database.init_db(app)

@app.route('/setlang/<lang_code>')
def setlang(lang_code):
    session['lang'] = lang_code
    return redirect(request.referrer or url_for('index'))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/scan', methods=['POST'])
def scan_rfid():
    data = request.json
    rfid_tag = data.get('rfid_tag')
    
    if not rfid_tag:
        return jsonify({'status': 'error', 'message': 'No RFID tag provided'}), 400

    user = database.get_user_by_rfid(rfid_tag)
    
    if not user:
        return jsonify({'status': 'unknown', 'rfid_tag': rfid_tag, 'message': 'User not found'}), 200 # 200 OK because it's a valid scan, just unknown user
    
    allowed, message, status_code, sub_name, weekly_count = database.check_access(user['id'])
    
    # Check_access counts *previous* logs. If we are allowing access *now*, 
    # we should include the current scan in the count for UI feedback.
    display_count = weekly_count + 1 if allowed else weekly_count
    
    # Fetch the previously recorded attempt before saving this new one
    last_log = database.get_last_log(user['id'])
    
    database.log_access(user['id'], allowed, message)
    
    return jsonify({
        'status': status_code,
        'user_name': user['name'],
        'user_id': user['id'],
        'message': message,
        'sub_name': sub_name,
        'weekly_count': display_count,
        'last_attempt': last_log
    })

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        phone = request.form['phone']
        rfid_tag = request.form['rfid_tag']
        sub_type_id = request.form.get('subscription_type')
        class_id = request.form.get('class_id')
        class_duration = request.form.get('class_duration')
        
        # Check if user exists
        existing_user = database.get_user_by_rfid(rfid_tag)
        if existing_user:
             return render_template('register.html', error="RFID Tag already registered!")

        user_id = database.create_user(name, phone, rfid_tag)
        if user_id:
            if sub_type_id:
                database.assign_subscription(user_id, sub_type_id)
            if class_id:
                database.enroll_user_in_class(user_id, class_id, class_duration)
            return redirect(url_for('index'))
        else:
             return render_template('register.html', error="Error creating user (Phone might use used).")

    # Get subscription types and classes for dropdowns
    sub_types = database.SubscriptionType.query.all()
    classes = database.get_all_classes()
    
    rfid_prefill = request.args.get('rfid', '')
    
    return render_template('register.html', sub_types=sub_types, classes=classes, rfid_prefill=rfid_prefill)

@app.route('/users')
def get_users_route():
    page = request.args.get('page', 1, type=int)
    name = request.args.get('name', '')
    phone = request.args.get('phone', '')
    sub_id = request.args.get('sub_id', '')
    class_id = request.args.get('class_id', '')
    
    paginated_data = database.get_users_paginated(page=page, per_page=50, search_name=name, search_phone=phone, search_sub_id=sub_id, search_class_id=class_id)
    subscription_types = database.SubscriptionType.query.all()
    classes = database.ClassSchedule.query.all()
    
    return render_template('users.html', 
                          paginated_data=paginated_data, 
                          subscription_types=subscription_types,
                          classes=classes,
                          search_name=name,
                          search_phone=phone,
                          search_sub_id=sub_id,
                          search_class_id=class_id)

@app.route('/user/<int:user_id>')
def user_profile(user_id):
    user = database.get_user_by_id(user_id)
    if not user:
        return redirect(url_for('get_users_route'))
        
    sub = database.get_active_subscription(user_id)
    stats = database.get_user_stats(user_id)
    logs = database.get_user_logs(user_id, limit=50)
    
    # Also fetch enrolled classes manually here for display
    user_classes = database.db.session.query(database.ClassSchedule, database.ClassParticipant.end_date)\
        .join(database.ClassParticipant, database.ClassParticipant.class_id == database.ClassSchedule.id)\
        .filter(database.ClassParticipant.user_id == user_id)\
        .all()
    
    classes = []
    for c, c_end in user_classes:
        cdict = database.dict_helper(c)
        cdict['end_date'] = c_end.strftime('%Y-%m-%d') if c_end else None
        classes.append(cdict)
    
    return render_template('user_profile.html', user=user, sub=sub, stats=stats, logs=logs, classes=classes)

@app.route('/user/<int:user_id>/edit', methods=['GET', 'POST'])
def edit_user(user_id):
    if request.method == 'POST':
        if 'extend_days' in request.form:
             days = int(request.form['extend_days'])
             database.extend_current_subscription(user_id, days)
        else:
             name = request.form['name']
             phone = request.form['phone']
             rfid = request.form['rfid_tag']
             database.update_user(user_id, name, phone, rfid)
        return redirect(url_for('get_users_route'))

    user = database.get_user_by_id(user_id)
    sub = database.get_active_subscription(user_id)
    return render_template('edit_user.html', user=user, sub=sub)

@app.route('/user/<int:user_id>/delete', methods=['POST'])
def delete_user(user_id):
    database.delete_user(user_id)
    return redirect(url_for('get_users_route'))

@app.route('/log/<int:log_id>/delete', methods=['POST'])
def delete_user_log(log_id):
    database.delete_access_log(log_id)
    # Redirect back to where the user came from (profile or admin dashboard)
    return redirect(request.referrer or url_for('admin'))

@app.route('/admin')
def admin():
    logs_data = database.db.session.query(database.AccessLog, database.User.name)\
        .join(database.User, database.AccessLog.user_id == database.User.id)\
        .order_by(database.AccessLog.timestamp.desc())\
        .limit(50).all()
        
    logs = []
    for log, name in logs_data:
        l_dict = database.dict_helper(log)
        l_dict['name'] = name
        # Convert timestamp to string for Jinja
        if hasattr(l_dict['timestamp'], 'strftime'):
            l_dict['timestamp'] = l_dict['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
        logs.append(l_dict)

    subscription_types = database.SubscriptionType.query.all()
    classes = database.get_all_classes()
    sub_stats = database.get_subscription_stats()
    class_stats = database.get_class_stats()
        
    return render_template('admin.html', logs=logs, subscription_types=subscription_types, classes=classes, sub_stats=sub_stats, class_stats=class_stats)

@app.route('/admin/log/<int:log_id>/delete', methods=['POST'])
def delete_log(log_id):
    database.delete_log(log_id)
    return redirect(url_for('admin'))

@app.route('/admin/subscription_types', methods=['POST'])
def create_subscription_type():
    name = request.form.get('name')
    entries_per_week = request.form.get('entries_per_week')
    duration_days = request.form.get('duration_days')
    price = request.form.get('price')
    
    database.create_subscription_type(name, entries_per_week, duration_days, price)
    return redirect(url_for('admin'))

@app.route('/admin/subscription_types/<int:type_id>/delete', methods=['POST'])
def delete_subscription_type(type_id):
    database.delete_subscription_type(type_id)
    return redirect(url_for('admin'))

@app.route('/admin/classes', methods=['POST'])
def create_class_schedule():
    name = request.form.get('name')
    day_of_week = request.form.get('day_of_week')
    start_time = request.form.get('start_time')
    capacity = request.form.get('capacity')
    price = request.form.get('price', 0.0)
    
    database.create_class_schedule(name, day_of_week, start_time, capacity, price)
    return redirect(url_for('admin'))

@app.route('/admin/classes/<int:class_id>/delete', methods=['POST'])
def delete_class_schedule(class_id):
    database.delete_class_schedule(class_id)
    return redirect(url_for('admin'))

@app.route('/admin/subscription_types/<int:type_id>/edit', methods=['POST'])
def edit_subscription_type(type_id):
    name = request.form.get('name')
    entries_per_week = request.form.get('entries_per_week')
    duration_days = request.form.get('duration_days')
    price = request.form.get('price')
    database.update_subscription_type(type_id, name, entries_per_week, duration_days, price)
    return redirect(url_for('admin'))

@app.route('/admin/classes/<int:class_id>/edit', methods=['POST'])
def edit_class_schedule(class_id):
    name = request.form.get('name')
    day_of_week = request.form.get('day_of_week')
    start_time = request.form.get('start_time')
    capacity = request.form.get('capacity')
    price = request.form.get('price', 0.0)
    database.update_class_schedule(class_id, name, day_of_week, start_time, capacity, price)
    return redirect(url_for('admin'))

# import webview  # Dezactivat - nu e necesar pe server web
# import threading

# def start_server():
#     app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

@app.route('/reports')
def reports():
    stats = database.get_report_stats()
    return render_template('reports.html', **stats)

if __name__ == '__main__':
    # Server web - rulează direct Flask
    app.run(host='0.0.0.0', port=5000, debug=False)
