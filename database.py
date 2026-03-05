import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_babel import gettext as _

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

class ClassSchedule(db.Model):
    __tablename__ = 'class_schedules'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False) # 0=Monday, 6=Sunday
    start_time = db.Column(db.String(5), nullable=False) # Format: HH:MM
    capacity = db.Column(db.Integer)

class ClassParticipant(db.Model):
    __tablename__ = 'class_participants'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('class_schedules.id'), nullable=False)
    enrolled_at = db.Column(db.DateTime, default=datetime.datetime.now)

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
    if not type_id:
        return False
        
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

def enroll_user_in_class(user_id, class_id):
    try:
        if not class_id:
            return False
            
        # Check if already enrolled
        existing = ClassParticipant.query.filter_by(user_id=user_id, class_id=class_id).first()
        if existing:
            return True
            
        participant = ClassParticipant(user_id=user_id, class_id=class_id)
        db.session.add(participant)
        db.session.commit()
        return True
    except Exception as e:
        print(f"Error enrolling user in class: {e}")
        db.session.rollback()
        return False

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
        # Check all enrolled classes for this user
        all_enrolled = db.session.query(ClassSchedule)\
            .join(ClassParticipant, ClassParticipant.class_id == ClassSchedule.id)\
            .filter(ClassParticipant.user_id == user_id)\
            .all()
            
        if not all_enrolled:
            return False, _("No active subscription or class found."), "denied", None, count
            
        # Check if any class is scheduled for today
        current_day_of_week = today.weekday()
        classes_today = [c for c in all_enrolled if c.day_of_week == current_day_of_week]
        
        if classes_today:
            now = datetime.datetime.now()
            valid_classes_now = []
            
            for c in classes_today:
                try:
                    h, m = map(int, c.start_time.split(':'))
                    dt_class = datetime.datetime.combine(today, datetime.time(h, m))
                    
                    # Allowed window: 60 mins before class, up to 30 mins after
                    if (dt_class - datetime.timedelta(minutes=60)) <= now <= (dt_class + datetime.timedelta(minutes=30)):
                        valid_classes_now.append(c)
                except Exception:
                    # Fallback if time format is unexpected
                    valid_classes_now.append(c)
                    
            if valid_classes_now:
                class_names_today = ", ".join([c.name for c in valid_classes_now])
                return True, _("Access Granted for Class: %(classes)s", classes=class_names_today), "allowed", class_names_today, count
            else:
                class_details = ", ".join([f"{c.name} ({c.start_time})" for c in classes_today])
                return False, _("Access Denied. Next class today at: %(details)s", details=class_details), "denied", class_details, count
            
        # If they have classes but none today
        class_names_all = ", ".join([c.name for c in all_enrolled])
        return False, _("Access Denied. Your classes (%(classes)s) are not scheduled for today.", classes=class_names_all), "denied", class_names_all, count
        
    sub, sub_type = subscription_data
    sub_name = sub_type.name

    # Append any enrolled classes to the sub_name for display
    user_classes = db.session.query(ClassSchedule.name)\
        .join(ClassParticipant, ClassParticipant.class_id == ClassSchedule.id)\
        .filter(ClassParticipant.user_id == user_id)\
        .all()
    class_names = [c[0] for c in user_classes]
    
    if class_names:
        sub_name = f"{sub_name} + {', '.join(class_names)}"

    if sub_type.entries_per_week:
        if count >= sub_type.entries_per_week:
            return False, _("Weekly limit reached (%(count)s/%(total)s).", count=count, total=sub_type.entries_per_week), "denied", sub_name, count

    days_left = (sub.end_date - today).days
    
    if days_left <= 7:
        return True, _("Access Granted. Expires in %(days)s days (%(date)s)", days=days_left, date=sub.end_date), "warning", sub_name, count

    return True, _("Access Granted"), "allowed", sub_name, count

def get_users_paginated(page=1, per_page=50, search_name=None, search_phone=None, search_sub_id=None, search_class_id=None):
    query = db.session.query(User, ActiveSubscription.end_date, SubscriptionType.name.label('sub_name'), SubscriptionType.id.label('sub_type_id'))\
        .outerjoin(ActiveSubscription, (User.id == ActiveSubscription.user_id) & (ActiveSubscription.end_date >= datetime.date.today()))\
        .outerjoin(SubscriptionType, ActiveSubscription.type_id == SubscriptionType.id)
        
    if search_name:
        query = query.filter(User.name.ilike(f"%{search_name}%"))
    if search_phone:
        query = query.filter(User.phone.ilike(f"%{search_phone}%"))
        
    if search_sub_id:
        if search_sub_id == 'none':
            query = query.filter(ActiveSubscription.id == None)
        else:
            query = query.filter(SubscriptionType.id == search_sub_id)
            
    if search_class_id:
        query = query.join(ClassParticipant, User.id == ClassParticipant.user_id)\
                     .filter(ClassParticipant.class_id == search_class_id)
            
    query = query.order_by(User.id.desc())
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)
        
    users = []
    for user, end_date, sub_name, sub_type_id in paginated.items:
        u_dict = dict_helper(user)
        
        user_classes = db.session.query(ClassSchedule.name)\
            .join(ClassParticipant, ClassParticipant.class_id == ClassSchedule.id)\
            .filter(ClassParticipant.user_id == user.id)\
            .all()
        class_names = [c[0] for c in user_classes]

        if end_date and isinstance(end_date, datetime.date):
            u_dict['end_date'] = end_date.strftime('%Y-%m-%d')
        else:
            u_dict['end_date'] = end_date
            
        if class_names:
            u_dict['sub_name'] = f"{sub_name} + {', '.join(class_names)}" if sub_name else ", ".join(class_names)
        else:
            u_dict['sub_name'] = sub_name
            
        users.append(u_dict)
        
    return {
        'items': users,
        'pa_total': paginated.total,
        'pa_pages': paginated.pages,
        'pa_page': paginated.page,
        'pa_has_next': paginated.has_next,
        'pa_has_prev': paginated.has_prev,
        'pa_next_num': paginated.next_num,
        'pa_prev_num': paginated.prev_num
    }

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
        ClassParticipant.query.filter_by(user_id=user_id).delete()
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

def create_subscription_type(name, entries_per_week, duration_days, price):
    try:
        entries = int(entries_per_week) if entries_per_week else None
        sub_type = SubscriptionType(
            name=name,
            entries_per_week=entries,
            duration_days=int(duration_days),
            price=float(price)
        )
        db.session.add(sub_type)
        db.session.commit()
        return True
    except Exception as e:
        print(f"Error creating subscription type: {e}")
        db.session.rollback()
        return False

def delete_subscription_type(type_id):
    try:
        # Prevent deletion if active subscriptions exist
        active_subs = ActiveSubscription.query.filter_by(type_id=type_id).first()
        if active_subs:
            return False, _("Cannot delete. There are active users with this subscription.")
        
        SubscriptionType.query.filter_by(id=type_id).delete()
        db.session.commit()
        return True, _("Subscription type deleted.")
    except Exception as e:
        print(f"Error deleting subscription type: {e}")
        db.session.rollback()
        return False, _("Error deleting subscription type.")

def create_class_schedule(name, day_of_week, start_time, capacity):
    try:
        # Validate time format loosely
        if ':' not in start_time or len(start_time) > 5:
            start_time = "00:00"
            
        cap = int(capacity) if capacity else None
        
        new_class = ClassSchedule(
            name=name,
            day_of_week=int(day_of_week),
            start_time=start_time,
            capacity=cap
        )
        db.session.add(new_class)
        db.session.commit()
        return True
    except Exception as e:
        print(f"Error creating class schedule: {e}")
        db.session.rollback()
        return False

def get_all_classes():
    classes = ClassSchedule.query.order_by(ClassSchedule.day_of_week, ClassSchedule.start_time).all()
    return [dict_helper(c) for c in classes]

def delete_class_schedule(class_id):
    try:
        ClassSchedule.query.filter_by(id=class_id).delete()
        db.session.commit()
        return True
    except Exception as e:
        print(f"Error deleting class schedule: {e}")
        db.session.rollback()
        return False

def get_subscription_stats():
    stats = []
    sub_types = SubscriptionType.query.all()
    today = datetime.date.today()
    for st in sub_types:
        count = db.session.query(db.func.count(ActiveSubscription.id))\
                .filter(ActiveSubscription.type_id == st.id)\
                .filter(ActiveSubscription.end_date >= today)\
                .scalar()
        stats.append({'name': st.name, 'active_count': count})
    return stats

def get_class_stats():
    stats = []
    classes = ClassSchedule.query.order_by(ClassSchedule.day_of_week, ClassSchedule.start_time).all()
    days_map = ['Luni', 'Marți', 'Miercuri', 'Joi', 'Vineri', 'Sâmbătă', 'Duminică']
    for c in classes:
        count = db.session.query(db.func.count(ClassParticipant.id))\
                .filter(ClassParticipant.class_id == c.id)\
                .scalar()
        
        cap = c.capacity if c.capacity else 0
        pct = (count / cap * 100) if cap > 0 else 0
        
        time_str = c.start_time.strftime('%H:%M') if hasattr(c.start_time, 'strftime') else str(c.start_time)
        day_name = days_map[c.day_of_week] if 0 <= c.day_of_week <= 6 else str(c.day_of_week)
        
        stats.append({
            'name': f"{c.name} ({day_name} {time_str})", 
            'enrolled': count, 
            'capacity': cap, 
            'percentage': round(pct)
        })
    return stats

def get_user_stats(user_id):
    today = datetime.date.today()
    # Total visits
    total_visits = db.session.query(db.func.count(AccessLog.id))\
        .filter(AccessLog.user_id == user_id)\
        .filter(AccessLog.allowed == True)\
        .scalar()
        
    # Visits this month
    monthly_visits = db.session.query(db.func.count(AccessLog.id))\
        .filter(AccessLog.user_id == user_id)\
        .filter(AccessLog.allowed == True)\
        .filter(db.extract('year', AccessLog.timestamp) == today.year)\
        .filter(db.extract('month', AccessLog.timestamp) == today.month)\
        .scalar()
        
    return {
        'total_visits': total_visits,
        'monthly_visits': monthly_visits
    }

def get_user_logs(user_id, limit=100):
    logs = AccessLog.query.filter_by(user_id=user_id)\
        .order_by(AccessLog.timestamp.desc())\
        .limit(limit).all()
        
    logs_list = []
    for log in logs:
        l_dict = dict_helper(log)
        if hasattr(l_dict['timestamp'], 'strftime'):
            l_dict['timestamp'] = l_dict['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
        logs_list.append(l_dict)
    return logs_list

def delete_access_log(log_id):
    try:
        AccessLog.query.filter_by(id=log_id).delete()
        db.session.commit()
        return True
    except Exception as e:
        print(f"Error deleting access log: {e}")
        db.session.rollback()
        return False
