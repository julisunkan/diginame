from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

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
    card_background = db.Column(db.String(7), nullable=False, default='#ffffff')
    text_color = db.Column(db.String(7), nullable=False, default='#333333')
    navbar_color = db.Column(db.String(7), nullable=False, default='#000000')

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)