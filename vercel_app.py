from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from datetime import datetime
from sqlalchemy import distinct, or_, desc
from model import *
import os
import random
import string
from sqlalchemy.sql import func
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__, static_folder='static')
app.secret_key = 'your_secret_key'

# Vercel-specific configuration
current_dir = os.path.abspath(os.path.dirname(__file__))
if os.environ.get('VERCEL'):
    # Use temporary directory for SQLite in Vercel environment
    db_path = "/tmp/data_base.sqlite3"
    UPLOAD_FOLDER = "/tmp/cv"
else:
    # Local development configuration
    db_path = os.path.join(current_dir, 'data_base.sqlite3')
    UPLOAD_FOLDER = os.path.join(current_dir, 'static', 'cv')

ALLOWED_EXTENSIONS = {'pdf'}

app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{db_path}"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure upload directory exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Initialize database
db.init_app(app)
with app.app_context():
    db.create_all()

def get_service_by_id(service_id):
    for service in services:
        if service["id"] == service_id:
            return service
    return None

@app.route('/')
def home():
    search_query = request.args.get('search', '').strip()

    services = []

    if search_query:
        # Match service name with search input
        matched_services = service.query.filter(
            service.name.ilike(f"%{search_query}%")
        ).all()

        # Only keep one service per unique name
        seen_names = set()
        for s in matched_services:
            if s.name not in seen_names:
                services.append(s)
                seen_names.add(s.name)
    else:
        # No search query: fetch one entry per distinct name
        distinct_names = db.session.query(service.name).distinct().all()
        for name_tuple in distinct_names:
            first_service = service.query.filter_by(name=name_tuple[0]).first()
            services.append(first_service)

    return render_template("home_dashboard.html", services=services, search_query=search_query)





@app.route('/login.html', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        form_email = request.form['email']
        form_password = request.form['password']

        user_obj = user.query.filter_by(email=form_email).first()

        if user_obj:
            # First check if password hash matches
            hashed_check = check_password_hash(user_obj.password, form_password)
            
            # If not, fallback to plain text
            if hashed_check or user_obj.password == form_password:
                session['user_id'] = user_obj.id
                session['role'] = user_obj.role

                flash("Logged in successfully.", "success")

                if user_obj.role == 'customer':
                    if user_obj.status == 'blocked':
                        return redirect(url_for('block'))
                    else:
                        return redirect(url_for('customer_dashboard'))

                elif user_obj.role == 'service professional':
                    if user_obj.status == 'blocked':
                        return redirect(url_for('block'))
                    elif user_obj.status == 'approved':
                        return redirect(url_for('professional_dashboard'))
                    else:
                        return redirect(url_for('pending'))

                elif user_obj.role == 'admin':
                    return redirect(url_for('admin_dashboard'))
            else:
                flash("Invalid password.", "error")
        else:
            flash("Invalid email.", "error")

    return render_template('login.html')





@app.route('/block', methods=['GET', 'POST'])
def block():
    return render_template('block.html')

@app.route('/pending', methods=['GET', 'POST'])
def pending():
    return render_template('pending.html')




# Service Professional Dashboard Route

@app.route('/professional/dashboard')
def professional_dashboard():
    if 'user_id' not in session or session.get('role') != 'service professional':
        flash("You need to log in as a service professional to access this page.", "error")
        return redirect(url_for('login'))

    user_id = session['user_id']
    professional = user.query.get(user_id)
    search_query = request.args.get('search', '').strip()

    def match_search(query):
        if search_query:
            return query.filter(
                (ServiceRequest.customer_name.ilike(f"%{search_query}%")) |
                (ServiceRequest.date_of_request.cast(db.String).ilike(f"%{search_query}%"))
            )
        return query

    # Pending
    pending_query = ServiceRequest.query.filter(
        ServiceRequest.service_status == 'Requested',
        ServiceRequest.service_name == professional.service_type,
        ServiceRequest.customer_city == professional.city,
        ~ServiceRequest.id.in_(
            db.session.query(RejectedRequest.service_request_id)
            .filter_by(professional_id=professional.id)
        )
    )
    pending_requests = match_search(pending_query).order_by(ServiceRequest.date_of_request).all()

    # Accepted
    accepted_query = ServiceRequest.query.filter_by(
        professional_id=user_id, service_status='Accepted'
    )
    accepted_requests = match_search(accepted_query).order_by(ServiceRequest.date_of_request).all()

    # Completed
    completed_query = ServiceRequest.query.filter_by(
        professional_id=user_id, service_status='Completed'
    )
    completed_requests = match_search(completed_query).order_by(desc(ServiceRequest.date_of_completion)).all()

    # Rejected
    rejected_query = db.session.query(ServiceRequest).join(RejectedRequest).filter(
        RejectedRequest.professional_id == user_id,
        ServiceRequest.id == RejectedRequest.service_request_id
    )
    rejected_requests = match_search(rejected_query).order_by(desc(ServiceRequest.date_of_request)).all()

    return render_template(
        'professional_dashboard.html',
        professional=professional,
        pending_requests=pending_requests,
        accepted_requests=accepted_requests,
        completed_requests=completed_requests,
        rejected_requests=rejected_requests,
        search_query=search_query
    )



@app.route('/professional/accept_request/<int:request_id>', methods=['POST'])
def accept_request(request_id):
    service_request = ServiceRequest.query.get(request_id)
    
    if not service_request or service_request.service_status != 'Requested':
        flash("Service request cannot be accepted.", "error")
        return redirect(url_for('professional_dashboard'))
    
    professional_id = session['user_id']
    request_date = service_request.date_of_request.date()

    # Check already accepted requests on the same day
    accepted_requests = ServiceRequest.query.filter(
        ServiceRequest.professional_id == professional_id,
        func.date(ServiceRequest.date_of_request) == request_date,
        ServiceRequest.service_status == 'Accepted'
    ).all()

    total_hours = 0
    for req in accepted_requests:
        service_details = service.query.filter_by(name=req.service_name).first()
        if service_details and service_details.time_required:
            try:
                total_hours += int(service_details.time_required)
            except ValueError:
                flash("Invalid time format in the service details.", "error")
                return redirect(url_for('professional_dashboard'))

    current_service = service.query.filter_by(name=service_request.service_name).first()
    if current_service and current_service.time_required:
        try:
            total_hours += int(current_service.time_required)
        except ValueError:
            flash("Invalid time format in the service details.", "error")
            return redirect(url_for('professional_dashboard'))

    if total_hours > 12:
        flash("You cannot accept this request as it exceeds the 12-hour daily work limit.", "error")
        return redirect(url_for('professional_dashboard'))

    # ✅ Generate a unique 8-character code (format: 12AB66CD)
    def generate_unique_code():
        return (
            ''.join(random.choices(string.digits, k=2)) +
            ''.join(random.choices(string.ascii_uppercase, k=2)) +
            ''.join(random.choices(string.digits, k=2)) +
            ''.join(random.choices(string.ascii_uppercase, k=2)) +
            ''.join(random.choices(string.digits, k=2))
        )

    service_request.service_status = 'Accepted'
    service_request.professional_id = professional_id
    service_request.unique_code = generate_unique_code()
    
    db.session.commit()

    flash("Service request accepted. Unique code has been generated.", "success")
    return redirect(url_for('professional_dashboard'))






@app.route('/professional/reject_request/<int:request_id>', methods=['POST'])
def reject_request(request_id):
    service_request = ServiceRequest.query.get(request_id)
    professional_id = session['user_id']
    if service_request and service_request.service_status == 'Requested':
        
        rejection = RejectedRequest(
            service_request_id=request_id,
            professional_id=professional_id
        )
        db.session.add(rejection)
        db.session.commit()
        flash("Service request rejected.", "success")
    else:
        flash("Service request cannot be rejected.", "error")
    return redirect(url_for('professional_dashboard'))


@app.route('/professional/close_request/<int:request_id>', methods=['POST'])
def close_request(request_id):
    service_request = ServiceRequest.query.get(request_id)

    if not service_request:
        flash("Service request not found.", "error")
        return redirect(url_for('professional_dashboard'))

    if service_request.service_status != 'Accepted' or service_request.professional_id != session.get('user_id'):
        flash("You are not authorized to complete this request.", "error")
        return redirect(url_for('professional_dashboard'))
    # Get the code submitted via form
    entered_code = request.form.get('verification_code')
    # Check if it matches the stored unique code
    if entered_code and entered_code == service_request.unique_code:
        service_request.service_status = 'Completed'
        service_request.date_of_completion = datetime.utcnow()
        db.session.commit()
        flash("Service request completed successfully.", "success")
    else:
        flash("Incorrect service code. Please try again.", "danger")
    return redirect(url_for('professional_dashboard'))

@app.route('/professional/approve_date_change/<int:request_id>', methods=['POST'])
def approve_date_change(request_id):
    service_request = ServiceRequest.query.get_or_404(request_id)

    if service_request.professional_id != session.get('user_id'):
        flash("Unauthorized access.", "error")
        return redirect(url_for('professional_dashboard'))

    if service_request.pending_date_change:
        service_request.date_of_request = service_request.pending_date_change
        service_request.pending_date_change = None
        db.session.commit()
        flash("Date change approved and updated.", "success")
    else:
        flash("No pending date change to approve.", "warning")

    return redirect(url_for('professional_dashboard'))


@app.route('/professional/reject_date_change/<int:request_id>', methods=['POST'])
def reject_date_change(request_id):
    service_request = ServiceRequest.query.get_or_404(request_id)

    if service_request.professional_id != session.get('user_id'):
        flash("Unauthorized access.", "error")
        return redirect(url_for('professional_dashboard'))

    if service_request.pending_date_change:
        # Save the rejected date
        rejected_entry = RejectedDate(
            service_request_id=request_id,
            rejected_date=service_request.pending_date_change
        )
        db.session.add(rejected_entry)

        # Clear the pending change
        service_request.pending_date_change = None
        db.session.commit()

        flash("Date change request rejected.", "info")
    else:
        flash("No pending date change to reject.", "warning")

    return redirect(url_for('professional_dashboard'))



@app.route('/professional_profile')
def professional_profile():
    professional_id = session.get('user_id')
    
    if not professional_id or session.get('role') != 'service professional':
        flash("Please log in to access your profile", "error")
        return redirect(url_for('login'))
    
    professional = user.query.get(professional_id)
            
    cities = [city[0] for city in db.session.query(service.city).distinct().all()]

    return render_template(
        'edit_service_professional_profile.html',
        professional=professional,
        cities=cities
    )
    
@app.route('/update_professional_profile', methods=['POST'])
def update_professional_profile():
    professional_id = session.get('user_id')
    if not professional_id:
        flash("Unauthorized access", "error")
        return redirect(url_for('login'))

    professional = user.query.get(professional_id)
    professional.username = request.form['username']
    professional.email = request.form['email']
    professional.phone_no = request.form['phone_no']
    professional.city = request.form['city']
    professional.description = request.form['description']
    db.session.commit()
    flash("Profile updated successfully!", "success")
    return redirect(url_for('professional_profile'))

# Professional Dashboard end here


# Customer dashboard started here
# Routes
@app.route('/customer_profile')
def customer_profile():
    customer_id = session.get('user_id')

    if not customer_id or session.get('role') != 'customer':
        flash("Please log in to access your profile", "error")
        return redirect(url_for('login'))

    customer = user.query.get(customer_id)
    search_query = request.args.get('search', '').strip()

    if search_query:
        service_requests = ServiceRequest.query.filter(
            ServiceRequest.customer_id == customer_id,
            ServiceRequest.service_name.ilike(f"%{search_query}%") |
            (ServiceRequest.date_of_request.cast(db.String).ilike(f"%{search_query}%"))
        ).order_by(desc(ServiceRequest.id)).all()
    else:
        service_requests = ServiceRequest.query.filter_by(
            customer_id=customer_id
        ).order_by(desc(ServiceRequest.id)).all()

    professionals = {}
    for req in service_requests:
        professional = user.query.get(req.professional_id)
        if professional:
            professionals[req.id] = professional

    # ✅ Fetch rejected date change history
    rejected_dates_map = {}
    for req in service_requests:
        rejected_dates = db.session.query(RejectedDate).filter_by(service_request_id=req.id).all()
        rejected_dates_map[req.id] = [r.rejected_date for r in rejected_dates]

    cities = [city[0] for city in db.session.query(service.city).distinct().all()]

    return render_template(
        'edit_customer_profile.html',
        customer=customer,
        service_requests=service_requests,
        professionals=professionals,
        cities=cities,
        search_query=search_query,
        rejected_dates_map=rejected_dates_map  # ✅ pass to template
    )


#

@app.route('/update_profile', methods=['POST'])
def update_profile():
    customer_id = session.get('user_id')
    if not customer_id:
        flash("Unauthorized access", "error")
        return redirect(url_for('login'))

    customer = user.query.get(customer_id)
    customer.username = request.form['username']
    customer.email = request.form['email']
    customer.phone_no = request.form['phone_no']
    customer.city = request.form['city']
    customer.area = request.form['area']
    customer.pincode = request.form['pincode']
    db.session.commit()
    flash("Profile updated successfully!", "success")
    return redirect(url_for('customer_profile'))

@app.route('/customer/change_date/<int:request_id>', methods=['POST'])
def change_date_direct(request_id):
    service_request = ServiceRequest.query.get_or_404(request_id)
    if service_request.customer_id != session.get('user_id') or service_request.service_status != 'Requested':
        flash("You can't change the date for this request.", "error")
        return redirect(url_for('customer_profile'))

    new_date_str = request.form.get('new_date')
    try:
        new_date = datetime.strptime(new_date_str, '%Y-%m-%d')
        service_request.date_of_request = new_date
        db.session.commit()
        flash("Service date updated successfully.", "success")
    except ValueError:
        flash("Invalid date format.", "error")

    return redirect(url_for('customer_profile'))

@app.route('/customer/request_date_change/<int:request_id>', methods=['POST'])
def request_date_change(request_id):
    service_request = ServiceRequest.query.get_or_404(request_id)
    if service_request.customer_id != session.get('user_id') or service_request.service_status != 'Accepted':
        flash("You can't request a date change for this request.", "error")
        return redirect(url_for('customer_profile'))

    new_date_str = request.form.get('new_date')
    try:
        new_date = datetime.strptime(new_date_str, '%Y-%m-%d')
        service_request.pending_date_change = new_date
        db.session.commit()
        flash("Date change request sent to the service professional.", "info")
    except ValueError:
        flash("Invalid date format.", "error")

    return redirect(url_for('customer_profile'))


@app.route('/cancel_request/<int:request_id>', methods=['POST'])
def cancel_request(request_id):
    service_request = ServiceRequest.query.get(request_id)
    if service_request:
        service_request.service_status = 'Cancelled'
        db.session.commit()
        flash("Service request cancelled successfully.", "success")
    else:
        flash("Service request not found.", "error")
    return redirect(url_for('customer_profile'))

@app.route('/rate_service/<int:request_id>', methods=['POST'])
def rate_service(request_id):
    service_request = ServiceRequest.query.get(request_id)
    
    if service_request and service_request.service_status == 'Completed':
        if service_request.ratings:
            flash("You have already rated this service.", "warning")
            return redirect(url_for('customer_profile'))
        
        service_request.ratings = request.form['rating']
        db.session.commit()
        
        professional_id = service_request.professional_id
        compute_user_ratings(professional_id)

        flash("Service rated successfully!", "success")
    else:
        flash("Unable to rate service.", "error")
    
    return redirect(url_for('customer_profile'))

def compute_user_ratings(professional_id):
    completed_requests = ServiceRequest.query.filter(
        ServiceRequest.professional_id == professional_id,
        ServiceRequest.ratings != None
    ).all()
    
    total_ratings = 0
    num_ratings = len(completed_requests)
    
    for request in completed_requests:
        total_ratings += int(request.ratings)
    
    average_rating = total_ratings / num_ratings if num_ratings > 0 else 0

    professional = user.query.get(professional_id)
    if professional:
        professional.ratings = f"{average_rating:.1f}"  
        db.session.commit()


@app.route('/customer_dashboard')
def customer_dashboard():
    customer_id = session.get('user_id')
    
    if not customer_id or session.get('role') != 'customer':
        flash("Please log in to access the dashboard", "error")
        return redirect(url_for('login'))
    
    customer = user.query.get(customer_id)
    search_query = request.args.get('search', '').strip()

    if search_query:
        # Filter services by name + city
        services = service.query.filter(
            service.city == customer.city,
            service.name.ilike(f"%{search_query}%")
        ).all()
    else:
        # Default: show services from the user's city
        services = service.query.filter_by(city=customer.city).all()

    return render_template(
        "customer_dashboard.html",
        services=services,
        customer=customer,
        search_query=search_query
    )



# Routes

@app.route('/book_service/<int:service_id>', methods=['GET'])
def book_service(service_id):
    
    service_item = service.query.get(service_id)
    if not service_item:
        flash("Service not found!", "error")
        return redirect(url_for('customer_dashboard'))
    
    user_id = session.get('user_id')
    user_1 = user.query.get(user_id) if user_id else None

    return render_template('book_service.html', service=service_item, user=user_1)



@app.route('/submit_booking', methods=['POST'])
def submit_booking():
    service_id = request.form.get('service_id')
    date_of_request = request.form.get('date_of_request')
    remarks = request.form.get('remarks')
    customer_id = session.get('user_id')
    
    service_item = service.query.get(service_id)
    customer = user.query.get(customer_id)

    if service_item and customer:
        booking = ServiceRequest(
            customer_id=customer_id,
            service_name=service_item.name,                
            customer_name=customer.username,              
            customer_email=customer.email,
            customer_phone_no=customer.phone_no,
            area=customer.area,
            customer_city=customer.city,                   
            customer_pincode=customer.pincode,             
            remarks=remarks,
            date_of_request=datetime.strptime(date_of_request, '%Y-%m-%d'),  
            service_status='Requested'                     
        )

        db.session.add(booking)
        db.session.commit()
        
        flash("Service booking has been successfully submitted!", "success")
    else:
        flash("Service could not be booked. Please try again.", "error")

    return redirect(url_for('customer_dashboard'))
# Customer dashboard ended here

# Admin dashboard started here
@app.route('/admin/dashboard')
def admin_dashboard():
    return render_template('admin_dashboard.html', current_year=2024)


@app.route('/admin/manage_customers')
def manage_customers():
    search_query = request.args.get('search', '')

    # Base filter for all customers
    base_filter = [user.role == 'customer']

    # Apply search filters if any
    if search_query:
        search_filter = or_(
            user.username.ilike(f"%{search_query}%"),
            user.email.ilike(f"%{search_query}%"),
            user.city.ilike(f"%{search_query}%")
        )
        base_filter.append(search_filter)

    # Customers by status
    approved_customers = user.query.filter(
        *base_filter,
        or_(user.status == 'approved', user.status == None)
    ).order_by(desc(user.id)).all()

    rejected_customers = user.query.filter(
        *base_filter,
        user.status == 'blocked'
    ).order_by(desc(user.id)).all()

    return render_template(
        'manage_customers.html',
        approved_customers=approved_customers,
        rejected_customers=rejected_customers,
        search_query=search_query
    )


@app.route('/admin/approve_customer/<int:customer_id>')
def approve_customer(customer_id):
    customer = user.query.get_or_404(customer_id)
    if customer:
        customer.status = "approved"  
        db.session.commit()  
    return redirect(url_for('manage_customers'))

@app.route('/admin/block_customer/<int:customer_id>')
def block_customer(customer_id):
    customer = user.query.get_or_404(customer_id)
    if customer:
        customer.status = "blocked"  
        db.session.commit()  
    return redirect(url_for('manage_customers'))

@app.route('/admin/delete_customer/<int:customer_id>')
def delete_customer(customer_id):
    customer = user.query.get_or_404(customer_id)
    if customer:
        db.session.delete(customer)  
        db.session.commit()  
    return redirect(url_for('manage_customers'))



# Routes for managing service professionals
@app.route('/admin/manage_service_professionals', methods=['GET', 'POST'])
def manage_service_professionals():
    search_query = request.args.get('search', '')  # Get the search query from the URL parameters

    # Base query for filtering professionals
    base_query = user.query.filter_by(role='service professional')

    # Apply search filters if a query is provided
    if search_query:
        base_query = base_query.filter(
            (user.username.ilike(f"%{search_query}%")) |  # Search by username
            (user.email.ilike(f"%{search_query}%")) |     # Search by email
            (user.city.ilike(f"%{search_query}%")) |
            (user.service_type.ilike(f"%{search_query}%"))  # Search by service type
        )

    # Categorize professionals based on their status
    pending_professionals = base_query.filter_by(status=None).order_by(desc(user.id)).all()
    approved_professionals = base_query.filter_by(status='approved').order_by(desc(user.id)).all()
    blocked_professionals = base_query.filter_by(status='blocked').order_by(desc(user.id)).all()

    return render_template(
        'manage_service_professionals.html',
        pending_professionals=pending_professionals,
        approved_professionals=approved_professionals,
        blocked_professionals=blocked_professionals,
        search_query=search_query
    )



@app.route('/admin/approve_professional/<int:professional_id>')
def approve_professional(professional_id):
    professional = user.query.get_or_404(professional_id)
    professional.status = "approved" 
    db.session.commit()  
    return redirect(url_for('manage_service_professionals'))

@app.route('/admin/block_professional/<int:professional_id>')
def block_professional(professional_id):
    professional = user.query.get_or_404(professional_id)
    professional.status = "blocked" 
    db.session.commit()  
    return redirect(url_for('manage_service_professionals'))

@app.route('/admin/delete_professional/<int:professional_id>')
def delete_professional(professional_id):
    professional = user.query.get_or_404(professional_id)
    db.session.delete(professional)  
    db.session.commit()  
    return redirect(url_for('manage_service_professionals'))

@app.route('/admin/manage_reports')
def manage_reports():
    reports = Report.query.order_by(desc(Report.id)).all()
    return render_template(
        'manage_reports.html',
        reports=reports
    )

@app.route('/admin/services')
def manage_services():
    search_query = request.args.get('search', '')

    if search_query:
        # Apply search filters using ilike (case-insensitive)
        services = service.query.filter(
            or_(
                service.name.ilike(f"%{search_query}%"),
                service.city.ilike(f"%{search_query}%")
            )
        ).all()
    else:
        services = service.query.all()
    return render_template('manage_services.html', services=services,  search_query=search_query)

@app.route('/admin/create_service', methods=['GET', 'POST'])
def create_service():
    if request.method == 'POST':
        form_name = request.form['name']
        form_description = request.form['description']
        form_price = request.form['price']
        form_city = request.form['city']
        form_time_required = request.form['time_required']
        form_image_location = request.form['image_location']
        new_service = service(
            name=form_name, 
            description=form_description, 
            price=form_price, 
            city = form_city,
            time_required=form_time_required,
            image_location=form_image_location
        )
        db.session.add(new_service)
        db.session.commit()
        return redirect(url_for('manage_services'))
    return render_template('create_service.html')

@app.route('/admin/update_service/<int:service_id>', methods=['GET', 'POST'])
def update_service(service_id):
    service_to_update = service.query.get_or_404(service_id)
    
    if request.method == 'POST':
        service_to_update.name = request.form['name']
        service_to_update.description = request.form['description']
        service_to_update.price = request.form['price']
        service_to_update.time_required = request.form['time_required']
        db.session.commit()
        return redirect(url_for('manage_services'))
    return render_template('update_service.html', service=service_to_update)

@app.route('/admin/delete_service/<int:service_id>', methods=['GET', 'POST'])
def delete_service(service_id):
    service_to_delete = service.query.get_or_404(service_id)
    
    if request.method == 'POST':
        db.session.delete(service_to_delete)
        db.session.commit()
        return redirect(url_for('manage_services'))
    return render_template('delete_service.html', service=service_to_delete)

# API Routes for Chart Data
@app.route('/chart-data/customers-by-city')
def customers_by_city():
    data = db.session.query(user.city, func.count(user.id)).filter(user.role == 'customer').group_by(user.city).all()
    return jsonify({'labels': [row[0] for row in data], 'values': [row[1] for row in data]})

@app.route('/chart-data/professionals-by-city')
def professionals_by_city():
    data = db.session.query(user.city, func.count(user.id)).filter(user.role == 'service professional').group_by(user.city).all()
    return jsonify({'labels': [row[0] for row in data], 'values': [row[1] for row in data]})

@app.route('/chart-data/service-types')
def service_types():
    data = db.session.query(
        user.service_type, func.count(user.id)
    ).filter(
        user.service_type != None,  
        user.service_type != ''     
    ).group_by(user.service_type).all()

    return jsonify({
        'labels': [row[0] for row in data],
        'values': [row[1] for row in data]
    })

@app.route('/chart-data/service-requests')
def service_requests():
    data = db.session.query(ServiceRequest.service_name, func.count(ServiceRequest.id)).group_by(ServiceRequest.service_name).all()
    return jsonify({'labels': [row[0] for row in data], 'values': [row[1] for row in data]})

@app.route('/chart-data/service-status')
def service_status():
    data = db.session.query(ServiceRequest.service_status, func.count(ServiceRequest.id)).group_by(ServiceRequest.service_status).all()
    return jsonify({'labels': [row[0] for row in data], 'values': [row[1] for row in data]})

@app.route('/chart-data/ratings')
def ratings():
    data = db.session.query(ServiceRequest.ratings, func.count(ServiceRequest.id)).group_by(ServiceRequest.ratings).all()
    return jsonify({'labels': [row[0] for row in data], 'values': [row[1] for row in data]})

@app.route('/monthly_requests')
def monthly_requests():
    monthly_requests = db.session.query(
        func.strftime('%Y-%m', ServiceRequest.date_of_request).label('month'),
        func.count(ServiceRequest.id).label('total_requests')
    ).group_by('month').all()

    completed_accepted_requests = db.session.query(
        func.strftime('%Y-%m', ServiceRequest.date_of_request).label('month'),
        func.count(ServiceRequest.id).label('completed_accepted_requests')
    ).filter(ServiceRequest.service_status.in_(['Completed', 'Accepted'])).group_by('month').all()

    completed_accepted_cancelled_requests = db.session.query(
        func.strftime('%Y-%m', ServiceRequest.date_of_request).label('month'),
        func.count(ServiceRequest.id).label('completed_accepted_cancelled_requests')
    ).filter(ServiceRequest.service_status.in_(['Completed', 'Accepted', 'Cancelled'])).group_by('month').all()

    monthly_data = {
        'months': [row[0] for row in monthly_requests],
        'total_requests': [row[1] for row in monthly_requests],
        'completed_accepted_requests': [
            next((req[1] for req in completed_accepted_requests if req[0] == month), 0)
            for month in [row[0] for row in monthly_requests]
        ],
        'completed_accepted_cancelled_requests': [
            next((req[1] for req in completed_accepted_cancelled_requests if req[0] == month), 0)
            for month in [row[0] for row in monthly_requests]
        ]
    }
    return monthly_data



@app.route('/graph')
def graph():
    return render_template('graph.html')

#Admin dashboard ended here

@app.route('/about_us', methods=['GET', 'POST'])
def about_us():
    return render_template('about_us.html')

@app.route('/contact_us', methods=['GET', 'POST'])
def contact_us():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        message = request.form.get('message')

        if not name or not email or not message:
            flash('All fields are required!', 'danger')
            return redirect(url_for('contact_us'))

        report = Report(name=name, email=email, message=message)
        db.session.add(report)
        db.session.commit()

        flash('Your message has been sent successfully!', 'success')
        return redirect(url_for('contact_us'))

    return render_template('contact_us.html')

@app.route('/facebook', methods=['GET', 'POST'])
def facebook():
    return render_template('facebook.html')

@app.route('/twitter', methods=['GET', 'POST'])
def twitter():
    return render_template('twitter.html')

@app.route('/instragram', methods=['GET', 'POST'])
def instragram():
    return render_template('instragram.html')

def allowed_file(filename):
    """Check if the file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    selected_city = request.args.get('city')
    cities = service.query.with_entities(service.city).distinct()
    services = []

    if selected_city:
        services = service.query.filter_by(city=selected_city).with_entities(service.name).distinct()

    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        phone_no = request.form.get('phone_no')
        role = request.form.get('role')
        raw_password = request.form.get('password')
        hashed_password = generate_password_hash(raw_password)
        city = request.form.get('city')

        service_type = experience = description = area = pincode = cv = None

        if role == 'service professional':
            service_type = request.form.get('service_type')
            experience = request.form.get('experience')
            description = request.form.get('description')

            cv_file = request.files.get('file')
            if cv_file and allowed_file(cv_file.filename):
                filename = secure_filename(cv_file.filename)
                cv_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                cv_file.save(cv_path)
            else:
                flash("Invalid CV format. Please upload a PDF file only.", "error")
                return redirect(url_for('signup'))
        else:
            area = request.form.get('area')
            pincode = request.form.get('pincode')

        if user.query.filter_by(email=email).first():
            flash("Email is already registered.", "error")
            return redirect(url_for('signup'))

        new_user = user(
            username=username,
            email=email,
            phone_no=phone_no,
            password=hashed_password,
            role=role,
            service_type=service_type,
            experience=int(experience) if experience else None,
            description=description,
            city=city,
            area=area if role == 'customer' else None,
            pincode=int(pincode) if pincode else None,
            cv=filename if role == 'service professional' else None,
            date_of_join=datetime.utcnow()
        )

        db.session.add(new_user)
        db.session.commit()

        flash("Account created successfully!", "success")
        return redirect(url_for('login'))

    services = service.query.with_entities(service.name).distinct()
    cities = service.query.with_entities(service.city).distinct()
    return render_template('signup2.html', services=services, cities=cities)

@app.route('/get_services/<city>', methods=['GET'])
def get_services(city):
    services = service.query.filter_by(city=city).all()
    services_list = [{'id': s.id, 'name': s.name} for s in services]
    return jsonify(services_list)


@app.route('/Forgot password.html', methods=['GET', 'POST'])
def forgot_password():
    return render_template("Forgot password.html")

@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for('login'))


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run()