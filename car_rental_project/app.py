import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
from models.database import connect_db

app = Flask(__name__)
app.config.from_object('config.Config')
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}
db_conn = connect_db()

# Helper function to check allowed file types
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Home route for login
@app.route('/')
def home():
    return render_template('home.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Collect form data for registration (name, email, password, etc.)
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        # Check if passwords match
        if password != confirm_password:
            flash('Passwords do not match')
            return redirect(url_for('register'))

        cursor = db_conn.cursor(dictionary=True)
        # Check if the email already exists
        cursor.execute("SELECT * FROM customers WHERE email = %s", (email,))
        customer = cursor.fetchone()

        if customer:
            flash('Email is already registered')
        else:
            # Insert the new customer into the database
            cursor.execute("INSERT INTO customers (name, email, password) VALUES (%s, %s, %s)",
                           (name, email, password))
            db_conn.commit()
            flash('Registration successful. Please log in.')
            return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/customer_dashboard')
def customer_dashboard():
    # Ensure the user is logged in
    if not session.get('user_logged_in'):
        flash("Please log in to access your dashboard.")
        return redirect(url_for('login'))

    # Retrieve customer name and id from session
    customer_id = session.get('customer_id')
    customer_name = session.get('customer_name')

    # Connect to the database
    cursor = db_conn.cursor(dictionary=True)

    # Fetch available cars
    cursor.execute("SELECT * FROM cars WHERE available = 1")
    cars = cursor.fetchall()

    # Fetch booking history for the customer
    cursor.execute("""
        SELECT * FROM bookings 
        JOIN cars ON bookings.car_id = cars.car_id 
        WHERE customer_id = %s
    """, (customer_id,))
    bookings = cursor.fetchall()

    cursor.close()

    # Render the template with customer name, cars, and bookings data
    return render_template('customer_dashboard.html', customer_name=customer_name, cars=cars, bookings=bookings)


@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    if request.method == 'POST':
        # Fetch form data
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        # Verify current password and update if the new password is confirmed
        customer_id = session.get('customer_id')  # Assuming customer_id is stored in the session
        cursor = db_conn.cursor(dictionary=True)
        cursor.execute("SELECT password FROM customers WHERE customer_id = %s", (customer_id,))
        customer = cursor.fetchone()

        # Check if the current password matches
        if customer and customer['password'] == current_password:
            if new_password == confirm_password:
                # Update the password in the database
                cursor.execute("UPDATE customers SET password = %s WHERE customer_id = %s", (new_password, customer_id))
                db_conn.commit()
                flash("Password updated successfully.")
            else:
                flash("New password and confirmation do not match.")
        else:
            flash("Current password is incorrect.")

        cursor.close()

        # Redirect back to the dashboard or settings
        return redirect(url_for('customer_dashboard'))

    # Render the change password form
    return render_template('change_password.html')

@app.route('/payment', methods=['GET', 'POST'])
def payment():
    if request.method == 'POST':
        return redirect(url_for('process_payment'))
    return render_template('payment.html')

@app.route('/update_payment_details', methods=['GET', 'POST'])
def update_payment_details():
    customer_id = session.get('customer_id')  # Ensure the user is logged in

    if request.method == 'POST':
        payment_method = request.form.get('payment_method')

        # Initialize variables for payment details
        card_number, expiration_date, cvv, account_number, routing_number = None, None, None, None, None

        # Collect payment details based on the method chosen
        if payment_method in ['credit', 'debit']:
            card_number = request.form.get('card_number')
            expiration_date = request.form.get('expiration_date')
            cvv = request.form.get('cvv')
        elif payment_method == 'account':
            account_number = request.form.get('account_number')
            routing_number = request.form.get('routing_number')

        # Update the customer's payment details in the database
        cursor = db_conn.cursor(dictionary=True)
        cursor.execute("""
            UPDATE customers
            SET payment_method = %s, card_number = %s, expiration_date = %s, cvv = %s, 
                account_number = %s, routing_number = %s
            WHERE customer_id = %s
        """, (payment_method, card_number, expiration_date, cvv, account_number, routing_number, customer_id))

        db_conn.commit()
        cursor.close()

        flash("Payment details updated successfully.")
        return redirect(url_for('customer_dashboard'))

    return render_template('payment_form.html')


@app.route('/process_payment', methods=['POST'])
def process_payment():
    customer_id = session.get('customer_id')
    if not customer_id:
        flash("Please log in to make a payment.")
        return redirect(url_for('login'))

    payment_method = request.form.get('payment_method')
    cursor = db_conn.cursor(dictionary=True)

    # Process payment based on method and validate 16-digit card number
    if payment_method in ['credit', 'debit']:
        card_number = request.form.get('card_number')
        expiration_date = request.form.get('expiration_date')
        cvv = request.form.get('cvv')

        if len(card_number) != 16:
            flash("Card number must be 16 digits.")
            return redirect(url_for('payment'))

        # Update payment details
        cursor.execute("""
            UPDATE customers
            SET payment_method = %s, card_number = %s, expiration_date = %s, cvv = %s
            WHERE customer_id = %s
        """, (payment_method, card_number, expiration_date, cvv, customer_id))

    elif payment_method == 'account':
        account_number = request.form.get('account_number')
        routing_number = request.form.get('routing_number')

        cursor.execute("""
            UPDATE customers
            SET payment_method = %s, account_number = %s, routing_number = %s
            WHERE customer_id = %s
        """, (payment_method, account_number, routing_number, customer_id))

    db_conn.commit()
    cursor.close()

    flash("Payment Successful! Your booking has been confirmed.")
    return redirect(url_for('customer_dashboard'))


@app.route('/book_car/<int:car_id>', methods=['GET', 'POST'])
def book_car(car_id):
    # Ensure customer is logged in
    customer_id = session.get('customer_id')
    if not customer_id:
        flash("Please log in to book a car.")
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Retrieve form data and calculate total cost
        booking_date = request.form.get('booking_date')
        return_date = request.form.get('return_date')
        cursor = db_conn.cursor(dictionary=True)

        # Fetch car details and calculate cost
        cursor.execute("SELECT price_per_day FROM cars WHERE car_id = %s", (car_id,))
        car = cursor.fetchone()
        days = (datetime.strptime(return_date, '%Y-%m-%d') - datetime.strptime(booking_date, '%Y-%m-%d')).days
        total_cost = car['price_per_day'] * days

        # Insert booking into bookings table
        cursor.execute(
            "INSERT INTO bookings (customer_id, car_id, booking_date, return_date, total_cost) VALUES (%s, %s, %s, %s, %s)",
            (customer_id, car_id, booking_date, return_date, total_cost)
        )
        db_conn.commit()
        cursor.close()

        # Redirect to payment page
        return redirect(url_for('payment'))

    cursor = db_conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM cars WHERE car_id = %s", (car_id,))
    car = cursor.fetchone()
    cursor.close()
    return render_template('booking_form.html', car=car)

@app.route('/booking_history')
def booking_history():
    # Ensure the user is logged in
    if not session.get('user_logged_in'):
        flash("Please log in to view your booking history.")
        return redirect(url_for('login'))

    # Retrieve customer ID from session
    customer_id = session.get('customer_id')

    # Connect to the database
    cursor = db_conn.cursor(dictionary=True)

    # Fetch booking history for the customer including status
    cursor.execute("""
        SELECT b.booking_date, b.return_date, b.total_cost, b.status, 
               c.car_name, c.model_name, c.price_per_day
        FROM bookings b
        JOIN cars c ON b.car_id = c.car_id
        WHERE b.customer_id = %s
    """, (customer_id,))
    bookings = cursor.fetchall()
    cursor.close()

    # Render the booking history template
    return render_template('booking_history.html', bookings=bookings)

@app.route('/customer/bookings')
def view_bookings():
    customer_id = session.get('customer_id')
    cursor = db_conn.cursor(dictionary=True)
    cursor.execute("SELECT b.*, c.car_name, c.model_name FROM bookings b JOIN cars c ON b.car_id = c.car_id WHERE b.customer_id = %s", (customer_id,))
    bookings = cursor.fetchall()
    cursor.close()
    return render_template('bookings.html', bookings=bookings)


@app.route('/car_details/<int:car_id>')
def car_details(car_id):
    cursor = db_conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM cars WHERE car_id = %s", (car_id,))
    car = cursor.fetchone()
    cursor.close()
    return jsonify(car)

@app.route('/search_cars')
def search_cars():
    query = request.args.get('query', '')
    car_type = request.args.get('car_type', '')
    max_price = request.args.get('max_price', '')

    sql = "SELECT * FROM cars WHERE available = 1"
    filters = []
    if query:
        sql += " AND (car_name LIKE %s OR model_name LIKE %s)"
        filters.extend(['%' + query + '%', '%' + query + '%'])
    if car_type:
        sql += " AND size = %s"
        filters.append(car_type)
    if max_price:
        sql += " AND price_per_day <= %s"
        filters.append(max_price)

    cursor = db_conn.cursor(dictionary=True)
    cursor.execute(sql, filters)
    cars = cursor.fetchall()
    cursor.close()

    # Fetch customer information from session or database
    customer_id = session.get('customer_id')
    cursor = db_conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM customers WHERE customer_id = %s", (customer_id,))
    customer = cursor.fetchone()
    cursor.close()

    return render_template('customer_dashboard.html', customer=customer, cars=cars)


@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('user_logged_in') or session.get('user_role') != 'admin':
        flash("Access denied. Admins only.")
        return redirect(url_for('login'))

    admin_id = session.get('customer_id')

    # Fetch admin details from the customer table
    cursor = db_conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM customers WHERE customer_id = %s AND role = 'admin'", (admin_id,))
    admin = cursor.fetchone()

    if not admin:
        flash("Admin profile not found.")
        return redirect(url_for('login'))

    # Fetch count of available cars
    cursor.execute("SELECT COUNT(*) AS count FROM cars WHERE available = 1")
    available_cars_count = cursor.fetchone()['count']

    # Fetch count of customers
    cursor.execute("SELECT COUNT(*) AS count FROM customers WHERE role='user'")
    customer_count = cursor.fetchone()['count']

    # Fetch all cars with id field
    cursor.execute("SELECT * FROM cars")
    cars = cursor.fetchall()

    # Fetch unread notifications count
    cursor.execute("SELECT COUNT(*) AS unread_count FROM notifications WHERE admin_id = %s AND is_read = 0",
                   (admin_id,))
    unread_count = cursor.fetchone()['unread_count']

    cursor.close()

    # Render the template and pass the unread_count
    return render_template('admin_dashboard.html', admin=admin, available_cars_count=available_cars_count,
                           customer_count=customer_count, cars=cars, unread_count=unread_count)


@app.route('/admin/car_rental_analytics')
def car_rental_analytics():
    if not session.get('user_logged_in') or session.get('user_role') != 'admin':
        flash("Access denied. Admins only.")
        return redirect(url_for('login'))

    cursor = db_conn.cursor(dictionary=True)

    # Fetch monthly revenue and rentals data
    cursor.execute("""
        SELECT DATE_FORMAT(booking_date, '%Y-%m') AS month, COUNT(*) AS total_rentals, SUM(total_cost) AS total_revenue
        FROM bookings
        GROUP BY month
        ORDER BY month DESC
    """)
    monthly_data = cursor.fetchall()

    # Prepare data for the charts
    months = [data['month'] for data in monthly_data]
    total_rentals = [data['total_rentals'] for data in monthly_data]
    total_revenue = [data['total_revenue'] for data in monthly_data]

    # Fetch most popular cars (based on rental counts)
    cursor.execute("""
        SELECT c.car_name, COUNT(b.car_id) AS rental_count
        FROM bookings b
        JOIN cars c ON b.car_id = c.car_id
        GROUP BY c.car_name
        ORDER BY rental_count DESC
        LIMIT 5
    """)
    popular_cars = cursor.fetchall()

    car_names = [car['car_name'] for car in popular_cars]
    rental_counts = [car['rental_count'] for car in popular_cars]

    cursor.close()

    # Pass the data to the template
    return render_template('car_rental_analytics.html',
                           revenue_labels=months,
                           revenue_data=total_revenue,
                           rental_labels=months,
                           rental_data=total_rentals,
                           popular_cars_labels=car_names,
                           popular_cars_data=rental_counts)


@app.route('/admin/delete_car/<int:car_id>', methods=['POST'])
def delete_car(car_id):
    cursor = db_conn.cursor(dictionary=True)
    # Execute delete query
    cursor.execute("DELETE FROM cars WHERE car_id = %s", (car_id,))
    db_conn.commit()
    cursor.close()
    flash("Car deleted successfully!")
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/edit_car/<int:car_id>', methods=['GET', 'POST'])
def edit_car(car_id):
    cursor = db_conn.cursor(dictionary=True)

    if request.method == 'POST':
        # Process form submission for editing car details
        car_name = request.form['car_name']
        model_name = request.form['model_name']
        rating = request.form['rating']
        available_date = request.form['available_date']
        price_per_day = request.form['price_per_day']
        description = request.form['description']

        # Update car details in the database
        cursor.execute("""
            UPDATE cars SET car_name = %s, model_name = %s, rating = %s,
            available_date = %s, price_per_day = %s, description = %s
            WHERE car_id = %s
        """, (car_name, model_name, rating, available_date, price_per_day, description, car_id))
        db_conn.commit()
        cursor.close()
        flash("Car details updated successfully!")
        return redirect(url_for('admin_dashboard'))

    # Retrieve car details for the form if request method is GET
    cursor.execute("SELECT * FROM cars WHERE car_id = %s", (car_id,))
    car = cursor.fetchone()
    cursor.close()

    return render_template('edit_car.html', car=car)

@app.route('/admin/add_car', methods=['GET', 'POST'])
def add_car():
    if session.get('user_role') != 'admin':
        flash("Access denied. Admins only.")
        return redirect(url_for('login'))

    if request.method == 'POST':
        car_name = request.form['car_name']
        model_name = request.form['model_name']
        rating = request.form['rating']
        available_date = request.form['available_date']
        price_per_day = request.form['price_per_day']
        description = request.form['description']
        capacity = request.form['capacity']  # New capacity field
        luggage_space = request.form['luggage_space']  # New luggage_space field
        doors = request.form['doors']  # New doors field

        # Handle file upload
        if 'car_image' in request.files:
            file = request.files['car_image']
            if file and allowed_file(file.filename):
                # Create the uploads folder if it doesn't exist
                if not os.path.exists(app.config['UPLOAD_FOLDER']):
                    os.makedirs(app.config['UPLOAD_FOLDER'])

                # Save the file
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)

                # Insert car details, including image URL, into the database
                image_url = f"/{file_path}"  # URL to save in the database
                cursor = db_conn.cursor()
                cursor.execute("""
                    INSERT INTO cars (car_name, model_name, rating, available_date, price_per_day, 
                                      description, image_url, available, capacity, luggage_space, doors)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 1, %s, %s, %s)
                """, (car_name, model_name, rating, available_date, price_per_day, description, image_url, capacity, luggage_space, doors))
                db_conn.commit()
                cursor.close()

                flash("Car added successfully!")
                return redirect(url_for('admin_dashboard'))
            else:
                flash("Invalid file format. Please upload an image.")
    return render_template('add_car.html')



@app.route('/admin/profile', methods=['GET', 'POST'])
def update_admin_profile():
    if session.get('user_role') != 'admin':
        return redirect(url_for('login'))

    cursor = db_conn.cursor(dictionary=True)
    admin_id = session.get('user_id')

    if request.method == 'POST':
        # Update admin profile in the database
        phone = request.form['phone']
        address = request.form['address']
        cursor.execute("UPDATE customers SET phone = %s, address = %s WHERE customer_id = %s",
                       (phone, address, admin_id))
        db_conn.commit()
        flash("Profile updated successfully!")

        # Redirect back to the admin dashboard
        return redirect(url_for('admin_dashboard'))

    # Fetch the latest admin data
    cursor.execute("SELECT * FROM customers WHERE customer_id = %s", (admin_id,))
    admin = cursor.fetchone()
    cursor.close()

    return render_template('admin_profile.html', admin=admin)

@app.route('/admin/manage_users')
def manage_users():
    if session.get('user_role') != 'admin':
        flash("Access denied. Admins only.")
        return redirect(url_for('login'))

    # Fetch all users (excluding admins if necessary)
    cursor = db_conn.cursor(dictionary=True)
    cursor.execute("SELECT customer_id, name, email, phone, address, payment_method FROM customers WHERE role = 'user'")
    users = cursor.fetchall()
    cursor.close()

    return render_template('manage_users.html', users=users)

@app.route('/admin/edit_user/<int:user_id>', methods=['GET', 'POST'])
def edit_user(user_id):
    if session.get('user_role') != 'admin':
        flash("Access denied. Admins only.")
        return redirect(url_for('login'))

    cursor = db_conn.cursor(dictionary=True)
    if request.method == 'POST':
        # Get the updated user info
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        address = request.form['address']

        # Update the user details in the database
        cursor.execute("""
            UPDATE customers 
            SET name = %s, email = %s, phone = %s, address = %s 
            WHERE customer_id = %s
        """, (name, email, phone, address, user_id))
        db_conn.commit()
        cursor.close()
        flash("User details updated successfully.")
        return redirect(url_for('manage_users'))

    # Fetch current user details for editing
    cursor.execute("SELECT * FROM customers WHERE customer_id = %s", (user_id,))
    user = cursor.fetchone()
    cursor.close()

    return render_template('edit_user.html', user=user)


@app.route('/admin/view_user/<int:user_id>')
def view_user(user_id):
    if session.get('user_role') != 'admin':
        flash("Access denied. Admins only.")
        return redirect(url_for('login'))

    # Fetch user details and booking history
    cursor = db_conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM customers WHERE customer_id = %s", (user_id,))
    user = cursor.fetchone()

    cursor.execute("""
        SELECT b.*, c.car_name, c.model_name 
        FROM bookings b 
        JOIN cars c ON b.car_id = c.car_id 
        WHERE b.customer_id = %s
    """, (user_id,))
    bookings = cursor.fetchall()
    cursor.close()

    return render_template('view_user.html', user=user, bookings=bookings)

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if session.get('user_role') != 'admin':
        flash("Access denied. Admins only.")
        return redirect(url_for('login'))

    cursor = db_conn.cursor()
    cursor.execute("DELETE FROM customers WHERE customer_id = %s", (user_id,))
    db_conn.commit()
    cursor.close()
    flash("User deleted successfully.")
    return redirect(url_for('manage_users'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        cursor = db_conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM customers WHERE email = %s", (email,))
        user = cursor.fetchone()

        if user and user['password'] == password:  # Replace with hashed password check in production
            session['user_logged_in'] = True
            session['customer_id'] = user['customer_id']
            session['user_role'] = user['role']  # Set role (admin or user)
            session['customer_name'] = user['name']

            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))  # Redirect admin to admin dashboard
            else:
                return redirect(url_for('customer_dashboard'))  # Redirect user to customer dashboard
        else:
            flash("Invalid email or password")

    return render_template('customer_login.html')

@app.route('/admin/manage_cars', methods=['GET'])
def manage_cars():
    # Get filter values from the form
    car_name = request.args.get('car_name', '')
    model_name = request.args.get('model_name', '')
    availability = request.args.get('availability', '1')  # Default to '1' (available)
    min_price = request.args.get('min_price', '')
    max_price = request.args.get('max_price', '')

    # Prepare the SQL query with placeholders
    sql_query = """
    SELECT * FROM cars
    WHERE (car_name LIKE %s)
    AND (model_name LIKE %s)
    AND (available = %s)
    AND (price_per_day >= %s OR %s = '')
    AND (price_per_day <= %s OR %s = '')
    """

    # Define filter values
    filters = [f'%{car_name}%', f'%{model_name}%', availability, min_price, min_price, max_price, max_price]

    # Execute the query
    cursor = db_conn.cursor(dictionary=True)
    cursor.execute(sql_query, tuple(filters))
    cars = cursor.fetchall()
    cursor.close()

    # Render the template with filtered cars
    return render_template('manage_cars.html', cars=cars)

@app.route('/admin/notifications')
def admin_notifications():
    if not session.get('user_logged_in') or session.get('user_role') != 'admin':
        flash("Access denied. Admins only.")
        return redirect(url_for('login'))

    admin_id = session.get('customer_id')

    # Fetch notifications for the admin
    cursor = db_conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM notifications WHERE admin_id = %s ORDER BY created_at DESC", (admin_id,))
    notifications = cursor.fetchall()
    cursor.close()

    return render_template('admin_notification.html', notifications=notifications)

@app.route('/admin/view_notification/<int:notification_id>')
def view_notification(notification_id):
    cursor = db_conn.cursor()

    # Mark the notification as read
    cursor.execute("UPDATE notifications SET is_read = 1 WHERE notification_id = %s", (notification_id,))
    db_conn.commit()

    cursor.close()

    # Redirect back to the notifications page or dashboard
    return redirect(url_for('admin_notifications'))


@app.route('/admin/view_reports')
def view_reports():
    cursor = db_conn.cursor(dictionary=True)

    # Monthly Bookings and Revenue
    cursor.execute("""
        SELECT DATE_FORMAT(booking_date, '%Y-%m') AS month, COUNT(*) AS total_bookings, SUM(total_cost) AS total_revenue
        FROM bookings
        GROUP BY month
        ORDER BY month DESC
    """)
    monthly_bookings = cursor.fetchall()

    # New Customers per Month
    cursor.execute("""
        SELECT DATE_FORMAT(created_at, '%Y-%m') AS month, COUNT(*) AS new_customers
        FROM customers
        WHERE role = 'user'
        GROUP BY month
        ORDER BY month DESC
    """)
    monthly_customers = cursor.fetchall()

    # Payment Summary
    cursor.execute("""
        SELECT payment_method AS method, COUNT(*) AS count, SUM(total_cost) AS total
        FROM bookings
        JOIN customers ON bookings.customer_id = customers.customer_id
        GROUP BY method
    """)
    payment_summary = cursor.fetchall()

    # Car Availability
    cursor.execute("""
        SELECT car_name AS model, available, COUNT(bookings.car_id) AS total_bookings
        FROM cars
        LEFT JOIN bookings ON cars.car_id = bookings.car_id
        GROUP BY model, available
    """)
    car_availability = cursor.fetchall()

    cursor.close()

    return render_template('view_reports.html', monthly_bookings=monthly_bookings,
                           monthly_customers=monthly_customers, payment_summary=payment_summary,
                           car_availability=car_availability)


@app.route('/add_to_cart/<int:car_id>', methods=['POST'])
def add_to_cart(car_id):
    customer_id = session.get('customer_id')

    if not customer_id:
        return jsonify({"success": False, "error": "User not logged in"}), 403

    cursor = db_conn.cursor()
    cursor.execute("INSERT INTO cart_items (customer_id, car_id) VALUES (%s, %s)", (customer_id, car_id))
    db_conn.commit()
    cursor.close()

    return jsonify({"success": True})


@app.route('/remove_from_cart/<int:car_id>', methods=['POST'])
def remove_from_cart(car_id):
    customer_id = session.get('customer_id')

    if not customer_id:
        return jsonify({"success": False, "error": "User not logged in"}), 403

    cursor = db_conn.cursor()
    cursor.execute("DELETE FROM cart_items WHERE customer_id = %s AND car_id = %s", (customer_id, car_id))
    db_conn.commit()
    cursor.close()

    return jsonify({"success": True})


@app.route('/update_user_info', methods=['GET', 'POST'])
def update_user_info():
    customer_id = session.get('customer_id')
    cursor = db_conn.cursor(dictionary=True)

    if request.method == 'POST':
        # Update user info in the database
        name = request.form['name']
        phone = request.form['phone']
        cursor.execute("UPDATE customers SET name = %s, phone = %s WHERE customer_id = %s", (name, phone, customer_id))
        db_conn.commit()
        flash("Profile updated successfully!")
        return redirect(url_for('customer_dashboard'))

    # Fetch current user info to pre-fill the form
    cursor.execute("SELECT * FROM customers WHERE customer_id = %s", (customer_id,))
    customer = cursor.fetchone()
    cursor.close()

    return render_template('update_user_info.html', customer=customer)


@app.route('/view_cart')
def view_cart():
    customer_id = session.get('customer_id')

    if not customer_id:
        flash("Please log in to view your cart.")
        return redirect(url_for('login'))

    cursor = db_conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT c.car_name, c.model_name, c.price_per_day 
        FROM cart_items ci
        JOIN cars c ON ci.car_id = c.car_id
        WHERE ci.customer_id = %s
    """, (customer_id,))
    cart_items = cursor.fetchall()
    cursor.close()

    return render_template('view_cart.html', cart_items=cart_items)


@app.route('/cars')
def cars():
    cursor = db_conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM cars WHERE available = 1")
    cars = cursor.fetchall()
    cursor.close()

    return render_template('cars.html', cars=cars)

@app.route('/booking/<int:car_id>', methods=['GET', 'POST'])
def booking(car_id):
    if not session.get('customer_logged_in'):
        return redirect(url_for('login'))

    cursor = db_conn.cursor(dictionary=True)
    customer_id = session['customer_id']

    if request.method == 'POST':
        booking_date = request.form['booking_date']
        return_date = request.form['return_date']
        cursor.execute(
            "INSERT INTO bookings (customer_id, car_id, booking_date, return_date) VALUES (%s, %s, %s, %s)",
            (customer_id, car_id, booking_date, return_date)
        )
        cursor.execute("UPDATE cars SET available = 0 WHERE car_id = %s", (car_id,))
        db_conn.commit()
        cursor.close()
        flash('Booking confirmed!')
        return redirect(url_for('cars'))

    cursor.execute("SELECT * FROM cars WHERE car_id = %s", (car_id,))
    car = cursor.fetchone()
    cursor.close()

    return render_template('booking_form.html', car=car)

# Logout
@app.route('/logout')
def logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('home'))

@app.route('/privacy-policy')
def privacy_policy():
    return render_template('privacy_policy.html')

@app.route('/contact-us')
def contact_us():
    return render_template('contact_us.html')

@app.route('/terms-of-service')
def terms_of_service():
    return render_template('terms_of_service.html')

if __name__ == '__main__':
    app.run(debug=True)
