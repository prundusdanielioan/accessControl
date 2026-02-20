from flask import Flask, render_template, request, jsonify, redirect, url_for
import database
import datetime

app = Flask(__name__)

# Initialize DB
database.init_db()

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
    
    database.log_access(user['id'], allowed, message)
    
    return jsonify({
        'status': status_code,
        'user_name': user['name'],
        'message': message,
        'sub_name': sub_name,
        'weekly_count': display_count
    })

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        phone = request.form['phone']
        rfid_tag = request.form['rfid_tag']
        sub_type_id = request.form['subscription_type']
        
        # Check if user exists
        existing_user = database.get_user_by_rfid(rfid_tag)
        if existing_user:
             return render_template('register.html', error="RFID Tag already registered!")

        user_id = database.create_user(name, phone, rfid_tag)
        if user_id:
            database.assign_subscription(user_id, sub_type_id)
            return redirect(url_for('index'))
        else:
             return render_template('register.html', error="Error creating user (Phone might use used).")

    # Get subscription types for dropdown
    conn = database.get_db_connection()
    sub_types = conn.execute('SELECT * FROM subscription_types').fetchall()
    conn.close()
    
    rfid_prefill = request.args.get('rfid', '')
    
    return render_template('register.html', sub_types=sub_types, rfid_prefill=rfid_prefill)

@app.route('/users')
def get_users():
    users = database.get_all_users()
    return render_template('users.html', users=users)

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
        return redirect(url_for('get_users'))

    user = database.get_user_by_id(user_id)
    sub = database.get_active_subscription(user_id)
    return render_template('edit_user.html', user=user, sub=sub)

@app.route('/user/<int:user_id>/delete', methods=['POST'])
def delete_user(user_id):
    database.delete_user(user_id)
    return redirect(url_for('get_users'))

@app.route('/admin')
def admin():
    conn = database.get_db_connection()
    logs = conn.execute('''
        SELECT l.*, u.name 
        FROM access_logs l
        JOIN users u ON l.user_id = u.id
        ORDER BY l.timestamp DESC LIMIT 50
    ''').fetchall()
    conn.close()
    return render_template('admin.html', logs=logs)

@app.route('/admin/log/<int:log_id>/delete', methods=['POST'])
def delete_log(log_id):
    database.delete_log(log_id)
    return redirect(url_for('admin'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
