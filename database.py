import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    phone = db.Column(db.String, nullable=False, unique=True)
    rfid_tag = db.Column(db.String, nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class SubscriptionType(db.Model):
    __tablename__ = 'subscription_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    entries_per_week = db.Column(db.Integer)
    duration_days = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)

class ActiveSubscription(db.Model):
    __tablename__ = 'active_subscriptions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    type_id = db.Column(db.Integer, db.ForeignKey('subscription_types.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)

class AccessLog(db.Model):
    __tablename__ = 'access_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.now)
    allowed = db.Column(db.Boolean, nullable=False)
    reason = db.Column(db.String)

def init_db(app):
    with app.app_context():
        db.create_all()
        
        # Populate initial subscription types if needed
        if not SubscriptionType.query.first():
            types = [
                SubscriptionType(name='Unlimited access', entries_per_week=None, duration_days=30, price=50.0),
                SubscriptionType(name='3 Sessions / Week', entries_per_week=3, duration_days=30, price=30.0),
                SubscriptionType(name='2 Sessions / Week', entries_per_week=2, duration_days=30, price=20.0)
            ]
            db.session.add_all(types)
            db.session.commit()

def dict_helper(obj):
    if obj is None:
        return None
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}

def get_user_by_rfid(rfid_tag):
    user = User.query.filter_by(rfid_tag=rfid_tag).first()
    return dict_helper(user)

def create_user(name, phone, rfid_tag):
    try:
        user = User(name=name, phone=phone, rfid_tag=rfid_tag)
        db.session.add(user)
        db.session.commit()
        return user.id
    except Exception as e:
        print(f"Error creating user: {e}")
        db.session.rollback()
        return None

def assign_subscription(user_id, type_id):
    sub_type = SubscriptionType.query.get(type_id)
    if not sub_type:
        return False
        
    start_date = datetime.date.today()
    end_date = start_date + datetime.timedelta(days=sub_type.duration_days)
    
    sub = ActiveSubscription(
        user_id=user_id,
        type_id=type_id,
        start_date=start_date,
        end_date=end_date
    )
    db.session.add(sub)
    db.session.commit()
    return True

def log_access(user_id, allowed, reason):
    log = AccessLog(user_id=user_id, allowed=allowed, reason=reason)
    db.session.add(log)
    db.session.commit()

def check_access(user_id):
    today = datetime.date.today()
    
    subscription_data = db.session.query(ActiveSubscription, SubscriptionType)\
        .join(SubscriptionType, ActiveSubscription.type_id == SubscriptionType.id)\
        .filter(ActiveSubscription.user_id == user_id)\
        .filter(ActiveSubscription.start_date <= today)\
        .filter(ActiveSubscription.end_date >= today)\
        .order_by(ActiveSubscription.end_date.desc())\
        .first()

    # Calculate start of week globally
    start_of_week = today - datetime.timedelta(days=today.weekday())
    count = AccessLog.query\
        .filter(AccessLog.user_id == user_id)\
        .filter(AccessLog.allowed == True)\
        .filter(AccessLog.timestamp >= start_of_week)\
        .count()

    if not subscription_data:
        return False, "No active subscription found.", "denied", None, count
        
    sub, sub_type = subscription_data
    sub_name = sub_type.name

    if sub_type.entries_per_week:
        if count >= sub_type.entries_per_week:
            return False, f"Weekly limit reached ({count}/{sub_type.entries_per_week}).", "denied", sub_name, count

    days_left = (sub.end_date - today).days
    
    if days_left <= 7:
        return True, f"Access Granted. Expires in {days_left} days ({sub.end_date})", "warning", sub_name, count

    return True, "Access Granted", "allowed", sub_name, count

def get_all_users():
    results = db.session.query(User, ActiveSubscription.end_date, SubscriptionType.name.label('sub_name'))\
        .outerjoin(ActiveSubscription, (User.id == ActiveSubscription.user_id) & (ActiveSubscription.end_date >= datetime.date.today()))\
        .outerjoin(SubscriptionType, ActiveSubscription.type_id == SubscriptionType.id)\
        .all()
        
    users = []
    for user, end_date, sub_name in results:
        u_dict = dict_helper(user)
        if end_date and isinstance(end_date, datetime.date):
            u_dict['end_date'] = end_date.strftime('%Y-%m-%d')
        else:
            u_dict['end_date'] = end_date
        u_dict['sub_name'] = sub_name
        users.append(u_dict)
    return users

def get_user_by_id(user_id):
    user = User.query.get(user_id)
    return dict_helper(user)

def get_active_subscription(user_id):
    sub_data = db.session.query(ActiveSubscription, SubscriptionType)\
        .join(SubscriptionType, ActiveSubscription.type_id == SubscriptionType.id)\
        .filter(ActiveSubscription.user_id == user_id)\
        .filter(ActiveSubscription.end_date >= datetime.date.today())\
        .order_by(ActiveSubscription.end_date.desc())\
        .first()
        
    if sub_data:
        sub, sub_type = sub_data
        s_dict = dict_helper(sub)
        s_dict['sub_name'] = sub_type.name
        return s_dict
    return None

def update_user(user_id, name, phone, rfid_tag):
    try:
        user = User.query.get(user_id)
        if user:
            user.name = name
            user.phone = phone
            user.rfid_tag = rfid_tag
            db.session.commit()
    except Exception as e:
        print(f"Error updating user: {e}")
        db.session.rollback()

def extend_current_subscription(user_id, days):
    try:
        sub = ActiveSubscription.query\
            .filter_by(user_id=user_id)\
            .filter(ActiveSubscription.end_date >= datetime.date.today())\
            .order_by(ActiveSubscription.end_date.desc())\
            .first()
            
        if sub:
            sub.end_date = sub.end_date + datetime.timedelta(days=days)
            db.session.commit()
    except Exception as e:
        print(f"Error extending subscription: {e}")
        db.session.rollback()

def delete_user(user_id):
    try:
        AccessLog.query.filter_by(user_id=user_id).delete()
        ActiveSubscription.query.filter_by(user_id=user_id).delete()
        User.query.filter_by(id=user_id).delete()
        db.session.commit()
        return True
    except Exception as e:
        print(f"Error deleting user: {e}")
        db.session.rollback()
        return False

def delete_log(log_id):
    try:
        AccessLog.query.filter_by(id=log_id).delete()
        db.session.commit()
        return True
    except Exception as e:
        print(f"Error deleting log: {e}")
        db.session.rollback()
        return False

def get_last_log(user_id):
    try:
        log = AccessLog.query.filter_by(user_id=user_id).order_by(AccessLog.timestamp.desc()).first()
        if log:
            l_dict = dict_helper(log)
            # Format timestamp safely
            if hasattr(l_dict['timestamp'], 'strftime'):
                l_dict['timestamp'] = l_dict['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
            return l_dict
    except Exception as e:
        print(f"Error fetching last log: {e}")
    return None
