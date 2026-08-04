from datetime import datetime

from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


class user(db.Model):
    __tablename__ = "user_table"

    id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True,
    )

    username = db.Column(
        db.String(150),
        nullable=False,
    )

    email = db.Column(
        db.String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    # Phone numbers must be strings, not integers.
    phone_no = db.Column(
        db.String(20),
        nullable=True,
    )

    password = db.Column(
        db.String(255),
        nullable=False,
    )

    date_of_join = db.Column(
        db.DateTime,
        nullable=True,
        default=datetime.utcnow,
    )

    role = db.Column(
        db.String(50),
        nullable=False,
    )

    service_type = db.Column(
        db.String(150),
        nullable=True,
    )

    experience = db.Column(
        db.Integer,
        nullable=True,
    )

    description = db.Column(
        db.Text,
        nullable=True,
    )

    cv = db.Column(
        db.String(255),
        nullable=True,
    )

    city = db.Column(
        db.String(100),
        nullable=True,
    )

    pincode = db.Column(
        db.Integer,
        nullable=True,
    )

    area = db.Column(
        db.String(150),
        nullable=True,
    )

    status = db.Column(
        db.String(50),
        nullable=True,
    )

    ratings = db.Column(
        db.String(50),
        nullable=True,
    )


class ServiceRequest(db.Model):
    __tablename__ = "service_requests"

    id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True,
    )

    service_name = db.Column(
        db.String(150),
        nullable=False,
    )

    customer_id = db.Column(
        db.Integer,
        db.ForeignKey("user_table.id"),
        nullable=False,
    )

    customer_name = db.Column(
        db.String(150),
        nullable=True,
    )

    customer_email = db.Column(
        db.String(255),
        nullable=True,
    )

    # Store phone numbers as strings.
    customer_phone_no = db.Column(
        db.String(20),
        nullable=True,
    )

    customer_city = db.Column(
        db.String(100),
        nullable=True,
    )

    area = db.Column(
        db.String(150),
        nullable=True,
    )

    customer_pincode = db.Column(
        db.Integer,
        nullable=True,
    )

    remarks = db.Column(
        db.Text,
        nullable=True,
    )

    date_of_request = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    pending_date_change = db.Column(
        db.DateTime,
        nullable=True,
    )

    service_status = db.Column(
        db.String(50),
        default="Pending",
        nullable=False,
    )

    professional_id = db.Column(
        db.Integer,
        db.ForeignKey("user_table.id"),
        nullable=True,
    )

    date_of_completion = db.Column(
        db.DateTime,
        nullable=True,
    )

    ratings = db.Column(
        db.String(50),
        nullable=True,
    )

    unique_code = db.Column(
        db.String(100),
        nullable=True,
    )


class service(db.Model):
    __tablename__ = "services"

    id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True,
    )

    name = db.Column(
        db.String(150),
        nullable=False,
    )

    description = db.Column(
        db.Text,
        nullable=True,
    )

    price = db.Column(
        db.String(50),
        nullable=True,
    )

    city = db.Column(
        db.String(100),
        nullable=True,
    )

    time_required = db.Column(
        db.String(50),
        nullable=True,
    )

    image_location = db.Column(
        db.String(255),
        nullable=True,
    )


class RejectedRequest(db.Model):
    __tablename__ = "rejected_requests"

    id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True,
    )

    service_request_id = db.Column(
        db.Integer,
        db.ForeignKey("service_requests.id"),
        nullable=False,
    )

    professional_id = db.Column(
        db.Integer,
        db.ForeignKey("user_table.id"),
        nullable=False,
    )


class RejectedDate(db.Model):
    __tablename__ = "rejected_dates"

    id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True,
    )

    service_request_id = db.Column(
        db.Integer,
        db.ForeignKey("service_requests.id"),
        nullable=False,
    )

    rejected_date = db.Column(
        db.DateTime,
        nullable=False,
    )


class Report(db.Model):
    __tablename__ = "report"

    id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True,
    )

    name = db.Column(
        db.String(150),
        nullable=False,
    )

    email = db.Column(
        db.String(255),
        nullable=False,
    )

    message = db.Column(
        db.Text,
        nullable=False,
    )
