from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
db = SQLAlchemy()



class user(db.Model):
    __tablename__ ='user_table'
    id = db.Column(db.Integer , primary_key= True, autoincrement = True)
    username = db.Column(db.String)
    email = db.Column(db.String , unique = True)
    phone_no = db.Column(db.Integer)
    password = db.Column(db.String)
    date_of_join = db.Column(db.DateTime, nullable=True)
    role = db.Column(db.String)
    service_type = db.Column(db.String)
    experience = db.Column(db.Integer)
    description = db.Column(db.String)
    cv = db.Column(db.String)
    city = db.Column(db.String)
    pincode = db.Column(db.Integer)
    area = db.Column(db.Integer)
    status = db.Column(db.String)
    ratings = db.Column(db.String)
    
class ServiceRequest(db.Model):
    __tablename__ = 'service_requests'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    service_name = db.Column(db.String,)
    customer_id = db.Column(db.Integer, db.ForeignKey('user_table.id'))
    customer_name = db.Column(db.String)
    customer_email = db.Column(db.String)
    customer_phone_no = db.Column(db.Integer)
    customer_city = db.Column(db.String)
    area = db.Column(db.String)
    customer_pincode = db.Column(db.Integer)
    remarks = db.Column(db.String)
    date_of_request = db.Column(db.DateTime, default=datetime.utcnow)
    pending_date_change = db.Column(db.DateTime, nullable=True)
    service_status = db.Column(db.String, default='Pending')
    professional_id = db.Column(db.Integer, db.ForeignKey('user_table.id'))
    date_of_completion = db.Column(db.DateTime, nullable=True)
    ratings = db.Column(db.String)
    unique_code = db.Column(db.String)
    
    
class service(db.Model):
    __tablename__ ='services'
    id = db.Column(db.Integer , primary_key= True, autoincrement = True)
    name = db.Column(db.String)
    description = db.Column(db.String)
    price = db.Column(db.String)
    city = db.Column(db.String)
    time_required = db.Column(db.String)
    image_location = db.Column(db.String)  # New column for image location
    
class RejectedRequest(db.Model):
    __tablename__ = 'rejected_requests'
    id = db.Column(db.Integer, primary_key=True)
    service_request_id = db.Column(db.Integer, db.ForeignKey('service_requests.id'), nullable=False)
    professional_id = db.Column(db.Integer, db.ForeignKey('user_table.id'), nullable=False)

class RejectedDate(db.Model):
    __tablename__ = 'rejected_dates'
    id = db.Column(db.Integer, primary_key=True)
    service_request_id = db.Column(db.Integer, db.ForeignKey('service_requests.id'), nullable=False)
    rejected_date = db.Column(db.DateTime, nullable=False)

    
class Report(db.Model):
    __tablename__ = 'report'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    email = db.Column(db.String, nullable=False)
    message = db.Column(db.String, nullable=False)