import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import datetime, timedelta
from config import config
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf.csrf import CSRFProtect


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)

def create_app(config_name='default'):
    """Application factory function."""
    app = Flask(__name__)
    
    # Load configuration
    config_name = config_name or os.environ.get('FLASK_ENV', 'default')
    config_class = config[config_name]
    
    if config_name == 'production':
        # Instantiate production config to enforce environment variables
        app.config.from_object(config_class())
    else:
        # Use class for development
        app.config.from_object(config_class)
    
    # Setup ProxyFix for HTTPS handling (needed for PythonAnywhere)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
    
    # Initialize CSRF protection
    csrf = CSRFProtect(app)
    
    # Initialize the database with the app
    db.init_app(app)
    
    return app

# Create the app instance
# In production, this will use environment variable FLASK_ENV
app = create_app(os.environ.get('FLASK_ENV', 'development'))

# Database models
class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    featured_image = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f'<Post {self.id}: {self.title}>'

class SiteSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    blog_title = db.Column(db.String(100), nullable=False, default='Blog CMS')
    blog_description = db.Column(db.Text, nullable=False, default='Welcome to Our Blog')

    # Color customization fields
    primary_color = db.Column(db.String(7), nullable=False, default='#667eea')
    secondary_color = db.Column(db.String(7), nullable=False, default='#764ba2')
    background_color = db.Column(db.String(7), nullable=False, default='#667eea')
    overall_background = db.Column(db.String(7), nullable=False, default='#1a1a2e')
    card_background = db.Column(db.String(7), nullable=False, default='#ffffff')
    text_color = db.Column(db.String(7), nullable=False, default='#333333')
    navbar_color = db.Column(db.String(7), nullable=False, default='#000000')

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Ensure instance directory exists for SQLite database
os.makedirs('instance', exist_ok=True)

with app.app_context():
    db.create_all()
    # Create default site settings if none exist
    if not SiteSettings.query.first():
        default_settings = SiteSettings()
        default_settings.blog_title = 'Blog CMS'
        default_settings.blog_description = 'Welcome to Our Blog'
        default_settings.primary_color = '#667eea'
        default_settings.secondary_color = '#764ba2'
        default_settings.background_color = '#667eea'
        default_settings.overall_background = '#1a1a2e'
        default_settings.card_background = '#ffffff'
        default_settings.text_color = '#333333'
        default_settings.navbar_color = '#000000'
        db.session.add(default_settings)
        db.session.commit()

# Authentication decorator
def login_required(f):
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# Helper function to get site settings
def get_site_settings():
    settings = SiteSettings.query.first()
    if not settings:
        settings = SiteSettings()
        settings.blog_title = 'Blog CMS'
        settings.blog_description = 'Welcome to Our Blog'
        settings.primary_color = '#667eea'
        settings.secondary_color = '#764ba2'
        settings.background_color = '#667eea'
        settings.overall_background = '#1a1a2e'
        settings.card_background = '#ffffff'
        settings.text_color = '#333333'
        settings.navbar_color = '#000000'
        db.session.add(settings)
        db.session.commit()
    return settings

# Template context processor to make site settings available to all templates
@app.context_processor
def inject_site_settings():
    return {'site_settings': get_site_settings()}

# Public routes
@app.route('/')
def index():
    posts = Post.query.order_by(Post.created_at.desc()).all()
    return render_template('index.html', posts=posts)

@app.route('/post/<int:id>')
def post_detail(id):
    post = Post.query.get_or_404(id)
    return render_template('post_detail.html', post=post)

# Admin authentication
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Get stored admin credentials
        admin_username = app.config['ADMIN_USERNAME']
        admin_password_hash = app.config.get('ADMIN_PASSWORD_HASH')
        
        # If no hash is stored, check against plain password (development only)
        if admin_password_hash:
            password_valid = check_password_hash(admin_password_hash, password)
        else:
            # Fallback to plain password for development
            password_valid = password == app.config['ADMIN_PASSWORD']
        
        if username == admin_username and password_valid:
            session['logged_in'] = True
            session.permanent = True
            flash('Logged in successfully!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid credentials!', 'error')
    
    return render_template('login.html')

@app.route('/admin/logout')
@login_required
def admin_logout():
    session.pop('logged_in', None)
    flash('Logged out successfully!', 'success')
    return redirect(url_for('index'))

# Admin dashboard
@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    posts = Post.query.order_by(Post.created_at.desc()).all()
    return render_template('dashboard.html', posts=posts)

@app.route('/admin/new', methods=['GET', 'POST'])
@login_required
def new_post():
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        featured_image = request.form.get('featured_image', '').strip() or None
        
        post = Post()
        post.title = title
        post.content = content
        post.featured_image = featured_image
        db.session.add(post)
        db.session.commit()
        
        flash('Post created successfully!', 'success')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('new_post.html')

@app.route('/admin/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_post(id):
    post = Post.query.get_or_404(id)
    
    if request.method == 'POST':
        post.title = request.form['title']
        post.content = request.form['content']
        post.featured_image = request.form.get('featured_image', '').strip() or None
        db.session.commit()
        
        flash('Post updated successfully!', 'success')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('edit_post.html', post=post)

@app.route('/admin/delete/<int:id>', methods=['POST'])
@login_required
def delete_post(id):
    post = Post.query.get_or_404(id)
    db.session.delete(post)
    db.session.commit()
    
    flash('Post deleted successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/settings', methods=['GET', 'POST'])
@login_required
def admin_settings():
    settings = get_site_settings()
    
    if request.method == 'POST':
        settings.blog_title = request.form['blog_title']
        settings.blog_description = request.form['blog_description']
        settings.primary_color = request.form['primary_color']
        settings.secondary_color = request.form['secondary_color']
        settings.background_color = request.form['background_color']
        settings.overall_background = request.form['overall_background']
        settings.card_background = request.form['card_background']
        settings.text_color = request.form['text_color']
        settings.navbar_color = request.form['navbar_color']
        db.session.commit()
        
        flash('Settings updated successfully!', 'success')
        return redirect(url_for('admin_settings'))
    
    return render_template('admin_settings.html', settings=settings)

@app.route('/admin/export')
@login_required
def export_tutorials():
    """Export all tutorials as JSON"""
    import json
    from flask import Response
    from datetime import datetime
    
    posts = Post.query.all()
    tutorials_data = {
        'export_date': datetime.now().isoformat(),
        'total_posts': len(posts),
        'posts': []
    }
    
    for post in posts:
        post_data = {
            'title': post.title,
            'content': post.content,
            'featured_image': post.featured_image,
            'created_at': post.created_at.isoformat() if post.created_at else None
        }
        tutorials_data['posts'].append(post_data)
    
    json_data = json.dumps(tutorials_data, indent=2, ensure_ascii=False)
    
    response = Response(
        json_data,
        mimetype='application/json',
        headers={'Content-Disposition': f'attachment; filename=tutorials_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'}
    )
    
    flash(f'Successfully exported {len(posts)} tutorials!', 'success')
    return response

@app.route('/admin/import', methods=['GET', 'POST'])
@login_required
def import_tutorials():
    """Import tutorials from JSON file"""
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file selected!', 'error')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('No file selected!', 'error')
            return redirect(request.url)
        
        if not file.filename or not file.filename.lower().endswith('.json'):
            flash('Please upload a JSON file!', 'error')
            return redirect(request.url)
        
        import json
        from datetime import datetime
        
        try:
            # Read and parse JSON file
            file_content = file.read().decode('utf-8')
            data = json.loads(file_content)
            
            if 'posts' not in data:
                flash('Invalid file format! Missing posts data.', 'error')
                return redirect(request.url)
            
            imported_count = 0
            skipped_count = 0
            
            for post_data in data['posts']:
                # Check if required fields exist
                if not post_data.get('title') or not post_data.get('content'):
                    skipped_count += 1
                    continue
                
                # Check if post with same title already exists
                existing_post = Post.query.filter_by(title=post_data['title']).first()
                if existing_post:
                    skipped_count += 1
                    continue
                
                # Create new post
                new_post = Post()
                new_post.title = post_data['title']
                new_post.content = post_data['content']
                new_post.featured_image = post_data.get('featured_image')
                
                # Parse created_at if provided, otherwise use current time
                if post_data.get('created_at'):
                    try:
                        new_post.created_at = datetime.fromisoformat(post_data['created_at'].replace('Z', '+00:00'))
                    except:
                        new_post.created_at = datetime.utcnow()
                else:
                    new_post.created_at = datetime.utcnow()
                
                db.session.add(new_post)
                imported_count += 1
            
            db.session.commit()
            
            if imported_count > 0:
                flash(f'Successfully imported {imported_count} tutorials! Skipped {skipped_count} duplicates or invalid entries.', 'success')
            else:
                flash(f'No new tutorials imported. Skipped {skipped_count} duplicates or invalid entries.', 'warning')
            
            return redirect(url_for('admin_dashboard'))
            
        except json.JSONDecodeError:
            flash('Invalid JSON file format!', 'error')
            return redirect(request.url)
        except Exception as e:
            flash(f'Error importing tutorials: {str(e)}', 'error')
            return redirect(request.url)
    
    return render_template('import_tutorials.html')

@app.route('/certificate')
def certificate_form():
    """Display certificate generation form"""
    posts = Post.query.order_by(Post.created_at.desc()).all()
    return render_template('certificate_form.html', posts=posts)

@app.route('/generate_certificate', methods=['POST'])
def generate_certificate():
    """Process certificate form and redirect to certificate download"""
    student_name = request.form['student_name'].strip()
    post_id = request.form['post_id']
    
    if not student_name:
        flash('Please enter your full name.', 'error')
        return redirect(url_for('certificate_form'))
    
    if not post_id:
        flash('Please select a tutorial.', 'error')
        return redirect(url_for('certificate_form'))
    
    # Validate that post_id is valid and post exists
    try:
        post_id = int(post_id)
        post = Post.query.get(post_id)
        if not post:
            flash('Selected tutorial not found.', 'error')
            return redirect(url_for('certificate_form'))
    except ValueError:
        flash('Invalid tutorial selection.', 'error')
        return redirect(url_for('certificate_form'))
    
    # Redirect to the existing certificate download route (Flask handles URL encoding)
    return redirect(url_for('download_certificate', post_id=post_id, student_name=student_name))

@app.route('/manifest.json')
def serve_manifest():
    """Serve PWA manifest with proper MIME type"""
    from flask import send_from_directory
    return send_from_directory('static', 'manifest.json', mimetype='application/manifest+json')

@app.route('/certificate/<int:post_id>/<path:student_name>')
def download_certificate(post_id, student_name):
    """Generate and download certificate server-side"""
    from flask import Response
    import urllib.parse
    from datetime import datetime
    
    post = Post.query.get_or_404(post_id)
    settings = get_site_settings()
    
    # Flask automatically decodes the URL path parameter
    # student_name is already decoded by Flask
    completion_date = datetime.now().strftime('%B %d, %Y')
    
    certificate_html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Certificate - {student_name}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {{
            font-family: 'Times New Roman', serif;
            background: linear-gradient(135deg, {settings.background_color} 0%, {settings.secondary_color} 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        
        .certificate {{
            max-width: 800px;
            margin: 50px auto;
            background: white;
            padding: 60px;
            border: 8px solid {settings.primary_color};
            position: relative;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
        }}
        
        .certificate::before {{
            content: '';
            position: absolute;
            top: 20px;
            left: 20px;
            right: 20px;
            bottom: 20px;
            border: 3px solid {settings.secondary_color};
            pointer-events: none;
        }}
        
        .certificate-header {{
            text-align: center;
            margin-bottom: 40px;
        }}
        
        .certificate-title {{
            font-size: 3rem;
            font-weight: bold;
            color: {settings.primary_color};
            margin-bottom: 10px;
            letter-spacing: 3px;
        }}
        
        .certificate-subtitle {{
            font-size: 1.2rem;
            color: {settings.secondary_color};
            margin-bottom: 30px;
        }}
        
        .student-name {{
            font-size: 2.5rem;
            font-weight: bold;
            color: {settings.secondary_color};
            text-decoration: underline;
            text-decoration-color: {settings.primary_color};
            margin: 20px 0;
        }}
        
        .tutorial-title {{
            font-size: 1.8rem;
            font-style: italic;
            color: {settings.primary_color};
            margin: 20px 0;
        }}
        
        .completion-text {{
            font-size: 1.1rem;
            line-height: 1.8;
            text-align: center;
            margin: 30px 0;
        }}
        
        .date-signature {{
            display: flex;
            justify-content: space-between;
            margin-top: 60px;
        }}
        
        .signature-line {{
            text-align: center;
            min-width: 200px;
        }}
        
        .signature-line hr {{
            border: 2px solid {settings.primary_color};
            margin: 10px 0;
        }}
        
        .signature-line small {{
            color: {settings.secondary_color};
            font-size: 0.9rem;
        }}
    </style>
</head>
<body>
    <div class="certificate">
        <div class="certificate-header">
            <h1 class="certificate-title">CERTIFICATE</h1>
            <h2 class="certificate-subtitle">of Achievement</h2>
        </div>
        
        <div class="certificate-content text-center">
            <p class="completion-text">This is to certify that</p>
            
            <h2 class="student-name">{student_name}</h2>
            
            <p class="completion-text">has successfully completed the tutorial</p>
            
            <h3 class="tutorial-title">"{post.title}"</h3>
            
            <p class="completion-text">
                and has demonstrated proficiency in the subject matter<br>
                on this day of <strong>{completion_date}</strong>
            </p>
        </div>
        
        <div class="date-signature">
            <div class="signature-line">
                <hr>
                <small>Date</small>
            </div>
            <div class="signature-line">
                <hr>
                <small>Tutorial Platform</small>
            </div>
        </div>
    </div>
</body>
</html>
    """
    
    response = Response(certificate_html, mimetype='text/html')
    response.headers['Content-Disposition'] = f'attachment; filename="certificate-{student_name.replace(" ", "-").lower()}.html"'
    return response

@app.route('/dynamic-styles.css')
def dynamic_styles():
    settings = get_site_settings()
    
    css_content = f"""
/* Dynamic styles based on admin settings */
body.mobile-app-body {{
    background: {settings.overall_background} !important;
    background-attachment: fixed;
    transition: background-color 0.8s ease-in-out;
}}

.gradient-bg {{
    background: linear-gradient(135deg, {settings.background_color} 0%, {settings.secondary_color} 100%);
    animation: gradientShift 8s ease-in-out infinite;
}}

@keyframes gradientShift {{
    0%, 100% {{ background: linear-gradient(135deg, {settings.background_color} 0%, {settings.secondary_color} 100%); }}
    50% {{ background: linear-gradient(135deg, {settings.secondary_color} 0%, {settings.primary_color} 100%); }}
}}

.btn-gradient {{
    background: linear-gradient(45deg, {settings.primary_color}, {settings.secondary_color});
    transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative;
    overflow: hidden;
}}

.btn-gradient::before {{
    content: '';
    position: absolute;
    top: 0;
    left: -100%;
    width: 100%;
    height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
    transition: left 0.6s ease;
}}

.btn-gradient:hover::before {{
    left: 100%;
}}

.btn-gradient:hover {{
    background: linear-gradient(45deg, {settings.secondary_color}, {settings.primary_color});
    transform: translateY(-2px) scale(1.02);
    box-shadow: 0 10px 25px rgba({hex_to_rgb(settings.primary_color)}, 0.3);
}}

.blog-card {{
    background: rgba({hex_to_rgb(settings.card_background)}, 0.95);
    backdrop-filter: blur(10px);
    transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}}

.blog-card:hover {{
    transform: translateY(-8px) rotateX(2deg);
    box-shadow: 0 20px 40px rgba({hex_to_rgb(settings.primary_color)}, 0.2);
}}

.navbar-dark {{
    background: rgba({hex_to_rgb(settings.navbar_color)}, 0.9) !important;
    backdrop-filter: blur(20px);
    transition: all 0.3s ease;
}}

.mobile-header {{
    background: rgba({hex_to_rgb(settings.card_background)}, 0.95) !important;
    backdrop-filter: blur(20px);
    transition: all 0.3s ease;
}}

.bottom-nav {{
    background: rgba({hex_to_rgb(settings.card_background)}, 0.95) !important;
    backdrop-filter: blur(20px);
    transition: all 0.3s ease;
}}

.nav-item {{
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}}

.nav-item:hover {{
    transform: translateY(-3px) scale(1.05);
}}

.nav-item.active {{
    background: linear-gradient(45deg, {settings.primary_color}, {settings.secondary_color});
    color: white !important;
    border-radius: 15px;
    box-shadow: 0 8px 20px rgba({hex_to_rgb(settings.primary_color)}, 0.3);
}}

.certificate {{
    border: 3px solid {settings.primary_color};
    transition: all 0.3s ease;
}}

.certificate:hover {{
    transform: scale(1.02);
    box-shadow: 0 15px 35px rgba({hex_to_rgb(settings.primary_color)}, 0.2);
}}

.certificate::before {{
    border: 2px solid {settings.secondary_color};
}}

.certificate-header h2 {{
    color: {settings.primary_color};
    animation: glow 2s ease-in-out infinite alternate;
}}

@keyframes glow {{
    from {{ text-shadow: 0 0 5px rgba({hex_to_rgb(settings.primary_color)}, 0.5); }}
    to {{ text-shadow: 0 0 20px rgba({hex_to_rgb(settings.primary_color)}, 0.8); }}
}}

.student-name {{
    color: {settings.secondary_color} !important;
    text-decoration-color: {settings.primary_color};
    animation: pulse 2s ease-in-out infinite;
}}

@keyframes pulse {{
    0%, 100% {{ transform: scale(1); }}
    50% {{ transform: scale(1.02); }}
}}

.tutorial-title {{
    color: {settings.primary_color} !important;
}}

.signature-line hr {{
    border: 1px solid {settings.primary_color};
}}

.signature-line small {{
    color: {settings.secondary_color};
}}

.form-control {{
    border: 2px solid rgba({hex_to_rgb(settings.primary_color)}, 0.3);
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}}

.form-control:focus {{
    border-color: {settings.primary_color};
    box-shadow: 0 0 0 0.2rem rgba({hex_to_rgb(settings.primary_color)}, 0.25);
    transform: scale(1.02);
}}

.text-primary {{
    color: {settings.text_color} !important;
}}

.card-title {{
    color: {settings.text_color};
    transition: color 0.3s ease;
}}

.post-content {{
    color: {settings.text_color};
    line-height: 1.8;
    transition: all 0.3s ease;
}}

.mobile-alert {{
    animation: slideInDown 0.5s ease-out;
}}

@keyframes slideInDown {{
    from {{
        transform: translateY(-100%);
        opacity: 0;
    }}
    to {{
        transform: translateY(0);
        opacity: 1;
    }}
}}

.featured-image {{
    transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}}

.featured-image:hover {{
    transform: scale(1.05);
}}

/* Floating animation for icons */
.nav-item i {{
    animation: float 3s ease-in-out infinite;
}}

@keyframes float {{
    0%, 100% {{ transform: translateY(0px); }}
    50% {{ transform: translateY(-5px); }}
}}

/* Ripple effect for buttons */
.btn-gradient {{
    position: relative;
    overflow: hidden;
}}

.btn-gradient:active::after {{
    content: '';
    position: absolute;
    top: 50%;
    left: 50%;
    width: 0;
    height: 0;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.5);
    transform: translate(-50%, -50%);
    animation: ripple 0.6s ease-out;
}}

@keyframes ripple {{
    to {{
        width: 300px;
        height: 300px;
        opacity: 0;
    }}
}}

/* Smooth transitions for all interactive elements */
* {{
    transition: color 0.3s ease, background-color 0.3s ease, border-color 0.3s ease, transform 0.3s ease;
}}
"""
    
    from flask import Response
    return Response(css_content, mimetype='text/css')

def hex_to_rgb(hex_color):
    """Convert hex color to RGB values for rgba usage"""
    hex_color = hex_color.lstrip('#')
    return ', '.join(str(int(hex_color[i:i+2], 16)) for i in (0, 2, 4))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)