# app.py
import os
from datetime import datetime, date, timedelta
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# تحميل متغيرات البيئة
load_dotenv()

# استيراد قاعدة البيانات والأدوات المساعدة
from models import db, User, Category, Size, Thickness, Supplier, Customer
from models import FactoryRawMaterial, FactoryProduction, FactoryDiary
from models import StoreSale, StorePurchase, StoreInventory, StoreReceiving, StoreReturn, StoreDiary
from models import TreasuryAccount, TreasuryTransaction, TreasuryTransfer
from models import EditLog, Notification
from utils import (
    login_required as custom_login_required,
    role_required,
    can_edit,
    add_row_to_excel,
    generate_word_report,
    GoogleDriveService
)

# ==================== تهيئة التطبيق ====================
app = Flask(__name__)

# الإعدادات السرية
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-me')

# إعدادات الجلسة - من خبرة Adam Cargo
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = '/tmp/flask_session'
app.config['SESSION_PERMANENT'] = True
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False

# إعدادات قاعدة البيانات
database_url = os.environ.get('DATABASE_URL', 'sqlite:///instance/factory.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_timeout': 30,
    'pool_recycle': 300
}

# ربط قاعدة البيانات مع التطبيق
db.init_app(app)

# إعداد Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'يرجى تسجيل الدخول أولاً'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ==================== خدمة Google Drive ====================
drive_service = GoogleDriveService(
    credentials_file=os.environ.get('GOOGLE_CREDENTIALS_FILE', 'client_secrets.json'),
    folder_id=os.environ.get('GOOGLE_DRIVE_FOLDER_ID', '')
)

# ==================== تهيئة قاعدة البيانات ====================
def init_db():
    """إنشاء الجداول والمستخدمين الافتراضيين"""
    with app.app_context():
        db.create_all()

        # إضافة الأعمدة الجديدة بأمان (إن لم تكن موجودة)
        try:
            db.session.execute(db.text('ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(20)'))
            db.session.commit()
        except:
            pass

        # إنشاء المستخدمين الافتراضيين
        users_data = [
            {'username': os.environ.get('MEG_USERNAME', 'meg'),
             'password': os.environ.get('MEG_PASSWORD', '262004'),
             'full_name': 'MEG',
             'role': 'meg',
             'is_hidden': True},
            {'username': os.environ.get('ADMIN_USERNAME', 'f'),
             'password': os.environ.get('ADMIN_PASSWORD', '*1997#'),
             'full_name': 'Admin',
             'role': 'admin',
             'is_hidden': False},
            {'username': os.environ.get('MARIAM_USERNAME', 'mariam'),
             'password': os.environ.get('MARIAM_PASSWORD', '#mariam2004'),
             'full_name': 'Mariam',
             'role': 'mariam',
             'is_hidden': False},
            {'username': os.environ.get('REHAB_USERNAME', 'rehab'),
             'password': os.environ.get('REHAB_PASSWORD', 'rehab2004#'),
             'full_name': 'Rehab',
             'role': 'rehab',
             'is_hidden': False},
            {'username': os.environ.get('MOHAMED_USERNAME', 'mohamed'),
             'password': os.environ.get('MOHAMED_PASSWORD', 'mohamed123#'),
             'full_name': 'Mohamed',
             'role': 'mohamed',
             'is_hidden': False},
            {'username': os.environ.get('AHMED_USERNAME', 'a'),
             'password': os.environ.get('AHMED_PASSWORD', '#123456#'),
             'full_name': 'الحاج أحمد',
             'role': 'ahmed',
             'is_hidden': False},
            {'username': os.environ.get('EID_USERNAME', 'eid'),
             'password': os.environ.get('EID_PASSWORD', 'eid123#'),
             'full_name': 'عيد',
             'role': 'eid',
             'is_hidden': False},
            {'username': os.environ.get('ABDO_USERNAME', 'abdo'),
             'password': os.environ.get('ABDO_PASSWORD', 'abdo123#'),
             'full_name': 'عبدالله',
             'role': 'abdo',
             'is_hidden': False},
        ]

        for user_data in users_data:
            existing_user = User.query.filter_by(username=user_data['username']).first()
            if not existing_user:
                new_user = User(
                    username=user_data['username'],
                    full_name=user_data['full_name'],
                    role=user_data['role'],
                    is_hidden=user_data['is_hidden'],
                    created_at=datetime.utcnow()
                )
                new_user.set_password(user_data['password'])
                db.session.add(new_user)

        db.session.commit()
        print("✅ تم تهيئة قاعدة البيانات وإنشاء المستخدمين")

# تنفيذ التهيئة - مهم جداً أن تكون خارج if __name__ لتشتغل على Render
init_db()

# ==================== أدوات مساعدة للقوالب ====================
@app.context_processor
def inject_globals():
    unread_notifications = 0
    if current_user.is_authenticated:
        unread_notifications = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    return {
        'now': datetime.now(),
        'unread_notifications': unread_notifications
    }

# ==================== دوال مساعدة للخزينة ====================
def get_or_create_treasury_account(person_name, account_type):
    account = TreasuryAccount.query.filter_by(person_name=person_name, account_type=account_type).first()
    if not account:
        account = TreasuryAccount(person_name=person_name, account_type=account_type, balance=0)
        db.session.add(account)
        db.session.commit()
    return account

def get_visible_accounts_for_current_user():
    if current_user.role in ['meg', 'admin', 'mariam']:
        return TreasuryAccount.query.all()
    elif current_user.role == 'ahmed':
        return TreasuryAccount.query.filter_by(person_name='الحاج أحمد').all()
    elif current_user.role == 'eid':
        return TreasuryAccount.query.filter_by(person_name='عيد').all()
    elif current_user.role == 'abdo':
        return TreasuryAccount.query.filter_by(person_name='عبدالله').all()
    else:
        return []

# ==================== Routes الأساسية ====================
@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'message': 'مصنع الفتح شغال'})

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            session.permanent = True
            session['role'] = user.role
            session['user_id'] = user.id
            session['full_name'] = user.full_name

            # تسجيل إشعار للأدمن
            if user.role != 'admin':
                admin_user = User.query.filter_by(role='admin').first()
                if admin_user:
                    notification = Notification(
                        user_id=admin_user.id,
                        message=f"تم تسجيل دخول {user.full_name} ({user.role})"
                    )
                    db.session.add(notification)
                    db.session.commit()

            flash(f'مرحباً {user.full_name} 👋', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('اسم المستخدم أو كلمة المرور غير صحيحة', 'danger')

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.clear()
    flash('تم تسجيل الخروج بنجاح', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@custom_login_required
def dashboard():
    stats = {
        'raw_materials_count': FactoryRawMaterial.query.count(),
        'production_count': FactoryProduction.query.count(),
        'sales_count': StoreSale.query.count(),
        'purchases_count': StorePurchase.query.count(),
        'customers_count': Customer.query.count(),
        'suppliers_count': Supplier.query.count(),
        'treasury_balance': db.session.query(db.func.sum(TreasuryAccount.balance)).scalar() or 0,
        'today_sales': db.session.query(db.func.sum(StoreSale.total)).filter(StoreSale.date == date.today()).scalar() or 0,
        'today_purchases': db.session.query(db.func.sum(StorePurchase.total)).filter(StorePurchase.date == date.today()).scalar() or 0,
        'low_inventory_count': StoreInventory.query.filter(StoreInventory.current_quantity <= StoreInventory.min_quantity).count(),
    }

    recent_sales = StoreSale.query.order_by(StoreSale.date.desc()).limit(5).all()
    recent_production = FactoryProduction.query.order_by(FactoryProduction.date.desc()).limit(5).all()
    recent_transactions = TreasuryTransaction.query.order_by(TreasuryTransaction.date.desc()).limit(5).all()

    return render_template('dashboard.html', stats=stats,
                           recent_sales=recent_sales,
                           recent_production=recent_production,
                           recent_transactions=recent_transactions)

# ==================== المصنع ====================
@app.route('/factory')
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'mohamed')
def factory_index():
    today = date.today()
    raw_materials = FactoryRawMaterial.query.filter_by(date=today).order_by(FactoryRawMaterial.id.asc()).all()
    production = FactoryProduction.query.filter_by(date=today).order_by(FactoryProduction.id.asc()).all()
    diary = FactoryDiary.query.filter_by(date=today).order_by(FactoryDiary.id.asc()).all()
    return render_template('factory/index.html',
                           raw_materials=raw_materials,
                           production=production,
                           diary=diary)

@app.route('/factory/raw-materials', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'mohamed')
def factory_raw_materials():
    if request.method == 'POST':
        if request.form.get('delete_id'):
            record_id = int(request.form.get('delete_id'))
            record = FactoryRawMaterial.query.get_or_404(record_id)
            if current_user.role in ['meg', 'admin']:
                db.session.delete(record)
                db.session.commit()
                flash('تم حذف السجل بنجاح', 'success')
            else:
                flash('غير مصرح لك بالحذف', 'danger')
            return redirect(url_for('factory_raw_materials'))

        if request.form.get('edit_id'):
            record_id = int(request.form.get('edit_id'))
            record = FactoryRawMaterial.query.get_or_404(record_id)
            if can_edit(current_user.role, record.date, record.created_by, current_user.id):
                record.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
                record.pipe_size = request.form.get('pipe_size')
                record.pipe_thickness = request.form.get('pipe_thickness')
                record.quantity = float(request.form.get('quantity', 0))
                record.supplier = request.form.get('supplier')
                record.notes = request.form.get('notes')
                db.session.commit()
                flash('تم تحديث السجل بنجاح', 'success')
            else:
                flash('غير مصرح لك بالتعديل أو انتهت صلاحية التعديل', 'danger')
            return redirect(url_for('factory_raw_materials'))

        record_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        pipe_size = request.form.get('pipe_size')
        pipe_thickness = request.form.get('pipe_thickness')
        quantity = float(request.form.get('quantity', 0))
        supplier = request.form.get('supplier')
        notes = request.form.get('notes')

        new_record = FactoryRawMaterial(
            date=record_date,
            pipe_size=pipe_size,
            pipe_thickness=pipe_thickness,
            quantity=quantity,
            supplier=supplier,
            notes=notes,
            created_by=current_user.id,
            created_at=datetime.utcnow()
        )
        db.session.add(new_record)
        db.session.commit()

        row_data = [record_date.strftime('%Y-%m-%d'), 'وارد', pipe_size, pipe_thickness,
                    quantity, supplier, notes, current_user.full_name]
        excel_path = add_row_to_excel('يوميات المصنع.xlsx',
                                      ['التاريخ', 'الوصف', 'المقاس', 'السماكة', 'الكمية', 'المورد', 'ملاحظات', 'المسؤول'],
                                      row_data)
        if excel_path:
            drive_service.upload_file(excel_path, 'يوميات المصنع.xlsx')

        flash('تم إضافة وارد المواسير بنجاح', 'success')
        return redirect(url_for('factory_raw_materials'))

    materials = FactoryRawMaterial.query.order_by(FactoryRawMaterial.date.asc(), FactoryRawMaterial.id.asc()).all()
    return render_template('factory/raw_materials.html', materials=materials)

@app.route('/factory/production', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'mohamed')
def factory_production():
    if request.method == 'POST':
        if request.form.get('delete_id'):
            record_id = int(request.form.get('delete_id'))
            record = FactoryProduction.query.get_or_404(record_id)
            if current_user.role in ['meg', 'admin']:
                db.session.delete(record)
                db.session.commit()
                flash('تم حذف السجل بنجاح', 'success')
            else:
                flash('غير مصرح لك بالحذف', 'danger')
            return redirect(url_for('factory_production'))

        if request.form.get('edit_id'):
            record_id = int(request.form.get('edit_id'))
            record = FactoryProduction.query.get_or_404(record_id)
            if can_edit(current_user.role, record.date, record.created_by, current_user.id):
                record.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
                record.elbow_size = request.form.get('elbow_size')
                record.elbow_thickness = request.form.get('elbow_thickness')
                record.quantity = float(request.form.get('quantity', 0))
                record.raw_material_used = float(request.form.get('raw_material_used', 0))
                record.notes = request.form.get('notes')
                db.session.commit()
                flash('تم تحديث السجل بنجاح', 'success')
            else:
                flash('غير مصرح لك بالتعديل أو انتهت صلاحية التعديل', 'danger')
            return redirect(url_for('factory_production'))

        record_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        elbow_size = request.form.get('elbow_size')
        elbow_thickness = request.form.get('elbow_thickness')
        quantity = float(request.form.get('quantity', 0))
        raw_material_used = float(request.form.get('raw_material_used', 0))
        notes = request.form.get('notes')

        new_record = FactoryProduction(
            date=record_date,
            elbow_size=elbow_size,
            elbow_thickness=elbow_thickness,
            quantity=quantity,
            raw_material_used=raw_material_used,
            notes=notes,
            created_by=current_user.id,
            created_at=datetime.utcnow()
        )
        db.session.add(new_record)
        db.session.commit()

        row_data = [record_date.strftime('%Y-%m-%d'), 'إنتاج', elbow_size, elbow_thickness,
                    quantity, raw_material_used, notes, current_user.full_name]
        excel_path = add_row_to_excel('يوميات المصنع.xlsx',
                                      ['التاريخ', 'الوصف', 'المقاس', 'السماكة', 'الكمية', 'خام مستخدم', 'ملاحظات', 'المسؤول'],
                                      row_data)
        if excel_path:
            drive_service.upload_file(excel_path, 'يوميات المصنع.xlsx')

        flash('تم تسجيل الإنتاج بنجاح', 'success')
        return redirect(url_for('factory_production'))

    production = FactoryProduction.query.order_by(FactoryProduction.date.asc(), FactoryProduction.id.asc()).all()
    return render_template('factory/production.html', production=production)

@app.route('/factory/diary', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'mohamed')
def factory_diary():
    if request.method == 'POST':
        if request.form.get('delete_id'):
            record_id = int(request.form.get('delete_id'))
            record = FactoryDiary.query.get_or_404(record_id)
            if current_user.role in ['meg', 'admin']:
                db.session.delete(record)
                db.session.commit()
                flash('تم حذف السجل بنجاح', 'success')
            else:
                flash('غير مصرح لك بالحذف', 'danger')
            return redirect(url_for('factory_diary'))

        if request.form.get('edit_id'):
            record_id = int(request.form.get('edit_id'))
            record = FactoryDiary.query.get_or_404(record_id)
            if can_edit(current_user.role, record.date, record.created_by, current_user.id):
                record.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
                record.description = request.form.get('description')
                record.amount = float(request.form.get('amount', 0))
                db.session.commit()
                flash('تم تحديث السجل بنجاح', 'success')
            else:
                flash('غير مصرح لك بالتعديل أو انتهت صلاحية التعديل', 'danger')
            return redirect(url_for('factory_diary'))

        record_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        description = request.form.get('description')
        amount = float(request.form.get('amount', 0))

        new_record = FactoryDiary(
            date=record_date,
            description=description,
            amount=amount,
            created_by=current_user.id,
            created_at=datetime.utcnow()
        )
        db.session.add(new_record)
        db.session.commit()

        row_data = [record_date.strftime('%Y-%m-%d'), description, amount, current_user.full_name]
        excel_path = add_row_to_excel('يوميات المصنع.xlsx',
                                      ['التاريخ', 'الوصف', 'المبلغ', 'المسؤول'],
                                      row_data)
        if excel_path:
            drive_service.upload_file(excel_path, 'يوميات المصنع.xlsx')

        flash('تم تسجيل اليومية بنجاح', 'success')
        return redirect(url_for('factory_diary'))

    diary = FactoryDiary.query.order_by(FactoryDiary.date.asc(), FactoryDiary.id.asc()).all()
    return render_template('factory/diary.html', diary=diary)

# ==================== المحل ====================
@app.route('/store')
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'ahmed')
def store_index():
    today = date.today()
    sales = StoreSale.query.filter_by(date=today).order_by(StoreSale.id.asc()).all()
    purchases = StorePurchase.query.filter_by(date=today).order_by(StorePurchase.id.asc()).all()
    receiving = StoreReceiving.query.filter_by(date=today).order_by(StoreReceiving.id.asc()).all()
    return render_template('store/index.html',
                           sales=sales,
                           purchases=purchases,
                           receiving=receiving)

@app.route('/store/sales', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'ahmed')
def store_sales():
    if request.method == 'POST':
        if request.form.get('delete_id'):
            record_id = int(request.form.get('delete_id'))
            record = StoreSale.query.get_or_404(record_id)
            if current_user.role in ['meg', 'admin']:
                inventory_item = StoreInventory.query.filter_by(
                    product_type=record.product_type,
                    product_size=record.product_size,
                    product_spec=record.product_spec
                ).first()
                if inventory_item:
                    inventory_item.current_quantity += record.quantity
                    db.session.commit()
                db.session.delete(record)
                db.session.commit()
                flash('تم حذف البيع بنجاح', 'success')
            else:
                flash('غير مصرح لك بالحذف', 'danger')
            return redirect(url_for('store_sales'))

        if request.form.get('edit_id'):
            record_id = int(request.form.get('edit_id'))
            record = StoreSale.query.get_or_404(record_id)
            if can_edit(current_user.role, record.date, record.created_by, current_user.id):
                old_qty = record.quantity
                inventory_item = StoreInventory.query.filter_by(
                    product_type=record.product_type,
                    product_size=record.product_size,
                    product_spec=record.product_spec
                ).first()
                if inventory_item:
                    inventory_item.current_quantity += old_qty
                    db.session.commit()

                record.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
                record.customer_name = request.form.get('customer_name')
                record.customer_phone = request.form.get('customer_phone')
                record.product_type = request.form.get('product_type')
                record.product_size = request.form.get('product_size')
                record.product_spec = request.form.get('product_spec')
                record.quantity = float(request.form.get('quantity', 0))
                record.unit_price = float(request.form.get('unit_price', 0))
                record.payment_type = request.form.get('payment_type', 'آجل')
                record.total = record.quantity * record.unit_price

                if inventory_item:
                    inventory_item.current_quantity -= record.quantity
                    db.session.commit()
                else:
                    new_inv = StoreInventory(
                        product_type=record.product_type,
                        product_size=record.product_size,
                        product_spec=record.product_spec,
                        current_quantity=-record.quantity
                    )
                    db.session.add(new_inv)
                    db.session.commit()

                db.session.commit()
                flash('تم تحديث البيع بنجاح', 'success')
            else:
                flash('غير مصرح لك بالتعديل أو انتهت صلاحية التعديل', 'danger')
            return redirect(url_for('store_sales'))

        record_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        customer_name = request.form.get('customer_name')
        customer_phone = request.form.get('customer_phone')
        product_type = request.form.get('product_type')
        product_size = request.form.get('product_size')
        product_spec = request.form.get('product_spec')
        quantity = float(request.form.get('quantity', 0))
        unit_price = float(request.form.get('unit_price', 0))
        payment_type = request.form.get('payment_type', 'آجل')
        total = quantity * unit_price

        new_sale = StoreSale(
            invoice_number=f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            customer_name=customer_name,
            customer_phone=customer_phone,
            product_type=product_type,
            product_size=product_size,
            product_spec=product_spec,
            quantity=quantity,
            unit_price=unit_price,
            total=total,
            payment_type=payment_type,
            date=record_date,
            created_by=current_user.id,
            created_at=datetime.utcnow()
        )
        db.session.add(new_sale)
        db.session.commit()

        inventory_item = StoreInventory.query.filter_by(
            product_type=product_type,
            product_size=product_size,
            product_spec=product_spec
        ).first()
        if inventory_item:
            inventory_item.current_quantity -= quantity
        else:
            inventory_item = StoreInventory(
                product_type=product_type,
                product_size=product_size,
                product_spec=product_spec,
                current_quantity=-quantity
            )
            db.session.add(inventory_item)
        db.session.commit()

        # تسجيل تلقائي في يوميات المحل
        diary_entry = StoreDiary(
            date=record_date,
            description=f"بيع {quantity} {product_type} {product_size} {product_spec} إلى {customer_name}",
            amount=total,
            created_by=current_user.id,
            created_at=datetime.utcnow()
        )
        db.session.add(diary_entry)
        db.session.commit()

        row_data = [record_date.strftime('%Y-%m-%d'), 'بيع', customer_name, product_type,
                    product_size, product_spec, quantity, unit_price, total, payment_type, current_user.full_name]
        excel_path = add_row_to_excel('يوميات المحل.xlsx',
                                      ['التاريخ', 'النوع', 'الطرف', 'الصنف', 'المقاس', 'المواصفات',
                                       'الكمية', 'السعر', 'الإجمالي', 'الدفع', 'المسؤول'],
                                      row_data)
        if excel_path:
            drive_service.upload_file(excel_path, 'يوميات المحل.xlsx')

        flash('تم تسجيل البيع بنجاح', 'success')
        return redirect(url_for('store_sales'))

    sales = StoreSale.query.order_by(StoreSale.date.asc(), StoreSale.id.asc()).all()
    return render_template('store/sales.html', sales=sales)

@app.route('/store/purchases', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'ahmed')
def store_purchases():
    if request.method == 'POST':
        if request.form.get('delete_id'):
            record_id = int(request.form.get('delete_id'))
            record = StorePurchase.query.get_or_404(record_id)
            if current_user.role in ['meg', 'admin']:
                inventory_item = StoreInventory.query.filter_by(
                    product_type=record.product_type,
                    product_size=record.product_size,
                    product_spec=record.product_spec
                ).first()
                if inventory_item:
                    inventory_item.current_quantity -= record.quantity
                    db.session.commit()
                db.session.delete(record)
                db.session.commit()
                flash('تم حذف الشراء بنجاح', 'success')
            else:
                flash('غير مصرح لك بالحذف', 'danger')
            return redirect(url_for('store_purchases'))

        if request.form.get('edit_id'):
            record_id = int(request.form.get('edit_id'))
            record = StorePurchase.query.get_or_404(record_id)
            if can_edit(current_user.role, record.date, record.created_by, current_user.id):
                old_qty = record.quantity
                inventory_item = StoreInventory.query.filter_by(
                    product_type=record.product_type,
                    product_size=record.product_size,
                    product_spec=record.product_spec
                ).first()
                if inventory_item:
                    inventory_item.current_quantity -= old_qty
                    db.session.commit()

                record.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
                record.supplier_name = request.form.get('supplier_name')
                record.supplier_phone = request.form.get('supplier_phone')
                record.product_type = request.form.get('product_type')
                record.product_size = request.form.get('product_size')
                record.product_spec = request.form.get('product_spec')
                record.quantity = float(request.form.get('quantity', 0))
                record.unit_price = float(request.form.get('unit_price', 0))
                record.payment_type = request.form.get('payment_type', 'آجل')
                record.total = record.quantity * record.unit_price

                if inventory_item:
                    inventory_item.current_quantity += record.quantity
                    db.session.commit()
                else:
                    new_inv = StoreInventory(
                        product_type=record.product_type,
                        product_size=record.product_size,
                        product_spec=record.product_spec,
                        current_quantity=record.quantity
                    )
                    db.session.add(new_inv)
                    db.session.commit()

                db.session.commit()
                flash('تم تحديث الشراء بنجاح', 'success')
            else:
                flash('غير مصرح لك بالتعديل أو انتهت صلاحية التعديل', 'danger')
            return redirect(url_for('store_purchases'))

        record_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        supplier_name = request.form.get('supplier_name')
        supplier_phone = request.form.get('supplier_phone')
        product_type = request.form.get('product_type')
        product_size = request.form.get('product_size')
        product_spec = request.form.get('product_spec')
        quantity = float(request.form.get('quantity', 0))
        unit_price = float(request.form.get('unit_price', 0))
        payment_type = request.form.get('payment_type', 'آجل')
        total = quantity * unit_price

        new_purchase = StorePurchase(
            invoice_number=f"PUR-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            supplier_name=supplier_name,
            supplier_phone=supplier_phone,
            product_type=product_type,
            product_size=product_size,
            product_spec=product_spec,
            quantity=quantity,
            unit_price=unit_price,
            total=total,
            payment_type=payment_type,
            date=record_date,
            created_by=current_user.id,
            created_at=datetime.utcnow()
        )
        db.session.add(new_purchase)
        db.session.commit()

        inventory_item = StoreInventory.query.filter_by(
            product_type=product_type,
            product_size=product_size,
            product_spec=product_spec
        ).first()
        if inventory_item:
            inventory_item.current_quantity += quantity
        else:
            inventory_item = StoreInventory(
                product_type=product_type,
                product_size=product_size,
                product_spec=product_spec,
                current_quantity=quantity
            )
            db.session.add(inventory_item)
        db.session.commit()

        # تسجيل تلقائي في يوميات المحل
        diary_entry = StoreDiary(
            date=record_date,
            description=f"شراء {quantity} {product_type} {product_size} {product_spec} من {supplier_name}",
            amount=total,
            created_by=current_user.id,
            created_at=datetime.utcnow()
        )
        db.session.add(diary_entry)
        db.session.commit()

        row_data = [record_date.strftime('%Y-%m-%d'), 'شراء', supplier_name, product_type,
                    product_size, product_spec, quantity, unit_price, total, payment_type, current_user.full_name]
        excel_path = add_row_to_excel('يوميات المحل.xlsx',
                                      ['التاريخ', 'النوع', 'الطرف', 'الصنف', 'المقاس', 'المواصفات',
                                       'الكمية', 'السعر', 'الإجمالي', 'الدفع', 'المسؤول'],
                                      row_data)
        if excel_path:
            drive_service.upload_file(excel_path, 'يوميات المحل.xlsx')

        flash('تم تسجيل الشراء بنجاح', 'success')
        return redirect(url_for('store_purchases'))

    purchases = StorePurchase.query.order_by(StorePurchase.date.asc(), StorePurchase.id.asc()).all()
    return render_template('store/purchases.html', purchases=purchases)

====store===
@app.route('/store/inventory')
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'ahmed')
def store_inventory():
    inventory = StoreInventory.query.order_by(StoreInventory.product_type.asc(), StoreInventory.product_size.asc()).all()
    return render_template('store/inventory.html', inventory=inventory)

@app.route('/store/returns', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'ahmed')
def store_returns():
    if request.method == 'POST':
        if request.form.get('delete_id'):
            record_id = int(request.form.get('delete_id'))
            record = StoreReturn.query.get_or_404(record_id)
            if current_user.role in ['meg', 'admin']:
                db.session.delete(record)
                db.session.commit()
                flash('تم حذف المرتجع بنجاح', 'success')
            else:
                flash('غير مصرح لك بالحذف', 'danger')
            return redirect(url_for('store_returns'))

        if request.form.get('edit_id'):
            record_id = int(request.form.get('edit_id'))
            record = StoreReturn.query.get_or_404(record_id)
            if can_edit(current_user.role, record.date, record.created_by, current_user.id):
                record.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
                record.return_type = request.form.get('return_type')
                record.party_name = request.form.get('party_name')
                record.product_type = request.form.get('product_type')
                record.product_size = request.form.get('product_size')
                record.product_spec = request.form.get('product_spec')
                record.quantity = float(request.form.get('quantity', 0))
                record.reason = request.form.get('reason')
                db.session.commit()
                flash('تم تحديث المرتجع بنجاح', 'success')
            else:
                flash('غير مصرح لك بالتعديل أو انتهت صلاحية التعديل', 'danger')
            return redirect(url_for('store_returns'))

        record_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        return_type = request.form.get('return_type')
        party_name = request.form.get('party_name')
        product_type = request.form.get('product_type')
        product_size = request.form.get('product_size')
        product_spec = request.form.get('product_spec')
        quantity = float(request.form.get('quantity', 0))
        reason = request.form.get('reason')

        new_return = StoreReturn(
            date=record_date,
            return_type=return_type,
            party_name=party_name,
            product_type=product_type,
            product_size=product_size,
            product_spec=product_spec,
            quantity=quantity,
            reason=reason,
            created_by=current_user.id,
            created_at=datetime.utcnow()
        )
        db.session.add(new_return)
        db.session.commit()

        row_data = [record_date.strftime('%Y-%m-%d'), return_type, party_name, product_type,
                    product_size, product_spec, quantity, reason, current_user.full_name]
        excel_path = add_row_to_excel('يوميات المحل.xlsx',
                                      ['التاريخ', 'النوع', 'الطرف', 'الصنف', 'المقاس', 'المواصفات',
                                       'الكمية', 'السبب', 'المسؤول'],
                                      row_data)
        if excel_path:
            drive_service.upload_file(excel_path, 'يوميات المحل.xlsx')

        flash('تم تسجيل المرتجع بنجاح', 'success')
        return redirect(url_for('store_returns'))

    returns = StoreReturn.query.order_by(StoreReturn.date.asc(), StoreReturn.id.asc()).all()
    return render_template('store/returns.html', returns=returns)

@app.route('/store/diary', methods=['GET', 'POST'])
@custom_login_required
@role_required('meg', 'admin', 'mariam', 'rehab', 'ahmed')
def store_diary():
    if request.method == 'POST':
        if request.form.get('delete_id'):
            record_id = int(request.form.get('delete_id'))
            record = StoreDiary.query.get_or_404(record_id)
            if current_user.role in ['meg', 'admin']:
                db.session.delete(record)
                db.session.commit()
                flash('تم حذف اليومية بنجاح', 'success')
            else:
                flash('غير مصرح لك بالحذف', 'danger')
            return redirect(url_for('store_diary'))

        if request.form.get('edit_id'):
            record_id = int(request.form.get('edit_id'))
            record = StoreDiary.query.get_or_404(record_id)
            if can_edit(current_user.role, record.date, record.created_by, current_user.id):
                record.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
                record.description = request.form.get('description')
                record.amount = float(request.form.get('amount', 0))
                db.session.commit()
                flash('تم تحديث اليومية بنجاح', 'success')
            else:
                flash('غير مصرح لك بالتعديل أو انتهت صلاحية التعديل', 'danger')
            return redirect(url_for('store_diary'))

        record_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        description = request.form.get('description')
        amount = float(request.form.get('amount', 0))

        new_record = StoreDiary(
            date=record_date,
            description=description,
            amount=amount,
            created_by=current_user.id,
            created_at=datetime.utcnow()
        )
        db.session.add(new_record)
        db.session.commit()

        row_data = [record_date.strftime('%Y-%m-%d'), description, amount, current_user.full_name]
        excel_path = add_row_to_excel('يوميات المحل.xlsx',
                                      ['التاريخ', 'الوصف', 'المبلغ', 'المسؤول'],
                                      row_data)
        if excel_path:
            drive_service.upload_file(excel_path, 'يوميات المحل.xlsx')

        flash('تم تسجيل اليومية بنجاح', 'success')
        return redirect(url_for('store_diary'))

    diary = StoreDiary.query.order_by(StoreDiary.date.asc(), StoreDiary.id.asc()).all()
    return render_template('store/diary.html', diary=diary)
