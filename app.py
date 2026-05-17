import os
import re
import json
import logging
import functools
from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import datetime, timedelta
from config import config
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf.csrf import CSRFProtect

logging.basicConfig(level=logging.DEBUG)

# ---------------------------------------------------------------------------
# Firebase initialisation
# ---------------------------------------------------------------------------

_firestore_client = None

def get_db():
    """Return a Firestore client, initialising Firebase on first call."""
    global _firestore_client
    if _firestore_client is not None:
        return _firestore_client

    service_account_raw = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
    if not service_account_raw:
        raise RuntimeError(
            "FIREBASE_SERVICE_ACCOUNT environment variable is not set. "
            "Add your Firebase service-account JSON as that secret."
        )

    import firebase_admin
    from firebase_admin import credentials, firestore as fb_firestore

    if not firebase_admin._apps:
        try:
            service_account_info = json.loads(service_account_raw)
            cred = credentials.Certificate(service_account_info)
        except (json.JSONDecodeError, ValueError):
            cred = credentials.Certificate(service_account_raw)
        firebase_admin.initialize_app(cred)

    _firestore_client = fb_firestore.client()
    return _firestore_client


# ---------------------------------------------------------------------------
# Lightweight data classes (replicate the SQLAlchemy model interface so that
# existing Jinja templates work without modification)
# ---------------------------------------------------------------------------

def slugify(text):
    """Convert a tag name to a URL-safe slug."""
    text = str(text).lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('-')


class Post:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self.title = data.get('title', '')
        self.content = data.get('content', '')
        self.featured_image = data.get('featured_image') or None
        raw_tags = data.get('tags', [])
        self.tags = raw_tags if isinstance(raw_tags, list) else []
        raw_ts = data.get('created_at')
        if isinstance(raw_ts, datetime):
            self.created_at = raw_ts
        else:
            self.created_at = datetime.utcnow()

    def to_dict(self):
        return {
            'title': self.title,
            'content': self.content,
            'featured_image': self.featured_image,
            'tags': self.tags,
            'created_at': self.created_at,
        }


DEFAULT_SETTINGS = {
    'blog_title': 'Blog CMS',
    'blog_description': 'Welcome to Our Blog',
    'primary_color': '#667eea',
    'secondary_color': '#764ba2',
    'background_color': '#667eea',
    'overall_background': '#1a1a2e',
    'card_background': '#ffffff',
    'text_color': '#333333',
    'navbar_color': '#000000',
}


class SiteSettings:
    def __init__(self, data=None):
        d = {**DEFAULT_SETTINGS, **(data or {})}
        self.blog_title = d['blog_title']
        self.blog_description = d['blog_description']
        self.primary_color = d['primary_color']
        self.secondary_color = d['secondary_color']
        self.background_color = d['background_color']
        self.overall_background = d['overall_background']
        self.card_background = d['card_background']
        self.text_color = d['text_color']
        self.navbar_color = d['navbar_color']

    def to_dict(self):
        return {
            'blog_title': self.blog_title,
            'blog_description': self.blog_description,
            'primary_color': self.primary_color,
            'secondary_color': self.secondary_color,
            'background_color': self.background_color,
            'overall_background': self.overall_background,
            'card_background': self.card_background,
            'text_color': self.text_color,
            'navbar_color': self.navbar_color,
        }


# ---------------------------------------------------------------------------
# Firestore helpers
# ---------------------------------------------------------------------------

def fs_get_all_posts():
    db = get_db()
    docs = db.collection('posts').order_by(
        'created_at', direction='DESCENDING'
    ).stream()
    return [Post(doc.id, doc.to_dict()) for doc in docs]


def fs_get_post(post_id):
    db = get_db()
    doc = db.collection('posts').document(str(post_id)).get()
    if not doc.exists:
        return None
    return Post(doc.id, doc.to_dict())


def fs_create_post(title, content, featured_image=None, tags=None):
    db = get_db()
    data = {
        'title': title,
        'content': content,
        'featured_image': featured_image,
        'tags': tags or [],
        'created_at': datetime.utcnow(),
    }
    _, doc_ref = db.collection('posts').add(data)
    return doc_ref.id


def fs_update_post(post_id, title, content, featured_image=None, tags=None):
    db = get_db()
    db.collection('posts').document(str(post_id)).update({
        'title': title,
        'content': content,
        'featured_image': featured_image,
        'tags': tags or [],
    })


def fs_delete_post(post_id):
    db = get_db()
    db.collection('posts').document(str(post_id)).delete()


def fs_get_posts_by_tag(tag_slug):
    """Return posts whose tags contain a tag matching the given slug."""
    posts = fs_get_all_posts()
    return [p for p in posts if any(slugify(t) == tag_slug for t in p.tags)]


def fs_get_all_tags():
    """Return a sorted list of all unique tag names across all posts."""
    posts = fs_get_all_posts()
    tag_set = {}
    for p in posts:
        for t in p.tags:
            tag_set[slugify(t)] = t
    return sorted(tag_set.values(), key=str.lower)


def fs_find_tag_by_slug(slug):
    """Return the original tag name for a given slug, or None."""
    for t in fs_get_all_tags():
        if slugify(t) == slug:
            return t
    return None


def fs_get_related_posts(post, limit=3):
    """Return up to `limit` posts sharing at least one tag, excluding `post`."""
    if not post.tags:
        return []
    post_slugs = {slugify(t) for t in post.tags}
    candidates = []
    for p in fs_get_all_posts():
        if p.id == post.id:
            continue
        overlap = sum(1 for t in p.tags if slugify(t) in post_slugs)
        if overlap:
            candidates.append((overlap, p))
    candidates.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in candidates[:limit]]


def fs_get_settings():
    db = get_db()
    doc = db.collection('settings').document('main').get()
    return SiteSettings(doc.to_dict() if doc.exists else None)


def fs_save_settings(data_dict):
    db = get_db()
    db.collection('settings').document('main').set(data_dict)


def fs_get_admin():
    """Return admin credentials dict from Firestore."""
    db = get_db()
    doc = db.collection('admin').document('credentials').get()
    return doc.to_dict() if doc.exists else None


def fs_bootstrap_admin():
    """
    If no admin document exists yet, create one from ADMIN_USERNAME /
    ADMIN_PASSWORD environment variables and store the hashed password.
    """
    db = get_db()
    doc = db.collection('admin').document('credentials').get()
    if doc.exists:
        return
    username = os.environ.get('ADMIN_USERNAME', 'admin')
    password = os.environ.get('ADMIN_PASSWORD', 'admin123')
    db.collection('admin').document('credentials').set({
        'username': username,
        'password_hash': generate_password_hash(password),
    })
    logging.info("Admin credentials bootstrapped into Firestore.")


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

def create_app(config_name='default'):
    app = Flask(__name__)
    config_name = config_name or os.environ.get('FLASK_ENV', 'default')
    config_class = config[config_name]
    if config_name == 'production':
        app.config.from_object(config_class())
    else:
        app.config.from_object(config_class)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
    CSRFProtect(app)
    return app


app = create_app(os.environ.get('FLASK_ENV', 'development'))

# Bootstrap admin credentials into Firestore on startup (no-op if already set)
try:
    fs_bootstrap_admin()
except Exception as e:
    logging.warning(f"Could not bootstrap admin credentials: {e}")


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def login_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function


# ---------------------------------------------------------------------------
# Context processor — site settings available in every template
# ---------------------------------------------------------------------------

def get_site_settings():
    try:
        return fs_get_settings()
    except Exception as e:
        logging.warning(f"Could not load site settings: {e}")
        return SiteSettings()


@app.context_processor
def inject_site_settings():
    return {'site_settings': get_site_settings()}


# ---------------------------------------------------------------------------
# Public routes
# ---------------------------------------------------------------------------

@app.template_filter('slugify')
def slugify_filter(text):
    return slugify(text)


@app.route('/')
def index():
    try:
        posts = fs_get_all_posts()
        all_tags = fs_get_all_tags()
    except Exception as e:
        logging.error(f"Error loading posts: {e}")
        posts = []
        all_tags = []
    return render_template('index.html', posts=posts, all_tags=all_tags)


@app.route('/post/<string:id>')
def post_detail(id):
    post = fs_get_post(id)
    if post is None:
        from flask import abort
        abort(404)
    try:
        related = fs_get_related_posts(post)
    except Exception:
        related = []
    return render_template('post_detail.html', post=post, related_posts=related)


@app.route('/category/<string:tag>')
def category(tag):
    tag_name = fs_find_tag_by_slug(tag)
    if tag_name is None:
        tag_name = tag.replace('-', ' ').title()
    try:
        posts = fs_get_posts_by_tag(tag)
        all_tags = fs_get_all_tags()
    except Exception as e:
        logging.error(f"Error loading category posts: {e}")
        posts = []
        all_tags = []
    return render_template('category.html', posts=posts, tag=tag_name, all_tags=all_tags)


# ---------------------------------------------------------------------------
# Admin authentication
# ---------------------------------------------------------------------------

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    admin = None
    try:
        admin = fs_get_admin()
        stored_username = admin.get('username', 'admin') if admin else 'admin'
    except Exception:
        stored_username = 'admin'

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        try:
            if admin and username == admin.get('username') and \
                    check_password_hash(admin.get('password_hash', ''), password):
                session['logged_in'] = True
                session.permanent = True
                flash('Logged in successfully!', 'success')
                return redirect(url_for('admin_dashboard'))
        except Exception as e:
            logging.error(f"Login error: {e}")
            flash('Could not verify credentials. Check Firebase configuration.', 'error')
            return render_template('login.html', stored_username=stored_username)
        flash('Invalid credentials!', 'error')
    return render_template('login.html', stored_username=stored_username)


@app.route('/admin/logout')
@login_required
def admin_logout():
    session.pop('logged_in', None)
    flash('Logged out successfully!', 'success')
    return redirect(url_for('index'))


# ---------------------------------------------------------------------------
# Admin dashboard & post management
# ---------------------------------------------------------------------------

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    try:
        posts = fs_get_all_posts()
    except Exception as e:
        logging.error(f"Error loading posts: {e}")
        posts = []
    return render_template('dashboard.html', posts=posts)


@app.route('/admin/new', methods=['GET', 'POST'])
@login_required
def new_post():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        if not title or not content:
            flash('Title and content are required.', 'error')
            return redirect(url_for('new_post'))
        featured_image = request.form.get('featured_image', '').strip() or None
        raw_tags = request.form.get('tags', '')
        tags = [t.strip() for t in raw_tags.split(',') if t.strip()]
        try:
            fs_create_post(title, content, featured_image, tags)
            flash('Post created successfully!', 'success')
        except Exception as e:
            logging.error(f"Error creating post: {e}")
            flash(f'Error creating post: {e}', 'error')
        return redirect(url_for('admin_dashboard'))
    try:
        all_tags = fs_get_all_tags()
    except Exception:
        all_tags = []
    return render_template('new_post.html', all_tags=all_tags)


@app.route('/admin/edit/<string:id>', methods=['GET', 'POST'])
@login_required
def edit_post(id):
    post = fs_get_post(id)
    if post is None:
        from flask import abort
        abort(404)
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        if not title or not content:
            flash('Title and content are required.', 'error')
            return redirect(url_for('edit_post', id=id))
        raw_tags = request.form.get('tags', '')
        tags = [t.strip() for t in raw_tags.split(',') if t.strip()]
        try:
            fs_update_post(
                id,
                title,
                content,
                request.form.get('featured_image', '').strip() or None,
                tags,
            )
            flash('Post updated successfully!', 'success')
        except Exception as e:
            logging.error(f"Error updating post: {e}")
            flash(f'Error updating post: {e}', 'error')
        return redirect(url_for('admin_dashboard'))
    try:
        all_tags = fs_get_all_tags()
    except Exception:
        all_tags = []
    return render_template('edit_post.html', post=post, all_tags=all_tags)


@app.route('/admin/delete/<string:id>', methods=['POST'])
@login_required
def delete_post(id):
    try:
        fs_delete_post(id)
        flash('Post deleted successfully!', 'success')
    except Exception as e:
        logging.error(f"Error deleting post: {e}")
        flash(f'Error deleting post: {e}', 'error')
    return redirect(url_for('admin_dashboard'))


# ---------------------------------------------------------------------------
# Admin settings
# ---------------------------------------------------------------------------

@app.route('/admin/change-credentials', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        action = request.form.get('action')
        current_password = request.form.get('current_password', '').strip()

        if not current_password:
            flash('Current password is required to make any changes.', 'error')
            return redirect(url_for('change_password'))

        try:
            admin = fs_get_admin()
            if not admin or not check_password_hash(admin.get('password_hash', ''), current_password):
                flash('Current password is incorrect.', 'error')
                return redirect(url_for('change_password'))

            db = get_db()
            updates = {}

            if action == 'username':
                new_username = request.form.get('new_username', '').strip()
                if not new_username:
                    flash('New username cannot be empty.', 'error')
                    return redirect(url_for('change_password'))
                if len(new_username) < 3:
                    flash('Username must be at least 3 characters.', 'error')
                    return redirect(url_for('change_password'))
                updates['username'] = new_username
                db.collection('admin').document('credentials').update(updates)
                flash('Username updated successfully!', 'success')

            elif action == 'password':
                new_password = request.form.get('new_password', '')
                confirm_password = request.form.get('confirm_password', '')
                if not new_password or not confirm_password:
                    flash('New password fields cannot be empty.', 'error')
                    return redirect(url_for('change_password'))
                if new_password != confirm_password:
                    flash('New passwords do not match.', 'error')
                    return redirect(url_for('change_password'))
                if len(new_password) < 8:
                    flash('New password must be at least 8 characters.', 'error')
                    return redirect(url_for('change_password'))
                updates['password_hash'] = generate_password_hash(new_password)
                db.collection('admin').document('credentials').update(updates)
                flash('Password updated successfully!', 'success')

            else:
                flash('Unknown action.', 'error')

            return redirect(url_for('admin_dashboard'))

        except Exception as e:
            logging.error(f"Error updating credentials: {e}")
            flash(f'Error updating credentials: {e}', 'error')

    try:
        admin = fs_get_admin()
        current_username = admin.get('username', 'admin') if admin else 'admin'
    except Exception:
        current_username = 'admin'

    return render_template('change_password.html', current_username=current_username)


@app.route('/admin/settings', methods=['GET', 'POST'])
@login_required
def admin_settings():
    settings = get_site_settings()
    if request.method == 'POST':
        new_settings = SiteSettings({
            'blog_title': request.form.get('blog_title', '').strip() or settings.blog_title,
            'blog_description': request.form.get('blog_description', '').strip() or settings.blog_description,
            'primary_color': request.form.get('primary_color', '').strip() or settings.primary_color,
            'secondary_color': request.form.get('secondary_color', '').strip() or settings.secondary_color,
            'background_color': request.form.get('background_color', '').strip() or settings.background_color,
            'overall_background': request.form.get('overall_background', '').strip() or settings.overall_background,
            'card_background': request.form.get('card_background', '').strip() or settings.card_background,
            'text_color': request.form.get('text_color', '').strip() or settings.text_color,
            'navbar_color': request.form.get('navbar_color', '').strip() or settings.navbar_color,
        })
        try:
            fs_save_settings(new_settings.to_dict())
            flash('Settings updated successfully!', 'success')
        except Exception as e:
            logging.error(f"Error saving settings: {e}")
            flash(f'Error saving settings: {e}', 'error')
        return redirect(url_for('admin_settings'))
    return render_template('admin_settings.html', settings=settings)


# ---------------------------------------------------------------------------
# Export / Import
# ---------------------------------------------------------------------------

@app.route('/admin/export')
@login_required
def export_tutorials():
    try:
        posts = fs_get_all_posts()
    except Exception as e:
        logging.error(f"Error loading posts for export: {e}")
        flash(f'Error exporting tutorials: {e}', 'error')
        return redirect(url_for('admin_dashboard'))
    tutorials_data = {
        'export_date': datetime.now().isoformat(),
        'total_posts': len(posts),
        'posts': [
            {
                'title': p.title,
                'content': p.content,
                'featured_image': p.featured_image,
                'tags': p.tags,
                'created_at': p.created_at.isoformat() if p.created_at else None,
            }
            for p in posts
        ],
    }
    json_data = json.dumps(tutorials_data, indent=2, ensure_ascii=False)
    return Response(
        json_data,
        mimetype='application/json',
        headers={
            'Content-Disposition': (
                f'attachment; filename=tutorials_export_'
                f'{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
            )
        },
    )


@app.route('/admin/import', methods=['GET', 'POST'])
@login_required
def import_tutorials():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file selected!', 'error')
            return redirect(request.url)
        file = request.files['file']
        if not file.filename:
            flash('No file selected!', 'error')
            return redirect(request.url)
        if not file.filename.lower().endswith('.json'):
            flash('Please upload a JSON file!', 'error')
            return redirect(request.url)
        try:
            data = json.loads(file.read().decode('utf-8'))
            if 'posts' not in data:
                flash('Invalid file format! Missing posts data.', 'error')
                return redirect(request.url)

            existing_titles = {p.title for p in fs_get_all_posts()}
            imported_count = skipped_count = 0
            db = get_db()

            for post_data in data['posts']:
                if not post_data.get('title') or not post_data.get('content'):
                    skipped_count += 1
                    continue
                if post_data['title'] in existing_titles:
                    skipped_count += 1
                    continue
                created_at = datetime.utcnow()
                if post_data.get('created_at'):
                    try:
                        created_at = datetime.fromisoformat(
                            post_data['created_at'].replace('Z', '+00:00')
                        )
                    except Exception:
                        pass
                db.collection('posts').add({
                    'title': post_data['title'],
                    'content': post_data['content'],
                    'featured_image': post_data.get('featured_image'),
                    'tags': post_data.get('tags', []),
                    'created_at': created_at,
                })
                existing_titles.add(post_data['title'])
                imported_count += 1

            if imported_count > 0:
                flash(
                    f'Successfully imported {imported_count} tutorials! '
                    f'Skipped {skipped_count} duplicates or invalid entries.',
                    'success',
                )
            else:
                flash(
                    f'No new tutorials imported. '
                    f'Skipped {skipped_count} duplicates or invalid entries.',
                    'info',
                )
            return redirect(url_for('admin_dashboard'))

        except json.JSONDecodeError:
            flash('Invalid JSON file format!', 'error')
            return redirect(request.url)
        except Exception as e:
            flash(f'Error importing tutorials: {e}', 'error')
            return redirect(request.url)

    return render_template('import_tutorials.html')


# ---------------------------------------------------------------------------
# Certificate
# ---------------------------------------------------------------------------

@app.route('/certificate')
def certificate_form():
    try:
        posts = fs_get_all_posts()
    except Exception:
        posts = []
    return render_template('certificate_form.html', posts=posts)


@app.route('/generate_certificate', methods=['POST'])
def generate_certificate():
    student_name = request.form.get('student_name', '').strip()
    post_id = request.form.get('post_id', '').strip()
    if not student_name:
        flash('Please enter your full name.', 'error')
        return redirect(url_for('certificate_form'))
    if not post_id:
        flash('Please select a tutorial.', 'error')
        return redirect(url_for('certificate_form'))
    post = fs_get_post(post_id)
    if not post:
        flash('Selected tutorial not found.', 'error')
        return redirect(url_for('certificate_form'))
    return redirect(url_for('download_certificate', post_id=post_id, student_name=student_name))


@app.route('/offline')
def offline():
    return render_template('offline.html')


@app.route('/manifest.json')
def serve_manifest():
    return send_from_directory('static', 'manifest.json', mimetype='application/manifest+json')


@app.route('/sw.js')
def serve_sw():
    response = send_from_directory('static', 'sw.js', mimetype='application/javascript')
    response.headers['Service-Worker-Allowed'] = '/'
    response.headers['Cache-Control'] = 'no-cache'
    return response


@app.route('/certificate/<string:post_id>/<path:student_name>')
def download_certificate(post_id, student_name):
    post = fs_get_post(post_id)
    if post is None:
        from flask import abort
        abort(404)
    settings = get_site_settings()
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
            top: 20px; left: 20px; right: 20px; bottom: 20px;
            border: 3px solid {settings.secondary_color};
            pointer-events: none;
        }}
        .certificate-title {{
            font-size: 3rem; font-weight: bold;
            color: {settings.primary_color};
            margin-bottom: 10px; letter-spacing: 3px;
        }}
        .certificate-subtitle {{
            font-size: 1.2rem; color: {settings.secondary_color}; margin-bottom: 30px;
        }}
        .student-name {{
            font-size: 2.5rem; font-weight: bold;
            color: {settings.secondary_color};
            text-decoration: underline;
            text-decoration-color: {settings.primary_color};
            margin: 20px 0;
        }}
        .tutorial-title {{
            font-size: 1.8rem; font-style: italic;
            color: {settings.primary_color}; margin: 20px 0;
        }}
        .completion-text {{ font-size: 1.1rem; line-height: 1.8; text-align: center; margin: 30px 0; }}
        .date-signature {{ display: flex; justify-content: space-between; margin-top: 60px; }}
        .signature-line {{ text-align: center; min-width: 200px; }}
        .signature-line hr {{ border: 2px solid {settings.primary_color}; margin: 10px 0; }}
        .signature-line small {{ color: {settings.secondary_color}; font-size: 0.9rem; }}
    </style>
</head>
<body>
    <div class="certificate">
        <div class="certificate-header text-center" style="margin-bottom:40px;">
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
            <div class="signature-line"><hr><small>Date</small></div>
            <div class="signature-line"><hr><small>Tutorial Platform</small></div>
        </div>
    </div>
</body>
</html>
    """
    response = Response(certificate_html, mimetype='text/html')
    response.headers['Content-Disposition'] = (
        f'attachment; filename="certificate-{student_name.replace(" ", "-").lower()}.html"'
    )
    return response


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', error_code=404,
                           error_title='Page Not Found',
                           error_msg='The page you\'re looking for doesn\'t exist or has been moved.'), 404


@app.errorhandler(500)
def internal_error(e):
    logging.error(f"500 error: {e}")
    return render_template('error.html', error_code=500,
                           error_title='Server Error',
                           error_msg='Something went wrong on our end. Please try again later.'), 500


# ---------------------------------------------------------------------------
# Dynamic CSS
# ---------------------------------------------------------------------------

def hex_to_rgb(hex_color):
    try:
        hex_color = hex_color.lstrip('#')
        if len(hex_color) != 6:
            return '79, 70, 229'
        return ', '.join(str(int(hex_color[i:i + 2], 16)) for i in (0, 2, 4))
    except (ValueError, TypeError):
        return '79, 70, 229'


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
    50%  {{ background: linear-gradient(135deg, {settings.secondary_color} 0%, {settings.primary_color} 100%); }}
}}
.btn-gradient {{
    background: linear-gradient(45deg, {settings.primary_color}, {settings.secondary_color});
    transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative; overflow: hidden;
}}
.btn-gradient::before {{
    content: ''; position: absolute; top: 0; left: -100%;
    width: 100%; height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
    transition: left 0.6s ease;
}}
.btn-gradient:hover::before {{ left: 100%; }}
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
    backdrop-filter: blur(20px); transition: all 0.3s ease;
}}
.mobile-header {{
    background: rgba({hex_to_rgb(settings.card_background)}, 0.95) !important;
    backdrop-filter: blur(20px); transition: all 0.3s ease;
}}
.bottom-nav {{
    background: rgba({hex_to_rgb(settings.card_background)}, 0.95) !important;
    backdrop-filter: blur(20px); transition: all 0.3s ease;
}}
.nav-item {{ transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); }}
.nav-item:hover {{ transform: translateY(-3px) scale(1.05); }}
.nav-item.active {{
    background: linear-gradient(45deg, {settings.primary_color}, {settings.secondary_color});
    color: white !important; border-radius: 15px;
    box-shadow: 0 8px 20px rgba({hex_to_rgb(settings.primary_color)}, 0.3);
}}
.certificate {{ border: 3px solid {settings.primary_color}; transition: all 0.3s ease; }}
.certificate:hover {{
    transform: scale(1.02);
    box-shadow: 0 15px 35px rgba({hex_to_rgb(settings.primary_color)}, 0.2);
}}
.certificate::before {{ border: 2px solid {settings.secondary_color}; }}
.certificate-header h2 {{
    color: {settings.primary_color};
    animation: glow 2s ease-in-out infinite alternate;
}}
@keyframes glow {{
    from {{ text-shadow: 0 0 5px rgba({hex_to_rgb(settings.primary_color)}, 0.5); }}
    to   {{ text-shadow: 0 0 20px rgba({hex_to_rgb(settings.primary_color)}, 0.8); }}
}}
.student-name {{
    color: {settings.secondary_color} !important;
    text-decoration-color: {settings.primary_color};
    animation: pulse 2s ease-in-out infinite;
}}
@keyframes pulse {{
    0%, 100% {{ transform: scale(1); }}
    50%       {{ transform: scale(1.02); }}
}}
.tutorial-title {{ color: {settings.primary_color} !important; }}
.signature-line hr  {{ border: 1px solid {settings.primary_color}; }}
.signature-line small {{ color: {settings.secondary_color}; }}
.form-control {{
    border: 2px solid rgba({hex_to_rgb(settings.primary_color)}, 0.3);
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}}
.form-control:focus {{
    border-color: {settings.primary_color};
    box-shadow: 0 0 0 0.2rem rgba({hex_to_rgb(settings.primary_color)}, 0.25);
    transform: scale(1.02);
}}
.text-primary  {{ color: {settings.text_color} !important; }}
.card-title    {{ color: {settings.text_color}; transition: color 0.3s ease; }}
.post-content  {{ color: {settings.text_color}; line-height: 1.8; transition: all 0.3s ease; }}
.mobile-alert  {{ animation: slideInDown 0.5s ease-out; }}
@keyframes slideInDown {{
    from {{ transform: translateY(-100%); opacity: 0; }}
    to   {{ transform: translateY(0); opacity: 1; }}
}}
.featured-image {{ transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); }}
.featured-image:hover {{ transform: scale(1.05); }}
.nav-item i {{ animation: float 3s ease-in-out infinite; }}
@keyframes float {{
    0%, 100% {{ transform: translateY(0px); }}
    50%       {{ transform: translateY(-5px); }}
}}
.btn-gradient {{ position: relative; overflow: hidden; }}
.btn-gradient:active::after {{
    content: ''; position: absolute; top: 50%; left: 50%;
    width: 0; height: 0; border-radius: 50%;
    background: rgba(255,255,255,0.5);
    transform: translate(-50%, -50%);
    animation: ripple 0.6s ease-out;
}}
@keyframes ripple {{
    to {{ width: 300px; height: 300px; opacity: 0; }}
}}
a, button, .btn, .card, .nav-item, .form-control, .tag-chip, .category-pill {{ 
    transition: color 0.3s ease, background-color 0.3s ease, border-color 0.3s ease, transform 0.3s ease, box-shadow 0.3s ease; 
}}
"""
    return Response(css_content, mimetype='text/css')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
