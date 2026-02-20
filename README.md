# Access Control App

A Flask-based access control system designed to manage member subscriptions, RFID tag scanning, and access logs.

## Features
- **User Management**: Register and edit users with their phone numbers and RFID tags.
- **Subscription Plans**: Assign predefined subscription packages (e.g., unlimited, 3 sessions/week, 2 sessions/week).
- **RFID Scanning Simulator**: Simulate RFID tag scans to verify access based on the user's current subscription status and weekly limits.
- **Access Logs**: Track granted and denied access attempts. Administrators can delete specific log entries.

## Tech Stack
- **Backend**: Python, Flask
- **Database**: SQLite3
- **Frontend**: HTML, Tailwind CSS (via CDN)

## Setup & Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/prundusdanielioan/accessControl.git
   cd accessControl
   ```

2. **Create a virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the application:**
   ```bash
   python3 app.py
   ```
   The SQLite database (`access_control.db`) is automatically initialized on the first run.

## Usage
- Open your browser to `http://127.0.0.1:5000/` to access the main interface.
- Navigate to `/register` to enroll a new user and assign a package.
- Scan (or manually enter) an RFID tag on the home screen to simulate an entry attempt.
- Visit `/admin` to view access logs and manage users.
